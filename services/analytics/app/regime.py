"""Market-regime detection: is the overall tape friendly to buying stocks right now?

Combines three independent signals so a single noisy input can't flip the verdict:
  * benchmark trend  - S&P 500 (SPY) vs its 200-day average
  * fear gauge       - VIX level
  * breadth          - share of the universe trading above its own 200-day average
"""
from __future__ import annotations

import pandas as pd

from .indicators import sma, total_return
from .schemas import MarketRegime

EXPOSURE = {"Risk-On": 1.0, "Neutral": 0.6, "Risk-Off": 0.3}


def detect_regime(
    bench_close: pd.Series,
    vix_close: pd.Series | None,
    breadth_above_200: float | None,
    breadth_above_50: float | None,
) -> MarketRegime:
    price = float(bench_close.iloc[-1])
    sma200 = sma(bench_close, 200).iloc[-1]
    sma50 = sma(bench_close, 50).iloc[-1]
    above_200 = bool(pd.notna(sma200) and price > sma200)
    vix = float(vix_close.iloc[-1]) if vix_close is not None and len(vix_close) else None

    bullish = 0
    bearish = 0
    notes: list[str] = []

    if pd.notna(sma200):
        gap = price / sma200 - 1
        if above_200:
            bullish += 1
            notes.append(f"S&P 500 is {gap:+.1%} vs its 200-day average (uptrend)")
        else:
            bearish += 1
            notes.append(f"S&P 500 is {gap:+.1%} vs its 200-day average (downtrend)")

    if vix is not None:
        if vix < 20:
            bullish += 1
            notes.append(f"VIX {vix:.1f} - calm volatility")
        elif vix > 25:
            bearish += 1
            notes.append(f"VIX {vix:.1f} - elevated fear")
        else:
            notes.append(f"VIX {vix:.1f} - moderate volatility")

    if breadth_above_200 is not None:
        if breadth_above_200 >= 0.55:
            bullish += 1
            notes.append(f"{breadth_above_200:.0%} of tracked stocks above their 200-day average (broad participation)")
        elif breadth_above_200 < 0.40:
            bearish += 1
            notes.append(f"only {breadth_above_200:.0%} of tracked stocks above their 200-day average (weak breadth)")
        else:
            notes.append(f"{breadth_above_200:.0%} of tracked stocks above their 200-day average")

    if bullish >= 2 and bearish == 0:
        label = "Risk-On"
    elif bearish >= 2 or (not above_200 and bearish >= 1 and bullish == 0):
        label = "Risk-Off"
    else:
        label = "Neutral"

    exposure = EXPOSURE[label]
    lead = {
        "Risk-On": "Conditions favour being invested.",
        "Neutral": "Mixed conditions - be selective and keep some cash.",
        "Risk-Off": "Defensive conditions - keep most capital in cash and size positions small.",
    }[label]
    detail = "; ".join(notes)
    summary = f"{lead} Suggested equity exposure {exposure:.0%}. {detail[:1].upper()}{detail[1:]}."

    return MarketRegime(
        label=label,
        equity_exposure=exposure,
        summary=summary,
        metrics={
            "benchmark_price": round(price, 2),
            "benchmark_sma50": _r(sma50),
            "benchmark_sma200": _r(sma200),
            "benchmark_ret_1m": _r(total_return(bench_close, 21), 4),
            "benchmark_ret_3m": _r(total_return(bench_close, 63), 4),
            "vix": _r(vix),
            "breadth_above_200": _r(breadth_above_200, 3),
            "breadth_above_50": _r(breadth_above_50, 3),
        },
    )


def _r(value, digits: int = 2):
    return None if value is None or pd.isna(value) else round(float(value), digits)
