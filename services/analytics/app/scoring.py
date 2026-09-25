"""Multi-factor scoring model.

Each stock gets six component scores (0-100). Four are cross-sectional - a stock is
compared against the rest of the universe on the same day - so the model adapts to
whatever the market is doing instead of relying on fixed thresholds.

    trend              25%  price vs 20/50/200-day averages, 50-day slope
    momentum           25%  12-1 month, 6 month, 3 month return (percentile rank)
    relative_strength  15%  6 and 3 month return minus the S&P 500 (percentile rank)
    timing             10%  RSI zone, MACD direction/crossover, distance from 52w high
    risk               15%  low volatility, shallow drawdown, high Sharpe (percentile rank)
    fundamentals       10%  forward P/E, revenue growth, profit margin, leverage

Every point awarded is also written out as a plain-English reason so each
recommendation explains itself.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .indicators import (
    annualized_volatility,
    atr,
    macd,
    max_drawdown,
    rsi,
    sharpe_ratio,
    sma,
    total_return,
)
from .regime import detect_regime
from .schemas import AnalyzeRequest, AnalyzeResponse, Fundamentals, PriceSeries, StockAnalysis

MODEL_VERSION = "1.0.0"
MIN_BARS = 210

WEIGHTS = {
    "trend": 0.25,
    "momentum": 0.25,
    "relative_strength": 0.15,
    "timing": 0.10,
    "risk": 0.15,
    "fundamentals": 0.10,
}

# Absolute (not relative) cut-offs, so a weak market produces fewer buys instead of
# always promoting the "least bad" names.
RATING_THRESHOLDS = [(78, "Strong Buy"), (65, "Buy"), (45, "Hold"), (0, "Avoid")]
BUYABLE = {"Strong Buy", "Buy"}


def to_frame(ps: PriceSeries) -> pd.DataFrame:
    df = pd.DataFrame(
        {"open": ps.open, "high": ps.high, "low": ps.low, "close": ps.close, "volume": ps.volume},
        index=pd.to_datetime(ps.dates),
        dtype="float64",
    ).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df.dropna(subset=["close"])


def compute_features(df: pd.DataFrame, bench_close: pd.Series) -> dict[str, Any]:
    close = df["close"]
    price = float(close.iloc[-1])
    sma20, sma50, sma200 = (sma(close, n) for n in (20, 50, 200))
    macd_df = macd(close)
    hist = macd_df["hist"]
    recent_hist = hist.iloc[-6:-1]

    bench = bench_close.loc[: close.index[-1]]
    ret_6m = total_return(close, 126)
    ret_3m = total_return(close, 63)
    bench_6m = total_return(bench, 126)
    bench_3m = total_return(bench, 63)

    atr_val = None
    if df["high"].notna().sum() > 20 and df["low"].notna().sum() > 20:
        atr_val = _f(atr(df["high"], df["low"], close).iloc[-1])

    vol = df["volume"]
    volume_ratio = None
    if vol.notna().sum() >= 60 and vol.iloc[-60:].mean() > 0:
        volume_ratio = float(vol.iloc[-20:].mean() / vol.iloc[-60:].mean())

    ret_12m_ex1m = total_return(close, 252, skip_recent=21)
    return {
        "price": price,
        "sma20": _f(sma20.iloc[-1]),
        "sma50": _f(sma50.iloc[-1]),
        "sma200": _f(sma200.iloc[-1]),
        "sma50_slope": _pct_change(sma50.iloc[-1], sma50.iloc[-21]),
        "rsi14": _f(rsi(close).iloc[-1]),
        "macd_hist": _f(hist.iloc[-1]),
        "macd_bullish_cross": bool(hist.iloc[-1] > 0 and (recent_hist <= 0).any()),
        "macd_bearish_cross": bool(hist.iloc[-1] < 0 and (recent_hist >= 0).any()),
        "atr14": atr_val,
        "ret_1m": total_return(close, 21),
        "ret_3m": ret_3m,
        "ret_6m": ret_6m,
        "ret_12m_ex1m": ret_12m_ex1m,
        "momentum_long": ret_12m_ex1m if ret_12m_ex1m is not None else ret_6m,
        "rs_6m": None if ret_6m is None or bench_6m is None else ret_6m - bench_6m,
        "rs_3m": None if ret_3m is None or bench_3m is None else ret_3m - bench_3m,
        "volatility_3m": annualized_volatility(close, 63),
        "max_drawdown_1y": max_drawdown(close, 252),
        "sharpe_1y": sharpe_ratio(close, 252),
        "dist_52w_high": price / float(close.iloc[-252:].max()) - 1,
        "volume_ratio": volume_ratio,
    }


def percentile(values: dict[str, float | None], higher_is_better: bool = True) -> dict[str, float]:
    """Cross-sectional percentile in [0, 1]; missing values sit at the median."""
    s = pd.Series(values, dtype="float64")
    ranks = s.rank(pct=True, ascending=higher_is_better)
    return {k: (0.5 if pd.isna(v) else float(v)) for k, v in ranks.items()}


def trend_score(f: dict[str, Any]) -> float:
    p, s20, s50, s200, slope = f["price"], f["sma20"], f["sma50"], f["sma200"], f["sma50_slope"]
    pts = 0.0
    pts += 30 if s200 and p > s200 else 0
    pts += 20 if s50 and p > s50 else 0
    pts += 25 if s50 and s200 and s50 > s200 else 0
    pts += 15 if slope is not None and slope > 0 else 0
    pts += 10 if s20 and p > s20 else 0
    return pts


def timing_score(f: dict[str, Any]) -> float:
    score = 50.0
    r = f["rsi14"]
    uptrend = bool(f["sma200"] and f["price"] > f["sma200"])
    if r is not None:
        if 45 <= r <= 65:
            score += 20
        elif 65 < r <= 75:
            score += 5
        elif r > 75:
            score -= 25
        elif 30 <= r < 45:
            score += 15 if uptrend else 0
        else:  # r < 30
            score += 10 if uptrend else -10
    if f["macd_hist"] is not None:
        score += 15 if f["macd_hist"] > 0 else -10
    if f["macd_bullish_cross"]:
        score += 10
    if f["dist_52w_high"] >= -0.05:
        score += 10
    elif f["dist_52w_high"] < -0.30:
        score -= 10
    return float(np.clip(score, 0, 100))


def fundamentals_score(fund: Fundamentals | None) -> tuple[float, bool]:
    """Returns (score, had_data). Missing data is neutral (50) rather than punished."""
    if fund is None:
        return 50.0, False
    parts: list[float] = []
    pe = fund.forward_pe
    if pe is not None:
        parts.append(0.0 if pe <= 0 else 1.0 if pe <= 25 else 0.6 if pe <= 40 else 0.25)
    g = fund.revenue_growth
    if g is not None:
        parts.append(1.0 if g > 0.15 else 0.75 if g > 0.05 else 0.5 if g > 0 else 0.15)
    m = fund.profit_margin
    if m is not None:
        parts.append(1.0 if m > 0.20 else 0.75 if m > 0.10 else 0.5 if m > 0 else 0.1)
    d = fund.debt_to_equity  # yfinance reports this in percent, e.g. 150 = 1.5x
    if d is not None:
        parts.append(1.0 if d < 50 else 0.6 if d < 150 else 0.3)
    if not parts:
        return 50.0, False
    return 100 * sum(parts) / len(parts), True


def rating_for(score: float) -> str:
    return next(label for threshold, label in RATING_THRESHOLDS if score >= threshold)


def explain(f: dict[str, Any], pct: dict[str, dict[str, float]], sym: str, fund: Fundamentals | None) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    cautions: list[str] = []
    p, s50, s200 = f["price"], f["sma50"], f["sma200"]

    if s200:
        gap = p / s200 - 1
        if p > s200 and s50 and s50 > s200:
            reasons.append(f"Established uptrend: price is {gap:+.1%} vs the 200-day average and the 50-day is above the 200-day.")
        elif p > s200:
            reasons.append(f"Trading {gap:+.1%} above its 200-day average.")
        else:
            cautions.append(f"Below its 200-day average ({gap:+.1%}) - long-term trend is down.")
    if f["sma50_slope"] is not None and f["sma50_slope"] > 0.02:
        reasons.append(f"50-day average is rising ({f['sma50_slope']:+.1%} over the last month).")

    mom = f["momentum_long"]
    mom_pct = pct["momentum_long"][sym]
    if mom is not None:
        label = "12-month (ex. last month)" if f["ret_12m_ex1m"] is not None else "6-month"
        if mom_pct >= 0.8:
            reasons.append(f"Strong {label} momentum of {mom:+.1%} - top {100 - mom_pct * 100:.0f}% of the universe.")
        elif mom_pct <= 0.2:
            cautions.append(f"Weak {label} momentum of {mom:+.1%} - bottom {mom_pct * 100:.0f}% of the universe.")

    if f["rs_6m"] is not None:
        if f["rs_6m"] > 0.05:
            reasons.append(f"Outperforming the S&P 500 by {f['rs_6m'] * 100:.1f} pts over 6 months.")
        elif f["rs_6m"] < -0.10:
            cautions.append(f"Lagging the S&P 500 by {abs(f['rs_6m']) * 100:.1f} pts over 6 months.")

    r = f["rsi14"]
    if r is not None:
        if r > 75:
            cautions.append(f"RSI {r:.0f} - overbought; consider waiting for a pullback before buying.")
        elif 45 <= r <= 65:
            reasons.append(f"RSI {r:.0f} - healthy momentum, not overbought.")
        elif r < 45 and s200 and p > s200:
            reasons.append(f"RSI {r:.0f} - pulled back within an uptrend, a potential entry point.")
        elif r < 30:
            cautions.append(f"RSI {r:.0f} - oversold in a downtrend (falling knife risk).")

    if f["macd_bullish_cross"]:
        reasons.append("MACD crossed above its signal line in the last week (fresh bullish momentum).")
    elif f["macd_bearish_cross"]:
        cautions.append("MACD crossed below its signal line in the last week (momentum fading).")

    dh = f["dist_52w_high"]
    if dh >= -0.05:
        reasons.append(f"Within {abs(dh):.1%} of its 52-week high - buyers are in control.")
    elif dh < -0.30:
        cautions.append(f"{abs(dh):.0%} below its 52-week high.")

    vol = f["volatility_3m"]
    if vol is not None:
        low_vol_pct = pct["volatility_3m"][sym]  # higher = calmer (ranked descending)
        if low_vol_pct >= 0.7:
            reasons.append(f"Low volatility ({vol:.0%} annualised) - calmer than {low_vol_pct * 100:.0f}% of peers.")
        elif vol > 0.50:
            cautions.append(f"High volatility ({vol:.0%} annualised) - expect big swings; size the position small.")
    mdd = f["max_drawdown_1y"]
    if mdd is not None and mdd < -0.30:
        cautions.append(f"Fell as much as {mdd:.0%} from a peak within the last year.")
    if f["sharpe_1y"] is not None and f["sharpe_1y"] > 1.5:
        reasons.append(f"Excellent risk-adjusted return over 1 year (Sharpe {f['sharpe_1y']:.2f}).")

    if f["volume_ratio"] is not None and f["volume_ratio"] > 1.3 and f["ret_1m"] and f["ret_1m"] > 0:
        reasons.append(f"Rising on above-average volume ({f['volume_ratio']:.1f}x the 3-month norm) - institutional interest.")

    if fund is not None:
        if fund.forward_pe is not None:
            if 0 < fund.forward_pe <= 25:
                reasons.append(f"Reasonable valuation: forward P/E {fund.forward_pe:.1f}.")
            elif fund.forward_pe > 40:
                cautions.append(f"Expensive: forward P/E {fund.forward_pe:.1f}.")
            elif fund.forward_pe <= 0:
                cautions.append("Negative forward earnings expected.")
        if fund.revenue_growth is not None:
            if fund.revenue_growth > 0.10:
                reasons.append(f"Revenue growing {fund.revenue_growth:.0%} year over year.")
            elif fund.revenue_growth < 0:
                cautions.append(f"Revenue shrinking ({fund.revenue_growth:.0%} YoY).")
        if fund.profit_margin is not None and fund.profit_margin > 0.20:
            reasons.append(f"High profit margin ({fund.profit_margin:.0%}).")
    return reasons, cautions


def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    skipped: dict[str, str] = {}
    if req.benchmark not in req.series:
        raise ValueError(f"benchmark {req.benchmark} missing from series")

    as_of = pd.Timestamp(req.as_of)
    frames = {s: to_frame(ps).loc[:as_of] for s, ps in req.series.items()}
    bench_close = frames[req.benchmark]["close"]
    vix_close = None
    if req.volatility_index and req.volatility_index in frames:
        vix_close = frames[req.volatility_index]["close"]

    features: dict[str, dict[str, Any]] = {}
    for sym, df in frames.items():
        if sym == req.volatility_index or sym.startswith("^"):
            continue
        if len(df) < MIN_BARS:
            skipped[sym] = f"insufficient history ({len(df)} bars, need {MIN_BARS})"
            continue
        if (as_of - df.index[-1]).days > 7:
            skipped[sym] = f"stale data (last bar {df.index[-1].date()})"
            continue
        features[sym] = compute_features(df, bench_close)

    stocks = [s for s in features if s != req.benchmark]
    above_200 = [features[s]["price"] > features[s]["sma200"] for s in stocks if features[s]["sma200"]]
    above_50 = [features[s]["price"] > features[s]["sma50"] for s in stocks if features[s]["sma50"]]
    regime = detect_regime(
        bench_close,
        vix_close,
        sum(above_200) / len(above_200) if above_200 else None,
        sum(above_50) / len(above_50) if above_50 else None,
    )

    if not stocks:
        return AnalyzeResponse(as_of=req.as_of, model_version=MODEL_VERSION, regime=regime, recommendations=[], skipped=skipped)

    col = lambda key: {s: features[s][key] for s in stocks}  # noqa: E731
    pct = {
        "momentum_long": percentile(col("momentum_long")),
        "ret_6m": percentile(col("ret_6m")),
        "ret_3m": percentile(col("ret_3m")),
        "rs_6m": percentile(col("rs_6m")),
        "rs_3m": percentile(col("rs_3m")),
        "volatility_3m": percentile(col("volatility_3m"), higher_is_better=False),
        "max_drawdown_1y": percentile(col("max_drawdown_1y")),
        "sharpe_1y": percentile(col("sharpe_1y")),
    }

    results: list[StockAnalysis] = []
    for sym in stocks:
        f = features[sym]
        fund = req.fundamentals.get(sym)
        fund_score, has_fund = fundamentals_score(fund)
        components = {
            "trend": trend_score(f),
            "momentum": 100 * (pct["momentum_long"][sym] + pct["ret_6m"][sym] + pct["ret_3m"][sym]) / 3,
            "relative_strength": 100 * (pct["rs_6m"][sym] + pct["rs_3m"][sym]) / 2,
            "timing": timing_score(f),
            "risk": 100 * (0.5 * pct["volatility_3m"][sym] + 0.3 * pct["max_drawdown_1y"][sym] + 0.2 * pct["sharpe_1y"][sym]),
            "fundamentals": fund_score,
        }
        score = sum(WEIGHTS[k] * v for k, v in components.items())
        reasons, cautions = explain(f, pct, sym, fund if has_fund else None)

        rating = rating_for(score)
        downtrend = bool(f["sma200"] and f["sma50"] and f["price"] < f["sma200"] and f["sma50"] < f["sma200"])
        if downtrend and rating in BUYABLE:
            rating = "Hold"
            cautions.append("Rating capped at Hold: the model does not recommend buying stocks in a confirmed downtrend.")
        if regime.label == "Risk-Off" and rating == "Strong Buy":
            rating = "Buy"
            cautions.append("Downgraded from Strong Buy because the overall market is Risk-Off.")
        if not has_fund:
            cautions.append("No fundamental data available - fundamentals scored as neutral.")

        stop = f["price"] - 2 * f["atr14"] if f["atr14"] else None
        results.append(
            StockAnalysis(
                symbol=sym,
                rank=0,
                score=round(score, 2),
                rating=rating,
                price=round(f["price"], 4),
                stop_loss=round(stop, 2) if stop and stop > 0 else None,
                target_weight=None,
                components={k: round(v, 1) for k, v in components.items()},
                metrics={k: _clean(v) for k, v in f.items()},
                reasons=reasons,
                cautions=cautions,
            )
        )

    results.sort(key=lambda r: (r.rating in BUYABLE, r.score), reverse=True)
    for i, r in enumerate(results, start=1):
        r.rank = i

    # Inverse-volatility position sizing across the buyable top-N, scaled by regime exposure.
    picks = [r for r in results[: req.top_n] if r.rating in BUYABLE]
    inv_vol = {r.symbol: 1 / max(r.metrics.get("volatility_3m") or 0.3, 0.05) for r in picks}
    total = sum(inv_vol.values())
    for r in picks:
        r.target_weight = round(regime.equity_exposure * inv_vol[r.symbol] / total, 4)

    return AnalyzeResponse(
        as_of=req.as_of,
        model_version=MODEL_VERSION,
        regime=regime,
        recommendations=results,
        skipped=skipped,
    )


def _f(v) -> float | None:
    return None if v is None or pd.isna(v) else float(v)


def _pct_change(now, before) -> float | None:
    if now is None or before is None or pd.isna(now) or pd.isna(before) or before == 0:
        return None
    return float(now / before - 1)


def _clean(v):
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    if isinstance(v, (float, np.floating)):
        return round(float(v), 6)
    return v
