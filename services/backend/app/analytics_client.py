"""Thin HTTP client for the analytics service."""
from __future__ import annotations

from typing import Any

import httpx

from .config import get_settings


def _client() -> httpx.Client:
    return httpx.Client(base_url=get_settings().analytics_url, timeout=180)


def _post(path: str, payload: dict[str, Any]) -> Any:
    with _client() as c:
        resp = c.post(path, json=payload)
        resp.raise_for_status()
        return resp.json()


def _get(path: str) -> Any:
    with _client() as c:
        resp = c.get(path)
        resp.raise_for_status()
        return resp.json()


def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    return _post("/analyze", payload)


def indicators(series: dict[str, Any]) -> dict[str, Any]:
    return _post("/indicators", {"series": series})


def performance(payload: dict[str, Any]) -> dict[str, Any]:
    return _post("/performance", payload)


def methodology() -> dict[str, Any]:
    return _get("/methodology")


def health() -> dict[str, Any]:
    return _get("/health")


def sectors(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return _post("/sectors", payload)


def exits(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return _post("/exits", payload)


def fx(series: dict[str, Any]) -> dict[str, Any]:
    return _post("/fx", {"series": series})


def strategy(payload: dict[str, Any]) -> dict[str, Any]:
    return _post("/strategy", payload)
