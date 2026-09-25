"""LLM providers behind one interface: structured output into a Pydantic model.

* Ollama   - free, local, open-source models (default: Qwen2.5 7B)
* Claude   - Anthropic API via the official SDK (paid, higher quality)
* none     - returns None so every caller falls back to its rules-based path
"""
from __future__ import annotations

import logging
from typing import Protocol, TypeVar

import anthropic
import httpx
from pydantic import BaseModel, ValidationError

from .config import get_settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLM(Protocol):
    name: str
    model: str

    def structured(self, system: str, prompt: str, schema: type[T]) -> T | None: ...


class NoLLM:
    name = "none"
    model = "rules-only"

    def structured(self, system: str, prompt: str, schema: type[T]) -> T | None:
        return None


def bounded_schema(schema: dict, max_items: int = 12, max_chars: int = 900) -> dict:
    """Copy of a JSON schema with length limits added. Small local models under constrained
    decoding can otherwise loop forever inside an open-ended array or string."""
    import copy

    out = copy.deepcopy(schema)

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "array":
                node.setdefault("maxItems", max_items)
            if node.get("type") == "string":
                node.setdefault("maxLength", max_chars)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(out)
    return out


class OllamaLLM:
    name = "ollama"

    def __init__(self, base_url: str, model: str, num_ctx: int):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx

    def available(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=3)
            names = {m["name"] for m in r.json().get("models", [])}
            return self.model in names or f"{self.model}:latest" in names
        except Exception:  # noqa: BLE001
            return False

    def structured(self, system: str, prompt: str, schema: type[T]) -> T | None:
        # Ollama's `format` accepts a JSON schema and constrains decoding to it.
        for attempt in range(2):
            try:
                r = httpx.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "stream": False,
                        "format": bounded_schema(schema.model_json_schema()),
                        "options": {"temperature": 0.2, "num_ctx": self.num_ctx, "num_predict": 2500, "repeat_penalty": 1.1},
                        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                    },
                    timeout=600,
                )
                r.raise_for_status()
                return schema.model_validate_json(r.json()["message"]["content"])
            except (ValidationError, KeyError, ValueError) as exc:
                log.warning("ollama returned invalid %s (attempt %d): %s", schema.__name__, attempt + 1, exc)
            except httpx.HTTPError as exc:
                log.warning("ollama request failed: %s", exc)
                return None
        return None


class ClaudeLLM:
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=3)

    def structured(self, system: str, prompt: str, schema: type[T]) -> T | None:
        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
                # If a safety classifier declines, let the API re-run the request on a fallback model.
                extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
                extra_body={"fallbacks": "default"},
            )
        except anthropic.RateLimitError as exc:
            log.warning("claude rate limited: %s", exc.message)
            return None
        except anthropic.APIStatusError as exc:
            log.warning("claude API error %s: %s", exc.status_code, exc.message)
            return None
        except anthropic.APIConnectionError:
            log.warning("claude unreachable")
            return None
        if response.stop_reason == "refusal":
            log.warning("claude declined: %s", response.stop_details)
            return None
        if response.stop_reason == "max_tokens":
            log.warning("claude output truncated for %s", schema.__name__)
            return None
        return response.parsed_output


def get_llm() -> LLM:
    s = get_settings()
    choice = s.llm_provider.lower()
    if choice in ("auto", "ollama"):
        ollama = OllamaLLM(s.ollama_base_url, s.ollama_model, s.ollama_num_ctx)
        if ollama.available():
            return ollama
        if choice == "ollama":
            log.warning("Ollama model %s not reachable at %s - using rules-only analysis", s.ollama_model, s.ollama_base_url)
            return NoLLM()
    if choice in ("auto", "anthropic") and s.anthropic_api_key:
        return ClaudeLLM(s.anthropic_api_key, s.anthropic_model)
    return NoLLM()
