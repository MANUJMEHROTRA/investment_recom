"""Pure technical-indicator functions over pandas Series.

Every function is side-effect free and works on a date-indexed Series so it can be
unit-tested without a database or network.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's RSI. 100 when there were no losses, 50 when the price was flat."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
        out = 100 - 100 / (1 + rs)
    out = out.where(avg_loss != 0, 100.0)
    out = out.where(~((avg_loss == 0) & (avg_gain == 0)), 50.0)
    return out.where(avg_gain.notna())


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return true_range.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def total_return(close: pd.Series, days: int, skip_recent: int = 0) -> float | None:
    """Return over `days` bars, optionally ending `skip_recent` bars ago (e.g. 12-1 momentum)."""
    if len(close) <= days:
        return None
    end = close.iloc[-1 - skip_recent]
    start = close.iloc[-1 - days]
    if start <= 0 or pd.isna(start) or pd.isna(end):
        return None
    return float(end / start - 1)


def annualized_volatility(close: pd.Series, days: int = 63) -> float | None:
    rets = np.log(close).diff().dropna().iloc[-days:]
    if len(rets) < max(10, days // 2):
        return None
    return float(rets.std(ddof=1) * np.sqrt(TRADING_DAYS))


def max_drawdown(close: pd.Series, days: int = TRADING_DAYS) -> float | None:
    window = close.iloc[-days:]
    if len(window) < 2:
        return None
    return float((window / window.cummax() - 1).min())


def sharpe_ratio(close: pd.Series, days: int = TRADING_DAYS, risk_free: float = 0.0) -> float | None:
    rets = close.pct_change().dropna().iloc[-days:]
    if len(rets) < 20 or rets.std(ddof=1) == 0:
        return None
    excess = rets - risk_free / TRADING_DAYS
    return float(excess.mean() / excess.std(ddof=1) * np.sqrt(TRADING_DAYS))
