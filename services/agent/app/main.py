"""Agent service: a LangGraph workflow that reads the news around the day's candidates,
holdings and sectors, and writes an evidence-backed morning brief."""
from __future__ import annotations

import logging

from fastapi import FastAPI

from .config import get_settings
from .graph import run_brief
from .llm import get_llm
from .schemas import BriefRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = FastAPI(title="News & Reasoning Agent", version="1.0.0")


@app.get("/health")
def health() -> dict:
    s = get_settings()
    llm = get_llm()
    return {
        "status": "ok",
        "llm_provider": llm.name,
        "llm_model": llm.model,
        "requested_provider": s.llm_provider,
        "news_sources": {"yahoo": True, "sec_edgar": True, "finnhub": bool(s.finnhub_api_key)},
    }


@app.post("/brief")
def brief(req: BriefRequest) -> dict:
    return run_brief(req)
