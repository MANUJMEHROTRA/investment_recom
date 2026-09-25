from datetime import date, timedelta

import pytest

from app.strategy import OpenClose, RunPicks, StrategyRequest, simulate


def series(start: float, step: float, n: int, d0: date = date(2026, 1, 5)) -> OpenClose:
    days = [d0 + timedelta(days=i) for i in range(n)]
    opens = [start + step * i for i in range(n)]
    return OpenClose(dates=days, open=opens, close=[o + step / 2 for o in opens])


def test_top_n_equal_weight_next_open_entry_and_inr_formula():
    n = 12
    req = StrategyRequest(
        runs=[RunPicks(run_date=date(2026, 1, 5) + timedelta(days=i), ranked=["UP", "FLAT", "SPY"]) for i in range(0, 10, 5)],
        prices={"UP": series(100, 1, n), "FLAT": series(50, 0, n), "SPY": series(200, 0, n)},
        fx=OpenClose(dates=[date(2026, 1, 5) + timedelta(days=i) for i in range(n)], open=[80.0] * n, close=[80 + i * 0.1 for i in range(n)]),
        sizes=[1, 2], rebalance_every=5, fx_markup_pct=1.0,
    )
    out = simulate(req)
    top1 = next(r for r in out["results"] if r["size"] == 1)
    # entry = open of Jan 6 (101), next entry Jan 11 open (106), final exit = last close (111.5)
    assert top1["period_log"][0]["positions"][0]["entry"] == 101
    assert top1["usd"]["total"] == pytest.approx(111.5 / 101 - 1, rel=1e-6)
    top2 = next(r for r in out["results"] if r["size"] == 2)
    assert top2["usd"]["total"] < top1["usd"]["total"]  # FLAT dilutes the winner
    fx_move = (80 + 11 * 0.1) / (80 + 1 * 0.1) - 1
    assert top1["inr"]["total"] == pytest.approx((1 + top1["usd"]["total"]) * (1 + fx_move) * 0.99 ** 2 - 1, rel=1e-6)
    assert top1["benchmark_usd"]["total"] == pytest.approx(0.0)


def test_assumed_fx_and_buyable_selection():
    n = 30
    req = StrategyRequest(
        runs=[RunPicks(run_date=date(2026, 1, 5), ranked=["A", "B"], buyable=["B"])],
        prices={"A": series(10, 1, n), "B": series(10, 0.1, n), "SPY": series(100, 0, n)},
        sizes=[5], selection="buyable", fx_mode="assumed", assumed_fx_annual_pct=1.0, fx_markup_pct=0,
    )
    r = simulate(req)["results"][0]
    assert r["period_log"][0]["holdings"] == ["B"]
    assert r["fx_move"] == pytest.approx((1.01) ** (r["days"] / 365.25) - 1)
