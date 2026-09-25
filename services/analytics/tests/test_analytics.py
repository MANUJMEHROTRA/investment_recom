from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import indicators as ind
from app.main import app
from app.schemas import AnalyzeRequest, PerformanceRec, PerformanceRequest, PriceSeries
from app.scoring import analyze, percentile, rating_for
from app.performance import evaluate

client = TestClient(app)


def make_series(n: int, drift: float, vol: float, seed: int, start: float = 100.0) -> PriceSeries:
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, n)
    close = start * np.exp(np.cumsum(rets))
    dates = pd.bdate_range(end=date(2026, 9, 24), periods=n)
    return PriceSeries(
        dates=[d.date() for d in dates],
        open=list(close),
        high=list(close * 1.01),
        low=list(close * 0.99),
        close=list(close),
        volume=[1e6] * n,
    )


def test_sma_and_returns():
    s = pd.Series([1.0, 2, 3, 4, 5])
    assert ind.sma(s, 5).iloc[-1] == 3
    assert ind.total_return(s, 4) == pytest.approx(4.0)
    assert ind.total_return(s, 10) is None


def test_rsi_extremes():
    up = pd.Series(np.arange(1, 40, dtype=float))
    flat = pd.Series([10.0] * 40)
    assert ind.rsi(up).iloc[-1] == 100
    assert ind.rsi(flat).iloc[-1] == 50


def test_max_drawdown():
    s = pd.Series([100.0, 120, 60, 90])
    assert ind.max_drawdown(s) == pytest.approx(-0.5)


def test_percentile_handles_missing():
    p = percentile({"A": 1.0, "B": 2.0, "C": None})
    assert p["C"] == 0.5 and p["B"] > p["A"]


def test_rating_thresholds():
    assert rating_for(80) == "Strong Buy"
    assert rating_for(66) == "Buy"
    assert rating_for(50) == "Hold"
    assert rating_for(10) == "Avoid"


def test_analyze_ranks_uptrend_above_downtrend():
    req = AnalyzeRequest(
        as_of=date(2026, 9, 24),
        series={
            "SPY": make_series(400, 0.0004, 0.01, 1),
            "UP": make_series(400, 0.0020, 0.012, 2),
            "DOWN": make_series(400, -0.0020, 0.02, 3),
            "SHORT": make_series(50, 0.001, 0.01, 4),
        },
    )
    res = analyze(req)
    by_sym = {r.symbol: r for r in res.recommendations}
    assert "SHORT" in res.skipped
    assert "SPY" not in by_sym  # benchmark is context, not a pick
    assert by_sym["UP"].score > by_sym["DOWN"].score
    assert by_sym["UP"].rank == 1
    assert by_sym["DOWN"].rating in {"Hold", "Avoid"}
    assert by_sym["UP"].reasons, "every pick must explain itself"
    assert res.regime.label in {"Risk-On", "Neutral", "Risk-Off"}


def test_analyze_endpoint_and_weights_sum_to_exposure():
    series = {"SPY": make_series(400, 0.0005, 0.01, 1)}
    for i in range(8):
        series[f"S{i}"] = make_series(400, 0.0005 + i * 0.0003, 0.01 + i * 0.002, 10 + i)
    resp = client.post("/analyze", json=AnalyzeRequest(as_of=date(2026, 9, 24), series=series, top_n=5).model_dump(mode="json"))
    assert resp.status_code == 200
    body = resp.json()
    weights = [r["target_weight"] for r in body["recommendations"] if r["target_weight"]]
    if weights:
        assert sum(weights) == pytest.approx(body["regime"]["equity_exposure"], abs=1e-3)


def test_performance_forward_returns():
    d0 = date(2026, 1, 5)
    days = [d0 + timedelta(days=i) for i in range(10)]
    req = PerformanceRequest(
        recommendations=[PerformanceRec(run_date=d0, symbol="X", rating="Buy", score=70)],
        closes={
            "X": {d: 100 + i * 10 for i, d in enumerate(days)},
            "SPY": {d: 100.0 for d in days},
        },
        horizons=[5],
    )
    out = evaluate(req)
    row = out["rows"][0]
    assert row["ret_5d"] == pytest.approx(0.5)
    assert row["excess_5d"] == pytest.approx(0.5)
    assert out["summary"][0]["group"] == "All buy picks"
