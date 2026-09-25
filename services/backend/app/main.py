"""Backend API: owns the database and market-data ingestion, delegates maths to the
analytics service, and serves everything the dashboard needs."""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from . import agent_client, analytics_client, brief as brief_mod, clustering_client, market_data, pipeline
from .config import get_settings
from .db import get_session, init_db
from .models import DailyBrief, DailyPrice, Holding, NewsArticle, Recommendation, RecommendationRun, Ticker
from .serializers import rec_dict, run_dict, ticker_map

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("backend")
settings = get_settings()
scheduler = BackgroundScheduler(timezone="America/New_York")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    scheduler.add_job(
        pipeline.run_daily,
        "cron",
        day_of_week="mon-fri",
        hour=settings.schedule_hour,
        minute=settings.schedule_minute,
        kwargs={"source": "scheduled"},
        id="daily",
        replace_existing=True,
        misfire_grace_time=6 * 3600,
    )
    scheduler.add_job(
        pipeline.morning_brief,
        "cron",
        day_of_week="mon-fri",
        hour=settings.brief_hour,
        minute=settings.brief_minute,
        kwargs={"source": "premarket"},
        id="brief",
        replace_existing=True,
        misfire_grace_time=4 * 3600,
    )
    scheduler.start()
    threading.Thread(target=pipeline.startup, daemon=True).start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Investment Recommender API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def private_network_access(request: Request, call_next):
    """Lets the GitHub Pages dashboard (a public origin) call this API on localhost in Chrome."""
    response = await call_next(request)
    if request.headers.get("access-control-request-private-network"):
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


# ---------------------------------------------------------------- health & status

@app.get("/api/health")
def health(session: Session = Depends(get_session)) -> dict[str, Any]:
    db_ok = session.execute(text("SELECT 1")).scalar() == 1
    try:
        analytics = analytics_client.health()
    except Exception as exc:  # noqa: BLE001
        analytics = {"status": "down", "error": str(exc)}
    try:
        agent = agent_client.health()
    except Exception as exc:  # noqa: BLE001
        agent = {"status": "down", "error": str(exc)}
    prices = session.scalar(select(func.count()).select_from(DailyPrice)) or 0
    return {
        "status": "ok" if db_ok and analytics.get("status") == "ok" else "degraded",
        "database": "ok" if db_ok else "down",
        "analytics": analytics,
        "agent": agent,
        "last_brief_date": (b.isoformat() if (b := brief_mod.latest_brief_date(session)) else None),
        "price_rows": prices,
        "last_market_date": (d.isoformat() if (d := pipeline.latest_market_date(session)) else None),
        "job": pipeline.status,
        "next_scheduled_run": str(scheduler.get_job("daily").next_run_time) if scheduler.get_job("daily") else None,
        "next_brief": str(scheduler.get_job("brief").next_run_time) if scheduler.get_job("brief") else None,
    }


@app.get("/api/universe")
def universe(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    tickers = ticker_map(session)
    symbols = dict.fromkeys([*settings.universe_list, *pipeline.holding_symbols(session), settings.benchmark])
    return [
        {"symbol": s, "name": tickers[s].name if s in tickers else ("SPDR S&P 500 ETF" if s == settings.benchmark else None),
         "sector": tickers[s].sector if s in tickers else None}
        for s in symbols
    ]


# ---------------------------------------------------------------- recommendations

@app.get("/api/runs")
def list_runs(limit: int = Query(365, le=2000), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    runs = session.scalars(select(RecommendationRun).order_by(RecommendationRun.run_date.desc()).limit(limit))
    names = ticker_map(session)
    out = []
    for run in runs:
        top = [r for r in run.recommendations if r.target_weight][:5]
        d = run_dict(run, session, include_recs=False)
        d["top_picks"] = [r.symbol for r in top]
        d["top_pick_names"] = {r.symbol: names[r.symbol].name for r in top if r.symbol in names}
        d["buy_count"] = sum(r.rating in ("Strong Buy", "Buy") for r in run.recommendations)
        out.append(d)
    return out


@app.get("/api/recommendations/latest")
def latest(session: Session = Depends(get_session)) -> dict[str, Any]:
    run = session.scalar(select(RecommendationRun).order_by(RecommendationRun.run_date.desc()).limit(1))
    if run is None:
        raise HTTPException(404, "No recommendations yet - the first run may still be in progress.")
    return run_dict(run, session)


@app.get("/api/recommendations/{run_date}")
def by_date(run_date: date, session: Session = Depends(get_session)) -> dict[str, Any]:
    run = session.scalar(select(RecommendationRun).where(RecommendationRun.run_date == run_date))
    if run is None:
        raise HTTPException(404, f"No run stored for {run_date}")
    return run_dict(run, session)


@app.post("/api/runs", status_code=202)
def trigger_run(background: BackgroundTasks) -> dict[str, Any]:
    if pipeline.status["running"]:
        raise HTTPException(409, "A job is already running")
    background.add_task(pipeline.run_daily, "manual")
    return {"accepted": True}


@app.post("/api/runs/backfill", status_code=202)
def trigger_backfill(background: BackgroundTasks, days: int = Query(60, ge=1, le=500)) -> dict[str, Any]:
    if pipeline.status["running"]:
        raise HTTPException(409, "A job is already running")
    background.add_task(pipeline.backfill, days)
    return {"accepted": True, "days": days}


# ---------------------------------------------------------------- stocks

@app.get("/api/stocks/{symbol}")
def stock(symbol: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    symbol = symbol.upper()
    last = pipeline.latest_market_date(session)
    series = pipeline.load_series(session, [symbol], last or date.today(), calendar_days=730).get(symbol)
    if not series:
        raise HTTPException(404, f"No price data for {symbol}")
    t = session.get(Ticker, symbol)
    history = session.execute(
        select(Recommendation.run_date, Recommendation.score, Recommendation.rating, Recommendation.rank)
        .where(Recommendation.symbol == symbol)
        .order_by(Recommendation.run_date)
    ).all()
    latest_rec = session.scalar(
        select(Recommendation).where(Recommendation.symbol == symbol).order_by(Recommendation.run_date.desc()).limit(1)
    )
    return {
        "symbol": symbol,
        "info": {
            k: getattr(t, k) for k in ("name", "sector", "industry", "quote_type", "market_cap", "forward_pe", "trailing_pe", "revenue_growth", "profit_margin", "debt_to_equity")
        } if t else {},
        "indicators": analytics_client.indicators(series),
        "latest": rec_dict(latest_rec, ticker_map(session)) | {"run_date": latest_rec.run_date.isoformat()} if latest_rec else None,
        "news": [
            {
                "id": a.id, "publisher": a.publisher, "title": a.title, "url": a.url, "kind": a.kind,
                "published_at": a.published_at.isoformat(), "sentiment": a.sentiment,
                "sentiment_method": a.sentiment_method, "takeaway": a.takeaway,
            }
            for a in session.scalars(
                select(NewsArticle).where(NewsArticle.topic == symbol).order_by(NewsArticle.published_at.desc()).limit(25)
            )
        ],
        "history": [{"run_date": d.isoformat(), "score": s, "rating": r, "rank": k} for d, s, r, k in history],
    }


_quote_cache: dict[str, Any] = {"at": 0.0, "key": None, "data": {}}


@app.get("/api/quotes")
def quotes(symbols: str | None = None, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Near-real-time (Yahoo-delayed) quotes; defaults to today's picks plus SPY and VIX."""
    if symbols:
        wanted = [s.strip().upper() for s in symbols.split(",") if s.strip()][:50]
    else:
        run = session.scalar(select(RecommendationRun).order_by(RecommendationRun.run_date.desc()).limit(1))
        picks = [r.symbol for r in run.recommendations[: settings.top_n]] if run else []
        wanted = [settings.benchmark, settings.volatility_index, *picks]
    key = ",".join(sorted(wanted))
    if _quote_cache["key"] == key and time.time() - _quote_cache["at"] < settings.quote_cache_seconds:
        return _quote_cache["data"]
    try:
        data = {"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "quotes": market_data.fetch_quotes(wanted)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"quote provider error: {exc}") from exc
    _quote_cache.update(at=time.time(), key=key, data=data)
    return data


# ---------------------------------------------------------------- analysis passthroughs

@app.get("/api/performance")
def performance(days: int = Query(90, ge=5, le=1000), session: Session = Depends(get_session)) -> dict[str, Any]:
    since = date.today() - timedelta(days=days)
    recs = session.execute(
        select(Recommendation.run_date, Recommendation.symbol, Recommendation.rating, Recommendation.score, Recommendation.rank)
        .where(Recommendation.run_date >= since)
    ).all()
    if not recs:
        return {"horizons": [], "summary": [], "rows": []}
    symbols = sorted({r.symbol for r in recs} | {settings.benchmark})
    prices = session.execute(
        select(DailyPrice.symbol, DailyPrice.date, DailyPrice.close).where(DailyPrice.symbol.in_(symbols), DailyPrice.date >= since)
    ).all()
    closes: dict[str, dict[str, float]] = {}
    for sym, d, c in prices:
        closes.setdefault(sym, {})[d.isoformat()] = c
    result = analytics_client.performance(
        {
            "recommendations": [{"run_date": d.isoformat(), "symbol": s, "rating": r, "score": sc} for d, s, r, sc, _ in recs],
            "closes": closes,
            "benchmark": settings.benchmark,
        }
    )
    top = {(d.isoformat(), s) for d, s, r, _, k in recs if k <= settings.top_n and r in ("Strong Buy", "Buy")}
    names = ticker_map(session)
    for row in result["rows"]:
        row["name"] = names[row["symbol"]].name if row["symbol"] in names else None
    result["rows"] = sorted(
        (row for row in result["rows"] if (row["run_date"], row["symbol"]) in top),
        key=lambda row: (row["run_date"], -row["score"]),
        reverse=True,
    )
    return result


@app.get("/api/methodology")
def methodology() -> dict[str, Any]:
    m = analytics_client.methodology()
    m["universe"] = settings.universe_list
    m["benchmark"] = settings.benchmark
    m["data_source"] = "Yahoo Finance via the open-source yfinance library (free, no API key, quotes delayed up to ~15 min)."
    m["schedule"] = f"Weekdays at {settings.schedule_hour:02d}:{settings.schedule_minute:02d} America/New_York"
    return m


# ---------------------------------------------------------------- USD / INR

@app.get("/api/fx")
def fx(session: Session = Depends(get_session)) -> dict[str, Any]:
    stats = brief_mod.fx_context(session)
    if not stats:
        raise HTTPException(404, "No USD/INR data yet - it downloads with the next run.")
    return stats


# ---------------------------------------------------------------- morning briefs

@app.get("/api/briefs")
def list_briefs(limit: int = Query(60, le=500), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    rows = session.scalars(select(DailyBrief).order_by(DailyBrief.brief_date.desc()).limit(limit))
    out = []
    for b in rows:
        c = b.content
        out.append(
            {
                "brief_date": b.brief_date.isoformat(),
                "run_date": b.run_date.isoformat(),
                "llm": f"{b.llm_provider}:{b.llm_model}",
                "headline": (c.get("market") or {}).get("headline"),
                "strong_picks": [p["symbol"] for p in c.get("picks", []) if p["verdict"] == "Strong pick"],
                "articles": c.get("stats", {}).get("articles", 0),
            }
        )
    return out


@app.get("/api/briefs/latest")
def latest_brief(session: Session = Depends(get_session)) -> dict[str, Any]:
    b = session.scalar(select(DailyBrief).order_by(DailyBrief.brief_date.desc()).limit(1))
    if b is None:
        raise HTTPException(404, "No morning brief yet - run one from this page or wait for the pre-market job.")
    return {"brief_date": b.brief_date.isoformat(), **b.content}


@app.get("/api/briefs/{brief_date}")
def brief_by_date(brief_date: date, session: Session = Depends(get_session)) -> dict[str, Any]:
    b = session.get(DailyBrief, brief_date)
    if b is None:
        raise HTTPException(404, f"No brief stored for {brief_date}")
    return {"brief_date": b.brief_date.isoformat(), **b.content}


@app.post("/api/briefs", status_code=202)
def trigger_brief(background: BackgroundTasks) -> dict[str, Any]:
    if pipeline.status["running"]:
        raise HTTPException(409, "A job is already running")
    background.add_task(pipeline.morning_brief, "manual")
    return {"accepted": True}


# ---------------------------------------------------------------- holdings

class HoldingIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    quantity: float = Field(gt=0)
    avg_cost: float = Field(gt=0, description="USD per share")
    buy_date: date | None = None
    buy_fx_rate: float | None = Field(default=None, gt=0, description="INR per USD when you bought; looked up if blank")
    notes: str | None = Field(default=None, max_length=500)


@app.get("/api/holdings")
def list_holdings(session: Session = Depends(get_session)) -> dict[str, Any]:
    fx_now = brief_mod.fx_rate_on(session)
    rows = brief_mod.holdings_view(session, fx_now)
    advice: dict[str, Any] = {}
    b = session.scalar(select(DailyBrief).order_by(DailyBrief.brief_date.desc()).limit(1))
    if b is not None:
        advice = {e["symbol"]: e | {"brief_date": b.brief_date.isoformat()} for e in b.content.get("exits", [])}
    totals = {
        k: sum(r[k] for r in rows if r[k] is not None)
        for k in ("cost_usd", "value_usd", "pnl_usd", "cost_inr", "value_inr", "pnl_inr", "fx_gain_inr")
    }
    return {"fx_rate": fx_now, "holdings": [r | {"advice": advice.get(r["symbol"])} for r in rows], "totals": totals}


@app.post("/api/holdings", status_code=201)
def add_holding(body: HoldingIn, session: Session = Depends(get_session)) -> dict[str, Any]:
    h = Holding(**body.model_dump() | {"symbol": body.symbol.strip().upper()})
    session.add(h)
    session.flush()
    return {"id": h.id}


@app.put("/api/holdings/{holding_id}")
def update_holding(holding_id: int, body: HoldingIn, session: Session = Depends(get_session)) -> dict[str, Any]:
    h = session.get(Holding, holding_id)
    if h is None:
        raise HTTPException(404, "Holding not found")
    for k, v in (body.model_dump() | {"symbol": body.symbol.strip().upper()}).items():
        setattr(h, k, v)
    return {"id": h.id}


@app.delete("/api/holdings/{holding_id}", status_code=204)
def delete_holding(holding_id: int, session: Session = Depends(get_session)) -> None:
    h = session.get(Holding, holding_id)
    if h is None:
        raise HTTPException(404, "Holding not found")
    session.delete(h)


# ---------------------------------------------------------------- news feed & social listening

@app.get("/api/news/feed")
def news_feed(after_pk: int = 0, limit: int = Query(2000, le=5000), session: Session = Depends(get_session)) -> dict[str, Any]:
    """Incremental feed of stored articles for the clustering service (cursor = pk)."""
    names = ticker_map(session)
    rows = session.scalars(select(NewsArticle).where(NewsArticle.pk > after_pk).order_by(NewsArticle.pk).limit(limit)).all()
    items = []
    for a in rows:
        t = names.get(a.topic)
        items.append(
            {
                "pk": a.pk, "id": a.id, "topic": a.topic, "source_api": a.source_api, "publisher": a.publisher,
                "title": a.title, "summary": a.summary, "url": a.url, "kind": a.kind,
                "published_at": a.published_at.isoformat(), "sentiment": a.sentiment, "sentiment_method": a.sentiment_method,
                "symbol_name": t.name if t else None,
                "sector": (t.sector if t else None) or (a.topic.split(":", 1)[1] if a.topic.startswith("sector:") else None),
            }
        )
    return {"items": items, "next_after_pk": rows[-1].pk if rows else after_pk}


def _social(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Clustering service unavailable: {exc}") from exc


@app.get("/api/social/map")
def social_map() -> Any:
    return _social(clustering_client.get, "/map")


@app.get("/api/social/status")
def social_status() -> Any:
    return _social(clustering_client.get, "/status")


@app.post("/api/social/run", status_code=202)
def social_run() -> Any:
    return _social(clustering_client.post, "/run")


@app.post("/api/news/sweep", status_code=202)
def trigger_sweep(background: BackgroundTasks) -> dict[str, Any]:
    if pipeline.status["running"]:
        raise HTTPException(409, "A job is already running")
    background.add_task(pipeline.news_sweep)
    return {"accepted": True}


# ---------------------------------------------------------------- strategy backtest

@app.get("/api/strategy")
def strategy(
    sizes: str = "5,10,20,30",
    rebalance_every: int = Query(5, ge=1, le=60),
    selection: str = Query("ranked", pattern="^(ranked|buyable)$"),
    fx_markup_pct: float = Query(1.0, ge=0, le=10),
    trade_cost_pct: float = Query(0.0, ge=0, le=5),
    fx_mode: str = Query("actual", pattern="^(actual|assumed)$"),
    assumed_fx_annual_pct: float = Query(1.0, ge=-20, le=20),
    days: int = Query(365, ge=10, le=2000),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Replays every stored recommendation day: buy the top-N at the next open, equal weight."""
    n = sorted({int(x) for x in sizes.split(",") if x.strip().isdigit() and 0 < int(x) <= 100}) or [10]
    since = date.today() - timedelta(days=days)
    runs = session.scalars(select(RecommendationRun).where(RecommendationRun.run_date >= since).order_by(RecommendationRun.run_date)).all()
    if not runs:
        raise HTTPException(404, "No stored recommendations in this window yet.")
    top = max(n)
    picks, symbols = [], {settings.benchmark}
    for run in runs:
        ranked = [r.symbol for r in run.recommendations]
        buyable = [r.symbol for r in run.recommendations if r.rating in ("Strong Buy", "Buy")]
        symbols.update(ranked[: top + 1])
        symbols.update(buyable[: top + 1])
        picks.append({"run_date": run.run_date.isoformat(), "source": run.source, "ranked": ranked[: top + 1], "buyable": buyable[: top + 1]})
    rows = session.execute(
        select(DailyPrice.symbol, DailyPrice.date, DailyPrice.open, DailyPrice.close)
        .where(DailyPrice.symbol.in_(symbols | {settings.fx_symbol}), DailyPrice.date >= runs[0].run_date)
        .order_by(DailyPrice.symbol, DailyPrice.date)
    ).all()
    prices: dict[str, dict[str, list]] = {}
    for sym, d, o, c in rows:
        p = prices.setdefault(sym, {"dates": [], "open": [], "close": []})
        p["dates"].append(d.isoformat())
        p["open"].append(o)
        p["close"].append(c)
    fx = prices.pop(settings.fx_symbol, None)
    result = analytics_client.strategy(
        {
            "runs": picks, "prices": prices, "fx": fx, "benchmark": settings.benchmark, "sizes": n,
            "rebalance_every": rebalance_every, "selection": selection, "fx_markup_pct": fx_markup_pct,
            "trade_cost_pct": trade_cost_pct, "fx_mode": fx_mode, "assumed_fx_annual_pct": assumed_fx_annual_pct,
        }
    )
    result["names"] = {s: t.name for s, t in ticker_map(session).items() if s in symbols}
    result["recommendation_days"] = len(runs)
    result["backfilled_days"] = sum(r.source == "backfill" for r in runs)
    return result
