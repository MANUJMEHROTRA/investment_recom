"""Daily pipeline: ingest prices -> ask the analytics service -> store the day's recommendations."""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from . import analytics_client, market_data
from .config import get_settings
from .db import session_scope
from .models import DailyPrice, Holding, Recommendation, RecommendationRun, Ticker

log = logging.getLogger(__name__)

LOOKBACK_CALENDAR_DAYS = 560  # ~380 trading days: enough for 12-1 momentum and a 200-day average

_lock = threading.Lock()
status: dict[str, Any] = {"running": False, "task": None, "started_at": None, "finished_at": None, "error": None, "message": "idle"}


def _set(**kw: Any) -> None:
    status.update(kw)


# ---------------------------------------------------------------- ingestion

def upsert_prices(session: Session, data: dict[str, pd.DataFrame]) -> int:
    rows = [
        {
            "symbol": sym,
            "date": ts.date(),
            "open": _num(r.get("open")),
            "high": _num(r.get("high")),
            "low": _num(r.get("low")),
            "close": float(r["close"]),
            "volume": int(r["volume"]) if pd.notna(r.get("volume")) else None,
        }
        for sym, df in data.items()
        for ts, r in df.iterrows()
    ]
    if not rows:
        return 0
    insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
    for i in range(0, len(rows), 5000):
        stmt = insert(DailyPrice).values(rows[i : i + 5000])
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "date"],
            set_={c: stmt.excluded[c] for c in ("open", "high", "low", "close", "volume")},
        )
        session.execute(stmt)
    return len(rows)


def holding_symbols(session: Session) -> list[str]:
    return sorted({h.symbol for h in session.scalars(select(Holding))})


def tracked_symbols(session: Session) -> list[str]:
    """Everything we download prices for: benchmark, VIX, USD/INR, sector ETFs, universe and your holdings."""
    return list(dict.fromkeys([*get_settings().all_symbols, *holding_symbols(session)]))


def analysable_symbols(session: Session) -> list[str]:
    fx = get_settings().fx_symbol
    return [s for s in tracked_symbols(session) if s != fx]


def refresh_prices(session: Session) -> int:
    s = get_settings()
    symbols = tracked_symbols(session)
    _set(message=f"downloading {len(symbols)} price histories from Yahoo Finance")
    n = upsert_prices(session, market_data.download_history(symbols, s.history_period))
    session.commit()
    return n


def refresh_fundamentals(session: Session, force: bool = False) -> int:
    s = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(days=s.fundamentals_max_age_days)
    existing = {t.symbol: t for t in session.scalars(select(Ticker))}
    updated = 0
    for sym in dict.fromkeys([*s.universe_list, *holding_symbols(session)]):
        t = existing.get(sym) or Ticker(symbol=sym)
        fresh = t.fundamentals_updated_at and t.fundamentals_updated_at.replace(tzinfo=timezone.utc) > cutoff
        if fresh and not force:
            continue
        _set(message=f"fetching fundamentals for {sym}")
        try:
            for k, v in market_data.fetch_fundamentals(sym).items():
                setattr(t, k, v)
            t.fundamentals_updated_at = datetime.now(timezone.utc)
            session.add(t)
            session.commit()
            updated += 1
        except Exception:  # noqa: BLE001
            session.rollback()
            log.warning("fundamentals failed for %s", sym, exc_info=True)
        time.sleep(0.3)  # be polite to a free endpoint
    return updated


# ---------------------------------------------------------------- analysis

def load_series(session: Session, symbols: list[str], end: date, calendar_days: int = LOOKBACK_CALENDAR_DAYS) -> dict[str, dict[str, list]]:
    start = end - timedelta(days=calendar_days)
    rows = session.execute(
        select(DailyPrice)
        .where(DailyPrice.symbol.in_(symbols), DailyPrice.date >= start, DailyPrice.date <= end)
        .order_by(DailyPrice.symbol, DailyPrice.date)
    ).scalars()
    out: dict[str, dict[str, list]] = {}
    for p in rows:
        s = out.setdefault(p.symbol, {"dates": [], "open": [], "high": [], "low": [], "close": [], "volume": []})
        s["dates"].append(p.date.isoformat())
        s["open"].append(p.open)
        s["high"].append(p.high)
        s["low"].append(p.low)
        s["close"].append(p.close)
        s["volume"].append(p.volume)
    return out


def latest_market_date(session: Session, on_or_before: date | None = None) -> date | None:
    q = select(func.max(DailyPrice.date)).where(DailyPrice.symbol == get_settings().benchmark)
    if on_or_before:
        q = q.where(DailyPrice.date <= on_or_before)
    return session.scalar(q)


def fundamentals_payload(session: Session) -> dict[str, dict[str, Any]]:
    fields = ("name", "sector", "forward_pe", "trailing_pe", "revenue_growth", "profit_margin", "debt_to_equity", "market_cap")
    return {t.symbol: {f: market_data._finite(getattr(t, f)) for f in fields} for t in session.scalars(select(Ticker))}


def analyze_date(session: Session, as_of: date | None, source: str, include_fundamentals: bool = True) -> RecommendationRun | None:
    """Analyse the universe using only data up to `as_of` and store the result."""
    s = get_settings()
    run_date = latest_market_date(session, as_of)
    if run_date is None:
        raise RuntimeError("no benchmark price data - refresh prices first")

    existing = session.scalar(select(RecommendationRun).where(RecommendationRun.run_date == run_date))
    if existing is not None and source == "backfill":
        return None  # never overwrite a real run (or a previous backfill) with a backfill

    payload = {
        "as_of": run_date.isoformat(),
        "series": load_series(session, analysable_symbols(session), run_date),
        "benchmark": s.benchmark,
        "volatility_index": s.volatility_index,
        # Fundamentals are "today's" snapshot, so historical backfills omit them to avoid look-ahead bias.
        "fundamentals": fundamentals_payload(session) if include_fundamentals else {},
        "top_n": s.top_n,
    }
    result = analytics_client.analyze(payload)

    if existing is not None:
        session.delete(existing)
        session.flush()

    regime = result["regime"]
    run = RecommendationRun(
        run_date=run_date,
        source=source,
        model_version=result["model_version"],
        regime_label=regime["label"],
        equity_exposure=regime["equity_exposure"],
        regime=regime,
        universe_size=len(result["recommendations"]),
        skipped=result["skipped"],
    )
    for r in result["recommendations"]:
        run.recommendations.append(
            Recommendation(
                run_date=run_date,
                symbol=r["symbol"],
                rank=r["rank"],
                score=r["score"],
                rating=r["rating"],
                price=r["price"],
                stop_loss=r["stop_loss"],
                target_weight=r["target_weight"],
                components=r["components"],
                metrics=r["metrics"],
                reasons=r["reasons"],
                cautions=r["cautions"],
            )
        )
    session.add(run)
    session.commit()
    return run


# ---------------------------------------------------------------- jobs

def _job(task: str, fn) -> None:
    if not _lock.acquire(blocking=False):
        log.info("skipping %s: another job is running", task)
        return
    _set(running=True, task=task, started_at=_now(), error=None, message="starting")
    try:
        fn()
        _set(message="done")
    except Exception as exc:  # noqa: BLE001
        log.exception("%s failed", task)
        _set(error=f"{exc.__class__.__name__}: {exc}", message="failed")
    finally:
        _set(running=False, finished_at=_now())
        _lock.release()


def run_daily(source: str = "scheduled") -> None:
    def work() -> None:
        with session_scope() as session:
            refresh_prices(session)
            if get_settings().fetch_fundamentals:
                refresh_fundamentals(session)
            _set(message="scoring the universe")
            run = analyze_date(session, date.today(), source)
            log.info("stored %s recommendations for %s", len(run.recommendations), run.run_date)

    _job(f"daily ({source})", work)


def morning_brief(source: str = "scheduled") -> None:
    """Pre-market: refresh data, re-score, then have the agent read the news and write the brief."""
    from . import brief  # local import: brief imports this module

    def work() -> None:
        with session_scope() as session:
            refresh_prices(session)
            if get_settings().fetch_fundamentals:
                refresh_fundamentals(session)
            _set(message="scoring the universe")
            run = analyze_date(session, date.today(), source)
            _set(message="agent is reading the news and writing the brief (several minutes with a local LLM)")
            b = brief.build_and_store(session, run)
            log.info("stored brief for %s with %d picks", b.brief_date, len(b.content.get("picks", [])))
            if get_settings().news_sweep:
                _sweep(session)

    _job(f"morning brief ({source})", work)


def _sweep(session: Session) -> None:
    """Collect news for every tracked stock (no LLM), store it, then ask the clustering service to update."""
    from . import agent_client, clustering_client
    from .brief import store_articles
    from .config import SECTOR_ETFS

    names = {t.symbol: t.name for t in session.scalars(select(Ticker))}
    fx = get_settings().fx_symbol
    symbols = [{"symbol": s, "name": names.get(s)} for s in tracked_symbols(session) if not s.startswith("^") and s != fx]
    _set(message=f"news sweep: collecting articles for {len(symbols)} symbols")
    result = agent_client.collect({"as_of": date.today().isoformat(), "symbols": symbols, "sectors": SECTOR_ETFS})
    store_articles(session, {"articles": result["articles"]}, date.today())
    session.commit()
    log.info("news sweep stored up to %d articles", len(result["articles"]))
    try:
        clustering_client.post("/run")
        _set(message="news sweep done; clustering service is updating")
    except Exception:  # noqa: BLE001 - clustering is optional; the brief is already saved
        log.warning("clustering service unavailable", exc_info=True)


def news_sweep() -> None:
    def work() -> None:
        with session_scope() as session:
            _sweep(session)

    _job("news sweep", work)


def backfill(days: int, refresh: bool = True) -> None:
    """Replay the model over the last `days` trading sessions to build history immediately."""

    def work() -> None:
        with session_scope() as session:
            if refresh:
                refresh_prices(session)
            dates = session.scalars(
                select(DailyPrice.date)
                .where(DailyPrice.symbol == get_settings().benchmark)
                .order_by(DailyPrice.date.desc())
                .limit(days)
            ).all()
            for i, d in enumerate(sorted(dates), start=1):
                _set(message=f"backfilling {d} ({i}/{len(dates)})")
                analyze_date(session, d, "backfill", include_fundamentals=False)

    _job(f"backfill {days}d", work)


def startup() -> None:
    s = get_settings()
    with session_scope() as session:
        run_count = session.scalar(select(func.count(RecommendationRun.id))) or 0
        last_created = session.scalar(select(func.max(RecommendationRun.created_at)))
    # Runs are dated by market day, so compare wall-clock creation time to avoid re-running on every restart.
    stale = last_created is None or datetime.now(timezone.utc) - last_created.replace(tzinfo=last_created.tzinfo or timezone.utc) > timedelta(hours=12)
    if s.run_on_startup and stale:
        run_daily("startup")
    if run_count < 5 and s.backfill_days_on_first_start > 0:
        backfill(s.backfill_days_on_first_start, refresh=False)
    from .brief import latest_brief_date

    with session_scope() as session:
        has_brief = latest_brief_date(session) == date.today()
    if s.run_on_startup and not has_brief:
        morning_brief("startup")


def _num(v) -> float | None:
    return None if v is None or pd.isna(v) else float(v)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
