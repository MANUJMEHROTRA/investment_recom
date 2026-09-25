"""Track record: how did past recommendations actually do versus simply buying the S&P 500?"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from .schemas import PerformanceRequest


def _forward_return(series: pd.Series, start_date: pd.Timestamp, bars: int | None) -> tuple[float | None, float | None]:
    """Return (entry price, return) from the close on/before start_date, `bars` sessions later (None = latest)."""
    past = series.loc[:start_date]
    if past.empty:
        return None, None
    entry = float(past.iloc[-1])
    start_idx = len(past) - 1
    if bars is None:
        end_idx = len(series) - 1
        if end_idx == start_idx:
            return entry, None
    else:
        end_idx = start_idx + bars
        if end_idx >= len(series):
            return entry, None
    return entry, float(series.iloc[end_idx] / entry - 1)


def evaluate(req: PerformanceRequest) -> dict[str, Any]:
    closes = {
        sym: pd.Series({pd.Timestamp(d): v for d, v in points.items()}, dtype="float64").sort_index()
        for sym, points in req.closes.items()
    }
    bench = closes.get(req.benchmark)
    horizons: list[int | None] = [*req.horizons, None]
    keys = [f"{h}d" if h else "to_date" for h in horizons]

    rows: list[dict[str, Any]] = []
    for rec in req.recommendations:
        series = closes.get(rec.symbol)
        if series is None or series.empty:
            continue
        start = pd.Timestamp(rec.run_date)
        row: dict[str, Any] = {"run_date": rec.run_date.isoformat(), "symbol": rec.symbol, "rating": rec.rating, "score": rec.score}
        for key, h in zip(keys, horizons):
            entry, ret = _forward_return(series, start, h)
            row["entry_price"] = entry
            row[f"ret_{key}"] = ret
            bench_ret = _forward_return(bench, start, h)[1] if bench is not None else None
            row[f"excess_{key}"] = None if ret is None or bench_ret is None else ret - bench_ret
        rows.append(row)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["rating"]].append(row)
        if row["rating"] in ("Strong Buy", "Buy"):
            groups["All buy picks"].append(row)

    summary = []
    for name in ["All buy picks", "Strong Buy", "Buy", "Hold", "Avoid"]:
        members = groups.get(name, [])
        if not members:
            continue
        entry: dict[str, Any] = {"group": name, "count": len(members)}
        for key in keys:
            rets = [m[f"ret_{key}"] for m in members if m[f"ret_{key}"] is not None]
            excess = [m[f"excess_{key}"] for m in members if m[f"excess_{key}"] is not None]
            entry[key] = {
                "n": len(rets),
                "avg_return": sum(rets) / len(rets) if rets else None,
                "hit_rate": sum(r > 0 for r in rets) / len(rets) if rets else None,
                "avg_excess": sum(excess) / len(excess) if excess else None,
                "beat_benchmark_rate": sum(e > 0 for e in excess) / len(excess) if excess else None,
            }
        summary.append(entry)

    return {"horizons": keys, "summary": summary, "rows": rows}
