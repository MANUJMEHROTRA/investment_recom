"""HTTP client for the news & reasoning agent service."""
from __future__ import annotations

from typing import Any

import httpx

from .config import get_settings


def brief(payload: dict[str, Any]) -> dict[str, Any]:
    # A local 7B model reading ~20 stocks' news can take several minutes.
    with httpx.Client(base_url=get_settings().agent_url, timeout=httpx.Timeout(3600, connect=10)) as c:
        resp = c.post("/brief", json=payload)
        resp.raise_for_status()
        return resp.json()


def health() -> dict[str, Any]:
    with httpx.Client(base_url=get_settings().agent_url, timeout=10) as c:
        resp = c.get("/health")
        resp.raise_for_status()
        return resp.json()
