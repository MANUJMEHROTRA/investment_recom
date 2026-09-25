"""Free market data from Yahoo Finance via the open-source `yfinance` library (no API key).

Yahoo quotes are delayed by up to ~15 minutes during market hours, which is plenty for
a daily-horizon strategy.
"""
from __future__ import annotations

import logging
import math
import time
from typing import Any

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

CHUNK = 40
COLUMNS = ["open", "high", "low", "close", "volume"]


def _split(raw: pd.DataFrame, symbols: list[str]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    if raw is None or raw.empty:
        return out
    for sym in symbols:
        if isinstance(raw.columns, pd.MultiIndex):
            if sym not in raw.columns.get_level_values(0):
                continue
            df = raw[sym]
        else:
            df = raw
        df = df.rename(columns=str.lower)
        if "close" not in df:
            continue
        df = df.dropna(subset=["close"])
        if not df.empty:
            df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
            out[sym] = df[[c for c in COLUMNS if c in df]]
    return out


def _download(symbols: list[str], period: str, threads: bool) -> dict[str, pd.DataFrame]:
    try:
        raw = yf.download(
            symbols,
            period=period,
            interval="1d",
            auto_adjust=True,
            group_by="ticker",
            threads=threads,
            progress=False,
        )
        return _split(raw, symbols)
    except Exception:  # noqa: BLE001 - one bad chunk shouldn't sink the run
        log.exception("history download failed for %s", symbols)
        return {}


def download_history(symbols: list[str], period: str = "2y") -> dict[str, pd.DataFrame]:
    """Split- and dividend-adjusted daily OHLCV for each symbol."""
    result: dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), CHUNK):
        result.update(_download(symbols[i : i + CHUNK], period, threads=True))
        time.sleep(1)
    # yfinance's threaded mode occasionally trips over its own cache lock; retry stragglers one by one.
    for sym in [s for s in symbols if s not in result]:
        result.update(_download([sym], period, threads=False))
    missing = set(symbols) - set(result)
    if missing:
        log.warning("no price data for: %s", ", ".join(sorted(missing)))
    return result


def _finite(v: Any) -> Any:
    """Yahoo sometimes reports Infinity/NaN (e.g. P/E on near-zero earnings); treat those as missing."""
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def fetch_fundamentals(symbol: str) -> dict[str, Any]:
    info = yf.Ticker(symbol).info or {}
    return {k: _finite(v) for k, v in {
        "name": info.get("shortName") or info.get("longName"),
        "sector": info.get("sector") or info.get("category"),
        "industry": info.get("industry"),
        "quote_type": info.get("quoteType"),
        "market_cap": info.get("marketCap") or info.get("totalAssets"),
        "forward_pe": info.get("forwardPE"),
        "trailing_pe": info.get("trailingPE"),
        "revenue_growth": info.get("revenueGrowth"),
        "profit_margin": info.get("profitMargins"),
        "debt_to_equity": info.get("debtToEquity"),
    }.items()}


def fetch_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Latest (delayed) price and change vs the previous close. During market hours
    Yahoo's daily bar for today updates live, so the last daily bar is the current quote."""
    raw = yf.download(
        symbols, period="5d", interval="1d", auto_adjust=False, group_by="ticker", threads=True, progress=False
    )
    quotes: dict[str, dict[str, Any]] = {}
    for sym, df in _split(raw, symbols).items():
        if len(df) < 2:
            continue
        last, prev = float(df["close"].iloc[-1]), float(df["close"].iloc[-2])
        quotes[sym] = {
            "price": round(last, 4),
            "prev_close": round(prev, 4),
            "change": round(last - prev, 4),
            "change_pct": round(last / prev - 1, 6) if prev else None,
            "as_of": df.index[-1].date().isoformat(),
        }
    return quotes
