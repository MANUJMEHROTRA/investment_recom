from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import cap_category
from .models import Recommendation, RecommendationRun, Ticker


def ticker_map(session: Session) -> dict[str, Ticker]:
    return {t.symbol: t for t in session.scalars(select(Ticker))}


def rec_dict(r: Recommendation, names: dict[str, Ticker] | None = None) -> dict[str, Any]:
    t = (names or {}).get(r.symbol)
    return {
        "symbol": r.symbol,
        "name": t.name if t else None,
        "sector": t.sector if t else None,
        "cap_category": cap_category(t.quote_type, t.market_cap) if t else None,
        "market_cap": t.market_cap if t else None,
        "rank": r.rank,
        "score": r.score,
        "rating": r.rating,
        "price": r.price,
        "stop_loss": r.stop_loss,
        "target_weight": r.target_weight,
        "components": r.components,
        "metrics": r.metrics,
        "reasons": r.reasons,
        "cautions": r.cautions,
    }


def run_dict(run: RecommendationRun, session: Session, include_recs: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "run_date": run.run_date.isoformat(),
        "source": run.source,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "model_version": run.model_version,
        "regime": run.regime,
        "universe_size": run.universe_size,
        "skipped": run.skipped,
    }
    if include_recs:
        names = ticker_map(session)
        out["recommendations"] = [rec_dict(r, names) for r in run.recommendations]
    return out
