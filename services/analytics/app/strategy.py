"""Backtest: "what if I had bought the top-N recommendations?" - in USD and, for an
India-based investor, in INR after FX costs.

Rules (all visible in the output so the user can audit them):
* On each rebalance date d (a recommendation date), buy the top-N ranked stocks at the OPEN of
  the next trading session (recommendations are made after the close / before the open).
* Equal weight. Hold until the next rebalance's entry open; the final period is marked to the
  latest close.
* Trading cost (optional) is charged on the fraction of the portfolio that changes.
* INR: rupees are converted to dollars once at the start and back once at the end, paying the
  FX markup each way; the currency move is either the actual USD/INR history or an assumed rate.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field


class RunPicks(BaseModel):
    run_date: date
    source: str = "scheduled"
    ranked: list[str]  # all symbols in rank order
    buyable: list[str] = Field(default_factory=list)  # Buy / Strong Buy only, in rank order


class OpenClose(BaseModel):
    dates: list[date]
    open: list[float | None]
    close: list[float | None]


class StrategyRequest(BaseModel):
    runs: list[RunPicks]
    prices: dict[str, OpenClose]
    fx: OpenClose | None = None  # INR per USD
    benchmark: str = "SPY"
    sizes: list[int] = Field(default_factory=lambda: [5, 10, 20, 30])
    rebalance_every: int = 5  # in recommendation days (5 ~ weekly)
    selection: Literal["ranked", "buyable"] = "ranked"
    fx_markup_pct: float = 1.0
    trade_cost_pct: float = 0.0
    fx_mode: Literal["actual", "assumed"] = "actual"
    assumed_fx_annual_pct: float = 1.0  # used when fx_mode == "assumed": rupee weakens this much per year


def _frame(oc: OpenClose) -> pd.DataFrame:
    return pd.DataFrame({"open": oc.open, "close": oc.close}, index=pd.to_datetime(oc.dates), dtype="float64").sort_index()


def _max_drawdown(curve: list[float]) -> float:
    arr = np.asarray([1.0, *curve])
    return float((arr / np.maximum.accumulate(arr) - 1).min())


def simulate(req: StrategyRequest) -> dict[str, Any]:
    px = {s: _frame(oc) for s, oc in req.prices.items()}
    bench = px[req.benchmark]
    sessions = bench.index
    runs = sorted(req.runs, key=lambda r: r.run_date)
    rebal = runs[:: max(1, req.rebalance_every)]
    fx = _frame(req.fx)["close"].dropna() if req.fx else None

    # entry session for each rebalance: first session strictly after the recommendation date
    entries = []
    for r in rebal:
        after = sessions[sessions > pd.Timestamp(r.run_date)]
        if len(after):
            entries.append((r, after[0]))
    if not entries:
        return {"assumptions": _assumptions(req), "results": [], "note": "Not enough price history after the recommendation dates yet."}
    last_session = sessions[-1]

    def price(sym: str, day: pd.Timestamp, field: str) -> float | None:
        df = px.get(sym)
        if df is None or day not in df.index:
            return None
        v = df.at[day, field]
        return None if pd.isna(v) else float(v)

    def period_return(syms: list[str], start: pd.Timestamp, end: pd.Timestamp, end_field: str) -> tuple[float | None, list[dict]]:
        rets, detail = [], []
        for s in syms:
            a, b = price(s, start, "open"), price(s, end, end_field)
            if a and b:
                rets.append(b / a - 1)
                detail.append({"symbol": s, "entry": round(a, 4), "exit": round(b, 4), "return": round(b / a - 1, 5)})
        return (float(np.mean(rets)) if rets else None), detail

    def fx_at(day: pd.Timestamp) -> float | None:
        if fx is None or fx.empty:
            return None
        s = fx.loc[:day]
        return float(s.iloc[-1]) if len(s) else float(fx.iloc[0])

    m = req.fx_markup_pct / 100
    c = req.trade_cost_pct / 100
    results = []
    for n in sorted(set(req.sizes)):
        equity, spy_eq, prev = 1.0, 1.0, set()
        curve, periods, wins, beats, trades = [], [], 0, 0, 0
        for k, (run, start) in enumerate(entries):
            final = k + 1 == len(entries)
            end, end_field = (last_session, "close") if final else (entries[k + 1][1], "open")
            if end <= start:
                continue
            pool = run.buyable if req.selection == "buyable" else run.ranked
            syms = [s for s in pool if s != req.benchmark][:n]
            if not syms:
                continue
            r, detail = period_return(syms, start, end, end_field)
            b, _ = period_return([req.benchmark], start, end, end_field)
            if r is None or b is None:
                continue
            changed = len(set(syms) ^ prev) / (2 * len(syms)) if prev else 1.0  # share of the book that turned over
            trades += len(set(syms) - prev) + len(prev - set(syms))
            cost = c * (2 * changed if prev else 1.0)
            r_net = (1 + r) * (1 - cost) - 1
            equity *= 1 + r_net
            spy_eq *= 1 + b
            wins += r_net > 0
            beats += r_net > b
            prev = set(syms)
            curve.append({"date": end.date().isoformat(), "strategy": round(equity, 5), "benchmark": round(spy_eq, 5)})
            periods.append(
                {"entry": start.date().isoformat(), "exit": end.date().isoformat(), "rec_date": run.run_date.isoformat(), "source": run.source,
                 "holdings": syms, "return": round(r_net, 5), "benchmark_return": round(b, 5), "turnover": round(changed, 3), "positions": detail}
            )
        if not periods:
            continue
        start_day = pd.Timestamp(periods[0]["entry"])
        end_day = pd.Timestamp(periods[-1]["exit"])
        days = (end_day - start_day).days
        years = days / 365.25
        usd_total, spy_total = equity - 1, spy_eq - 1

        if req.fx_mode == "actual" and fx_at(start_day) and fx_at(end_day):
            fx_move = fx_at(end_day) / fx_at(start_day) - 1
        else:
            fx_move = (1 + req.assumed_fx_annual_pct / 100) ** years - 1
        conv = (1 - m) ** 2  # INR->USD at start, USD->INR at end

        def inr(total_usd: float) -> float:
            return (1 + total_usd) * (1 + fx_move) * conv - 1

        for pt in curve:  # INR curve (markup applied as if you cashed out at that point)
            d = pd.Timestamp(pt["date"])
            move = (fx_at(d) / fx_at(start_day) - 1) if req.fx_mode == "actual" and fx_at(d) and fx_at(start_day) else (1 + req.assumed_fx_annual_pct / 100) ** ((d - start_day).days / 365.25) - 1
            pt["strategy_inr"] = round(pt["strategy"] * (1 + move) * conv, 5)
            pt["benchmark_inr"] = round(pt["benchmark"] * (1 + move) * conv, 5)

        ann = (lambda t: (1 + t) ** (1 / years) - 1) if years >= 1.0 else (lambda t: None)  # annualising < 1 year exaggerates
        results.append(
            {
                "size": n,
                "periods": len(periods),
                "start": periods[0]["entry"],
                "end": periods[-1]["exit"],
                "days": days,
                "usd": {"total": usd_total, "annualised": ann(usd_total), "max_drawdown": _max_drawdown([p["strategy"] for p in curve])},
                "benchmark_usd": {"total": spy_total, "annualised": ann(spy_total), "max_drawdown": _max_drawdown([p["benchmark"] for p in curve])},
                "inr": {"total": inr(usd_total), "annualised": ann(inr(usd_total))},
                "benchmark_inr": {"total": inr(spy_total), "annualised": ann(inr(spy_total))},
                "excess_usd": usd_total - spy_total,
                "win_rate": wins / len(periods),
                "beat_benchmark_rate": beats / len(periods),
                "avg_period_return": float(np.mean([p["return"] for p in periods])),
                "trades": trades,
                "fx_move": fx_move,
                "fx_cost": 1 - conv,
                "backfilled_periods": sum(p["source"] == "backfill" for p in periods),
                "curve": curve,
                "period_log": periods,
            }
        )
    return {"assumptions": _assumptions(req), "results": results}


def _assumptions(req: StrategyRequest) -> dict[str, Any]:
    return {
        "entry": "Buy at the next session's open after each recommendation date",
        "exit": "Sell at the next rebalance's entry open (last period marked to the latest close)",
        "weighting": "Equal weight across the N stocks",
        "rebalance_every_recommendation_days": req.rebalance_every,
        "selection": "Top N by model rank" if req.selection == "ranked" else "Top N among Buy / Strong Buy only (fewer if not enough)",
        "trade_cost_pct": req.trade_cost_pct,
        "fx_markup_pct_each_way": req.fx_markup_pct,
        "fx_mode": req.fx_mode,
        "assumed_fx_annual_pct": req.assumed_fx_annual_pct if req.fx_mode == "assumed" else None,
        "inr_formula": "INR return = (1 + USD return) x (1 + USD/INR change) x (1 - FX markup)^2 - 1",
        "benchmark": req.benchmark,
    }
