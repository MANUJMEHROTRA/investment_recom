from datetime import date

import pytest

from app.context import ExitRequest, FxRequest, HoldingSpec, SectorRequest, SectorStock, exit_signals, fx_stats, quadrant, sector_rotation
from tests.test_analytics import make_series


def test_quadrants():
    assert quadrant(0.05, 0.01) == "Leading"
    assert quadrant(0.05, -0.01) == "Weakening"
    assert quadrant(-0.05, 0.01) == "Improving"
    assert quadrant(-0.05, -0.01) == "Lagging"


def test_sector_rotation_ranks_outperformer_first():
    req = SectorRequest(
        as_of=date(2026, 9, 24),
        sector_etfs={"Technology": "XLK", "Energy": "XLE"},
        series={"SPY": make_series(300, 0.0005, 0.01, 1), "XLK": make_series(300, 0.0025, 0.01, 2), "XLE": make_series(300, -0.0015, 0.01, 3)},
        stocks=[SectorStock(symbol="AAPL", sector="Technology", score=80, rating="Strong Buy", above_sma50=True),
                SectorStock(symbol="XOM", sector="Energy", score=30, rating="Avoid", above_sma50=False)],
    )
    rows = sector_rotation(req)
    assert [r["sector"] for r in rows] == ["Technology", "Energy"]
    assert rows[0]["top_symbols"] == ["AAPL"] and rows[1]["buy_count"] == 0


def test_exit_signal_for_collapsing_stock_and_hold_for_uptrend():
    down = make_series(300, -0.004, 0.015, 5, start=100)
    up = make_series(300, 0.002, 0.01, 6, start=100)
    out = exit_signals(ExitRequest(
        holdings=[HoldingSpec(symbol="DOWN", quantity=10, avg_cost=100, buy_date=date(2025, 8, 1)),
                  HoldingSpec(symbol="UP", quantity=5, avg_cost=100)],
        series={"DOWN": down, "UP": up},
        analysis={"DOWN": {"rating": "Avoid", "score": 20, "metrics": {}}, "UP": {"rating": "Buy", "score": 70, "metrics": {"rs_6m": 0.1}}},
    ))
    by = {o["symbol"]: o for o in out}
    assert by["DOWN"]["action"] == "Exit" and by["DOWN"]["reasons_to_exit"]
    assert by["UP"]["action"] in ("Hold", "Add", "Trim") and by["UP"]["reasons_to_hold"]


def test_fx_stats():
    s = make_series(300, 0.0002, 0.003, 7, start=83)
    out = fx_stats(FxRequest(series=s))
    assert out["rate"] == pytest.approx(s.close[-1], rel=1e-4)
    assert out["trend"] in ("Dollar strengthening", "Rupee strengthening")
