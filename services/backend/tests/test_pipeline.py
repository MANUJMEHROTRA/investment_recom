from datetime import date

import pandas as pd
import pytest
from sqlalchemy import select

from app import pipeline
from app.db import SessionLocal, engine
from app.models import Base, DailyPrice, RecommendationRun


@pytest.fixture()
def session():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    s = SessionLocal()
    yield s
    s.close()


def frame(closes: list[float], start: str = "2026-09-01") -> pd.DataFrame:
    idx = pd.bdate_range(start=start, periods=len(closes))
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes, "volume": [100] * len(closes)}, index=idx)


def fake_result(as_of: str, symbols: list[str]) -> dict:
    return {
        "as_of": as_of,
        "model_version": "test",
        "regime": {"label": "Neutral", "equity_exposure": 0.6, "summary": "", "metrics": {}},
        "skipped": {},
        "recommendations": [
            {
                "symbol": s, "rank": i + 1, "score": 70 - i, "rating": "Buy", "price": 1.0, "stop_loss": None,
                "target_weight": 0.1, "components": {}, "metrics": {}, "reasons": ["r"], "cautions": [],
            }
            for i, s in enumerate(symbols)
        ],
    }


def test_upsert_is_idempotent_and_updates(session):
    pipeline.upsert_prices(session, {"SPY": frame([1, 2, 3])})
    pipeline.upsert_prices(session, {"SPY": frame([1, 2, 30])})
    session.commit()
    rows = session.scalars(select(DailyPrice).order_by(DailyPrice.date)).all()
    assert [r.close for r in rows] == [1, 2, 30]


def test_load_series_is_columnar_and_bounded(session):
    pipeline.upsert_prices(session, {"SPY": frame([1, 2, 3, 4]), "AAPL": frame([5, 6, 7, 8])})
    session.commit()
    out = pipeline.load_series(session, ["SPY", "AAPL"], date(2026, 9, 2))
    assert out["SPY"]["close"] == [1, 2]
    assert out["AAPL"]["dates"] == ["2026-09-01", "2026-09-02"]


def test_analyze_date_stores_and_replaces_but_backfill_never_overwrites(session, monkeypatch):
    pipeline.upsert_prices(session, {"SPY": frame([1, 2, 3])})
    session.commit()
    calls = []

    def fake_analyze(payload):
        calls.append(payload)
        return fake_result(payload["as_of"], ["AAPL", "MSFT"])

    monkeypatch.setattr(pipeline.analytics_client, "analyze", fake_analyze)

    run = pipeline.analyze_date(session, date(2026, 9, 5), "manual")  # Saturday -> uses Friday's bar
    assert run.run_date == date(2026, 9, 3)
    assert [r.symbol for r in run.recommendations] == ["AAPL", "MSFT"]

    assert pipeline.analyze_date(session, date(2026, 9, 3), "backfill") is None
    assert len(calls) == 1

    pipeline.analyze_date(session, date(2026, 9, 3), "scheduled")
    runs = session.scalars(select(RecommendationRun)).all()
    assert len(runs) == 1 and runs[0].source == "scheduled"
    assert calls[-1]["fundamentals"] is not None


def test_backfill_omits_fundamentals(session, monkeypatch):
    pipeline.upsert_prices(session, {"SPY": frame([1, 2, 3])})
    session.commit()
    seen = []
    monkeypatch.setattr(
        pipeline.analytics_client, "analyze", lambda p: seen.append(p) or fake_result(p["as_of"], ["AAPL"])
    )
    pipeline.analyze_date(session, date(2026, 9, 1), "backfill", include_fundamentals=False)
    assert seen[0]["fundamentals"] == {}


def test_holdings_inr_pnl_uses_buy_date_fx(session):
    from app.brief import fx_rate_on, holdings_view
    from app.models import Holding

    pipeline.upsert_prices(session, {"AAPL": frame([100, 110, 120]), "USDINR=X": frame([80, 84, 88])})
    session.add(Holding(symbol="AAPL", quantity=10, avg_cost=100, buy_date=date(2026, 9, 1)))
    session.commit()
    fx_now = fx_rate_on(session)
    row = holdings_view(session, fx_now)[0]
    assert fx_now == 88 and row["buy_fx_rate"] == 80 and row["buy_fx_is_estimate"]
    assert row["pnl_pct"] == pytest.approx(0.20)
    assert row["pnl_inr_pct"] == pytest.approx(120 * 88 / (100 * 80) - 1)  # stock gain compounded with the rupee's fall
    assert row["fx_gain_inr"] == pytest.approx(1000 * (88 - 80))


def test_non_finite_fundamentals_are_dropped():
    from app.market_data import _finite

    assert _finite(float("inf")) is None and _finite(float("nan")) is None and _finite(12.5) == 12.5
