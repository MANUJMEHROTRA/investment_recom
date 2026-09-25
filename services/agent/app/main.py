"""Agent service: a LangGraph workflow that reads the news around the day's candidates,
holdings and sectors, and writes an evidence-backed morning brief."""
from __future__ import annotations

import logging

from fastapi import FastAPI

from .config import get_settings
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from pydantic import BaseModel

from .graph import SECTOR_TERMS, gather_news, run_brief
from .news.trust import name_terms
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


class CollectSymbol(BaseModel):
    symbol: str
    name: str | None = None


class CollectRequest(BaseModel):
    as_of: date
    symbols: list[CollectSymbol]
    sectors: dict[str, str] = {}  # sector name -> ETF
    include_macro: bool = True


@app.post("/collect")
def collect(req: CollectRequest) -> dict:
    """News sweep without the LLM: same sources, filters and VADER scoring as the brief,
    for every tracked stock. Feeds the social-listening clustering service."""
    tasks = [{"kind": "company", "topic": s.symbol, "terms": name_terms(s.symbol, s.name)} for s in req.symbols]
    tasks += [{"kind": "sector", "topic": f"sector:{n}", "etf": etf, "terms": SECTOR_TERMS.get(n, [n])} for n, etf in req.sectors.items()]
    if req.include_macro:
        tasks.append({"kind": "macro", "topic": "macro", "terms": []})
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda t: gather_news({"task": t, "as_of": req.as_of.isoformat()}), tasks))
    articles = [a for r in results for group in r.get("articles", {}).values() for a in group]
    errors = [e for r in results for e in r.get("errors", [])]
    return {"articles": articles, "errors": errors}
