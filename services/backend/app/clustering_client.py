"""HTTP client for the social-listening clustering service (its own microservice and database)."""
from __future__ import annotations

from typing import Any

import httpx

from .config import get_settings


def _client(timeout: float = 60) -> httpx.Client:
    return httpx.Client(base_url=get_settings().clustering_url, timeout=timeout)


def get(path: str, params: dict[str, Any] | None = None) -> Any:
    with _client() as c:
        r = c.get(path, params={k: v for k, v in (params or {}).items() if v not in (None, "")})
        r.raise_for_status()
        return r.json()


def post(path: str, payload: dict[str, Any] | None = None) -> Any:
    with _client() as c:
        r = c.post(path, json=payload or {})
        r.raise_for_status()
        return r.json()
