"""Cluster headline + summary from a small LLM (Ollama) or Claude, with a keyword fallback."""
from __future__ import annotations

import copy
import logging

import anthropic
import httpx
from pydantic import BaseModel, Field

from .config import get_settings

log = logging.getLogger(__name__)

SYSTEM = (
    "You summarise clusters of financial news for a retail investor. Use only the headlines and snippets given. "
    "Never invent facts, numbers or companies. Be neutral and specific."
)


class ClusterSummary(BaseModel):
    headline: str = Field(description="A news-style headline for the story these articles share, at most 14 words")
    summary: str = Field(description="2-3 sentences: what happened, which companies, and why it matters to investors")
    sentiment: float = Field(description="Overall tone for the companies involved, from -1 (very negative) to 1 (very positive)")


def _bounded(schema: dict) -> dict:
    out = copy.deepcopy(schema)
    for prop in out.get("properties", {}).values():
        if prop.get("type") == "string":
            prop.setdefault("maxLength", 600)
    return out


def _ollama(prompt: str) -> ClusterSummary | None:
    s = get_settings()
    try:
        r = httpx.post(
            f"{s.ollama_base_url.rstrip('/')}/api/chat",
            json={
                "model": s.ollama_model, "stream": False, "format": _bounded(ClusterSummary.model_json_schema()),
                "options": {"temperature": 0.2, "num_ctx": 4096, "num_predict": 400},
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            },
            timeout=300,
        )
        r.raise_for_status()
        return ClusterSummary.model_validate_json(r.json()["message"]["content"])
    except Exception as exc:  # noqa: BLE001
        log.warning("ollama summary failed: %s", exc)
        return None


def _claude(prompt: str) -> ClusterSummary | None:
    s = get_settings()
    client = anthropic.Anthropic(api_key=s.anthropic_api_key, max_retries=3)
    try:
        resp = client.messages.parse(
            model=s.anthropic_model,
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_format=ClusterSummary,
            extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
            extra_body={"fallbacks": "default"},
        )
    except anthropic.APIStatusError as exc:
        log.warning("claude API error %s: %s", exc.status_code, exc.message)
        return None
    except anthropic.APIConnectionError:
        log.warning("claude unreachable")
        return None
    if resp.stop_reason in ("refusal", "max_tokens"):
        return None
    return resp.parsed_output


def _provider() -> str:
    s = get_settings()
    choice = s.llm_provider.lower()
    if choice in ("auto", "ollama"):
        try:
            names = {m["name"] for m in httpx.get(f"{s.ollama_base_url.rstrip('/')}/api/tags", timeout=3).json().get("models", [])}
            if s.ollama_model in names or f"{s.ollama_model}:latest" in names:
                return "ollama"
        except Exception:  # noqa: BLE001
            pass
        if choice == "ollama":
            return "none"
    if choice in ("auto", "anthropic") and s.anthropic_api_key:
        return "anthropic"
    return "none"


def summarise(titles: list[str], snippets: list[str], tickers: list[str], keywords: list[str], provider: str) -> tuple[ClusterSummary, str]:
    lines = "\n".join(f"- {t}" + (f" — {s[:200]}" if s else "") for t, s in zip(titles[:12], snippets[:12]))
    prompt = f"Companies tagged: {', '.join(tickers[:8]) or 'none'}. Keywords: {', '.join(keywords)}.\n\nArticles in this cluster:\n{lines}"
    result = _ollama(prompt) if provider == "ollama" else _claude(prompt) if provider == "anthropic" else None
    if result is not None:
        result.sentiment = max(-1.0, min(1.0, result.sentiment))
        return result, "llm"
    about = ", ".join(tickers[:3]) or ", ".join(keywords[:3]) or "markets"
    return (
        ClusterSummary(
            headline=titles[0][:140],
            summary=f"{len(titles)} related articles about {about}. Recurring terms: {', '.join(keywords[:5]) or 'n/a'}.",
            sentiment=0.0,
        ),
        "keywords",
    )
