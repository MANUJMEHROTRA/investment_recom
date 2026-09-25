"""Daily context: sector rotation, exit signals for existing holdings, and USD/INR."""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from .indicators import annualized_volatility, atr, macd, rsi, sma, total_return
from .schemas import PriceSeries
from .scoring import percentile, to_frame

# ---------------------------------------------------------------- sectors


class SectorStock(BaseModel):
    symbol: str
    sector: str | None
    score: float
    rating: str
    above_sma50: bool | None = None


class SectorRequest(BaseModel):
    as_of: date
    benchmark: str = "SPY"
    sector_etfs: dict[str, str]  # sector name -> ETF symbol
    series: dict[str, PriceSeries]
    stocks: list[SectorStock] = Field(default_factory=list)


def quadrant(rs_3m: float | None, rs_1m: float | None) -> str:
    """Relative-rotation style quadrant using 3-month RS as level and 1-month RS as direction."""
    if rs_3m is None or rs_1m is None:
        return "Unknown"
    if rs_3m >= 0:
        return "Leading" if rs_1m >= 0 else "Weakening"
    return "Improving" if rs_1m >= 0 else "Lagging"


def sector_rotation(req: SectorRequest) -> list[dict[str, Any]]:
    as_of = pd.Timestamp(req.as_of)
    bench = to_frame(req.series[req.benchmark])["close"].loc[:as_of]
    b = {n: total_return(bench, n) for n in (5, 21, 63)}
    rows: list[dict[str, Any]] = []
    for sector, etf in req.sector_etfs.items():
        if etf not in req.series:
            continue
        close = to_frame(req.series[etf])["close"].loc[:as_of]
        if len(close) < 70:
            continue
        r = {n: total_return(close, n) for n in (5, 21, 63)}
        rs = {n: None if r[n] is None or b[n] is None else r[n] - b[n] for n in (21, 63)}
        members = [s for s in req.stocks if s.sector == sector]
        above = [s.above_sma50 for s in members if s.above_sma50 is not None]
        buys = sorted((s for s in members if s.rating in ("Strong Buy", "Buy")), key=lambda s: -s.score)
        s200 = sma(close, 200).iloc[-1]
        rows.append(
            {
                "sector": sector,
                "etf": etf,
                "price": round(float(close.iloc[-1]), 2),
                "ret_1w": r[5],
                "ret_1m": r[21],
                "ret_3m": r[63],
                "rs_1m": rs[21],
                "rs_3m": rs[63],
                "above_sma200": bool(pd.notna(s200) and close.iloc[-1] > s200),
                "quadrant": quadrant(rs[63], rs[21]),
                "breadth_50": sum(above) / len(above) if above else None,
                "avg_score": round(sum(s.score for s in members) / len(members), 1) if members else None,
                "stock_count": len(members),
                "buy_count": len(buys),
                "top_symbols": [s.symbol for s in buys[:3]],
            }
        )
    if not rows:
        return rows
    p3 = percentile({x["sector"]: x["rs_3m"] for x in rows})
    p1 = percentile({x["sector"]: x["rs_1m"] for x in rows})
    for x in rows:
        x["strength"] = round(
            100 * (0.35 * p3[x["sector"]] + 0.25 * p1[x["sector"]] + 0.2 * ((x["avg_score"] or 50) / 100) + 0.2 * (x["breadth_50"] if x["breadth_50"] is not None else 0.5)),
            1,
        )
    rows.sort(key=lambda x: -x["strength"])
    for i, x in enumerate(rows, start=1):
        x["rank"] = i
    return rows


# ---------------------------------------------------------------- exits


class HoldingSpec(BaseModel):
    symbol: str
    quantity: float
    avg_cost: float
    buy_date: date | None = None


class ExitRequest(BaseModel):
    holdings: list[HoldingSpec]
    series: dict[str, PriceSeries]
    analysis: dict[str, dict[str, Any]] = Field(default_factory=dict)  # symbol -> latest recommendation row


def exit_signal(h: HoldingSpec, df: pd.DataFrame, rec: dict[str, Any] | None) -> dict[str, Any]:
    close = df["close"]
    price = float(close.iloc[-1])
    s50, s200 = sma(close, 50).iloc[-1], sma(close, 200).iloc[-1]
    r = rsi(close).iloc[-1]
    hist = macd(close)["hist"]
    a = atr(df["high"], df["low"], close).iloc[-1] if df["high"].notna().sum() > 20 else None
    since = close.loc[pd.Timestamp(h.buy_date):] if h.buy_date else close
    high_since = float((since if len(since) else close).max())
    trailing = high_since - 3 * float(a) if a is not None and pd.notna(a) else None
    pnl = price / h.avg_cost - 1 if h.avg_cost else None
    rating = (rec or {}).get("rating")
    metrics = (rec or {}).get("metrics", {})

    exit_pts, hold_pts = 0, 0
    to_exit: list[str] = []
    to_hold: list[str] = []
    if trailing is not None and price < trailing:
        exit_pts += 3
        to_exit.append(f"Price ${price:,.2f} is below the trailing stop ${trailing:,.2f} (3x ATR under the ${high_since:,.2f} high since you bought).")
    if pd.notna(s200) and pd.notna(s50) and price < s200 and s50 < s200:
        exit_pts += 3
        to_exit.append(f"Confirmed downtrend: price and the 50-day average (${s50:,.2f}) are both below the 200-day (${s200:,.2f}).")
    elif pd.notna(s200) and price < s200:
        exit_pts += 1
        to_exit.append(f"Price slipped below the 200-day average (${s200:,.2f}).")
    if pd.notna(s50) and price < s50:
        exit_pts += 1
        to_exit.append(f"Below the 50-day average (${s50:,.2f}) - short-term momentum has turned.")
    if rating == "Avoid":
        exit_pts += 2
        to_exit.append(f"The model now rates it Avoid (score {rec.get('score', 0):.0f}/100).")
    if pnl is not None and pnl <= -0.15:
        exit_pts += 1
        to_exit.append(f"Down {abs(pnl):.0%} from your average cost.")
    if len(hist) > 6 and hist.iloc[-1] < 0 and (hist.iloc[-6:-1] >= 0).any():
        exit_pts += 1
        to_exit.append("MACD crossed below its signal line this week (momentum fading).")

    if pd.notna(s200) and pd.notna(s50) and price > s200 and s50 > s200:
        hold_pts += 2
        to_hold.append(f"Long-term uptrend intact ({price / s200 - 1:+.1%} vs the 200-day average).")
    if rating in ("Strong Buy", "Buy"):
        hold_pts += 2
        to_hold.append(f"The model still rates it {rating} (score {rec.get('score', 0):.0f}/100).")
    if (metrics.get("rs_6m") or 0) > 0:
        hold_pts += 1
        to_hold.append(f"Beating the S&P 500 by {metrics['rs_6m'] * 100:.1f} pts over 6 months.")
    if (metrics.get("dist_52w_high") or -1) >= -0.05:
        hold_pts += 1
        to_hold.append("Trading near its 52-week high.")

    trim = pnl is not None and pnl >= 0.30 and pd.notna(r) and r > 75
    if trim:
        to_exit.append(f"Up {pnl:.0%} with RSI {r:.0f} (overbought) - consider taking partial profits.")

    if exit_pts >= 4:
        action = "Exit"
    elif exit_pts >= 2 or trim:
        action = "Trim"
    elif hold_pts >= 4 and rating == "Strong Buy" and pd.notna(s50) and price <= s50 * 1.08:
        action = "Add"
    else:
        action = "Hold"

    return {
        "symbol": h.symbol,
        "action": action,
        "exit_points": exit_pts,
        "hold_points": hold_pts,
        "reasons_to_exit": to_exit,
        "reasons_to_hold": to_hold,
        "price": round(price, 4),
        "pnl_pct": None if pnl is None else round(pnl, 4),
        "trailing_stop": None if trailing is None else round(trailing, 2),
        "high_since_buy": round(high_since, 2),
        "rsi14": None if pd.isna(r) else round(float(r), 1),
        "sma50": None if pd.isna(s50) else round(float(s50), 2),
        "sma200": None if pd.isna(s200) else round(float(s200), 2),
        "rating": rating,
        "score": (rec or {}).get("score"),
    }


def exit_signals(req: ExitRequest) -> list[dict[str, Any]]:
    out = []
    for h in req.holdings:
        ps = req.series.get(h.symbol)
        if ps is None:
            out.append({"symbol": h.symbol, "action": "Hold", "error": "no price data", "reasons_to_exit": [], "reasons_to_hold": []})
            continue
        out.append(exit_signal(h, to_frame(ps), req.analysis.get(h.symbol)))
    return out


# ---------------------------------------------------------------- USD/INR


class FxRequest(BaseModel):
    series: PriceSeries  # INR per 1 USD


def fx_stats(req: FxRequest) -> dict[str, Any]:
    close = to_frame(req.series)["close"]
    s200 = sma(close, 200).iloc[-1]
    rate = float(close.iloc[-1])
    years = (close.index[-1] - close.index[0]).days / 365.25
    return {
        "rate": round(rate, 4),
        "as_of": close.index[-1].date().isoformat(),
        "ret_1w": total_return(close, 5),
        "ret_1m": total_return(close, 21),
        "ret_3m": total_return(close, 63),
        "ret_6m": total_return(close, 126),
        "ret_1y": total_return(close, 252),
        "cagr": (rate / float(close.iloc[0])) ** (1 / years) - 1 if years > 0.5 else None,
        "cagr_years": round(years, 1),
        "volatility_1y": annualized_volatility(close, 252),
        "sma200": None if pd.isna(s200) else round(float(s200), 4),
        "trend": "Dollar strengthening" if pd.notna(s200) and rate > s200 else "Rupee strengthening",
    }
