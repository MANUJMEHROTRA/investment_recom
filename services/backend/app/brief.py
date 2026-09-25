"""Assemble the context the agent needs (candidates, holdings, sectors, USD/INR),
call the agent, and persist the brief and the articles it read."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import agent_client, analytics_client
from .config import SECTOR_ETFS, get_settings
from .models import DailyBrief, DailyPrice, Holding, NewsArticle, RecommendationRun
from .pipeline import latest_market_date, load_series
from .serializers import rec_dict, ticker_map

BUYABLE = ("Strong Buy", "Buy")


# ---------------------------------------------------------------- USD / INR

def fx_rate_on(session: Session, d: date | None = None) -> float | None:
    q = select(DailyPrice.close).where(DailyPrice.symbol == get_settings().fx_symbol)
    if d:
        q = q.where(DailyPrice.date <= d)
    return session.scalar(q.order_by(DailyPrice.date.desc()).limit(1))


def fx_context(session: Session) -> dict[str, Any]:
    s = get_settings()
    end = latest_market_date(session) or date.today()
    series = load_series(session, [s.fx_symbol], end + timedelta(days=5), calendar_days=800).get(s.fx_symbol)
    if not series or len(series["dates"]) < 30:
        return {}
    stats = analytics_client.fx(series)
    stats["markup_pct"] = s.fx_markup_pct
    stats["pair"] = "USD/INR"
    return stats


# ---------------------------------------------------------------- holdings

def holdings_view(session: Session, fx_now: float | None) -> list[dict[str, Any]]:
    names = ticker_map(session)
    out = []
    for h in session.scalars(select(Holding).order_by(Holding.symbol)):
        price = session.scalar(
            select(DailyPrice.close).where(DailyPrice.symbol == h.symbol).order_by(DailyPrice.date.desc()).limit(1)
        )
        buy_fx = h.buy_fx_rate or (fx_rate_on(session, h.buy_date) if h.buy_date else None) or fx_now
        cost_usd = h.quantity * h.avg_cost
        value_usd = h.quantity * price if price else None
        cost_inr = cost_usd * buy_fx if buy_fx else None
        value_inr = value_usd * fx_now if value_usd and fx_now else None
        t = names.get(h.symbol)
        out.append(
            {
                "id": h.id,
                "symbol": h.symbol,
                "name": t.name if t else None,
                "sector": t.sector if t else None,
                "quantity": h.quantity,
                "avg_cost": h.avg_cost,
                "buy_date": h.buy_date.isoformat() if h.buy_date else None,
                "buy_fx_rate": buy_fx,
                "buy_fx_is_estimate": h.buy_fx_rate is None,
                "notes": h.notes,
                "price": price,
                "cost_usd": cost_usd,
                "value_usd": value_usd,
                "pnl_usd": value_usd - cost_usd if value_usd is not None else None,
                "pnl_pct": value_usd / cost_usd - 1 if value_usd and cost_usd else None,
                "cost_inr": cost_inr,
                "value_inr": value_inr,
                "pnl_inr": value_inr - cost_inr if value_inr and cost_inr else None,
                "pnl_inr_pct": value_inr / cost_inr - 1 if value_inr and cost_inr else None,
                # How much of the INR result came purely from the currency move.
                "fx_gain_inr": cost_usd * (fx_now - buy_fx) if fx_now and buy_fx else None,
            }
        )
    return out


def exit_signals(session: Session, run: RecommendationRun, holdings: list[dict[str, Any]]) -> dict[str, dict]:
    if not holdings:
        return {}
    symbols = sorted({h["symbol"] for h in holdings})
    names = ticker_map(session)
    recs = {r.symbol: rec_dict(r, names) for r in run.recommendations if r.symbol in symbols}
    rows = analytics_client.exits(
        {
            "holdings": [{k: h[k] for k in ("symbol", "quantity", "avg_cost", "buy_date")} for h in holdings],
            "series": load_series(session, symbols, run.run_date, calendar_days=800),
            "analysis": recs,
        }
    )
    return {r["symbol"]: r for r in rows}


# ---------------------------------------------------------------- sectors & candidates

def sector_context(session: Session, run: RecommendationRun) -> list[dict[str, Any]]:
    s = get_settings()
    names = ticker_map(session)
    stocks = []
    for r in run.recommendations:
        t = names.get(r.symbol)
        if not t or t.quote_type == "ETF" or not t.sector:
            continue
        sma50 = (r.metrics or {}).get("sma50")
        stocks.append({"symbol": r.symbol, "sector": t.sector, "score": r.score, "rating": r.rating, "above_sma50": (r.price > sma50) if sma50 else None})
    symbols = [s.benchmark, *SECTOR_ETFS.values()]
    return analytics_client.sectors(
        {
            "as_of": run.run_date.isoformat(),
            "benchmark": s.benchmark,
            "sector_etfs": SECTOR_ETFS,
            "series": load_series(session, symbols, run.run_date, calendar_days=200),
            "stocks": stocks,
        }
    )


def candidates(session: Session, run: RecommendationRun) -> list[dict[str, Any]]:
    names = ticker_map(session)
    buyable = [r for r in run.recommendations if r.rating in BUYABLE]
    return [rec_dict(r, names) for r in buyable[: get_settings().brief_candidates]]


# ---------------------------------------------------------------- orchestration

def build_and_store(session: Session, run: RecommendationRun, brief_date: date | None = None) -> DailyBrief:
    brief_date = brief_date or date.today()
    fx = fx_context(session)
    holdings = holdings_view(session, fx.get("rate"))
    signals = exit_signals(session, run, holdings)
    sectors = sector_context(session, run)

    payload = {
        "as_of": brief_date.isoformat(),
        "regime": run.regime,
        "fx": fx,
        "candidates": candidates(session, run),
        "holdings": [{**h, "signal": signals.get(h["symbol"], {})} for h in holdings],
        "sectors": sectors,
    }
    content = agent_client.brief(payload)
    content["run_date"] = run.run_date.isoformat()

    session.execute(delete(DailyBrief).where(DailyBrief.brief_date == brief_date))
    llm = content.get("llm", {})
    b = DailyBrief(
        brief_date=brief_date,
        run_date=run.run_date,
        llm_provider=llm.get("provider", "none"),
        llm_model=llm.get("model", ""),
        content=content,
    )
    session.add(b)
    store_articles(session, content, brief_date)
    session.commit()
    return b


def store_articles(session: Session, content: dict[str, Any], seen_on: date) -> None:
    """Keep every article the agent read (with the LLM's sentiment when it assessed one) for the stock pages."""
    assessed: dict[str, dict] = {}
    for group in ("picks", "exits"):
        for item in content.get(group, []):
            for a in item.get("articles") or []:
                assessed[a["id"]] = a
    existing = {(i, t) for i, t in session.execute(select(NewsArticle.id, NewsArticle.topic))}
    for a in content.get("articles", []):
        if (a["id"], a["topic"]) in existing:
            continue
        best = assessed.get(a["id"], a)
        session.add(
            NewsArticle(
                id=a["id"], topic=a["topic"], source_api=a["source_api"], publisher=a["publisher"][:120], title=a["title"][:500],
                summary=(a.get("summary") or "")[:2000], url=a["url"][:1000], kind=a.get("kind", "news"),
                published_at=datetime.fromisoformat(a["published_at"]).astimezone(timezone.utc),
                sentiment=best.get("sentiment"), sentiment_method=best.get("sentiment_method"), takeaway=best.get("takeaway"),
                first_seen=seen_on,
            )
        )
        existing.add((a["id"], a["topic"]))


def latest_brief_date(session: Session) -> date | None:
    return session.scalar(select(func.max(DailyBrief.brief_date)))
