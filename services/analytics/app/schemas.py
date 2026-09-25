from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class PriceSeries(BaseModel):
    """Columnar OHLCV series - much smaller on the wire than one object per bar."""

    dates: list[date]
    open: list[float | None]
    high: list[float | None]
    low: list[float | None]
    close: list[float | None]
    volume: list[float | None]


class Fundamentals(BaseModel):
    name: str | None = None
    sector: str | None = None
    forward_pe: float | None = None
    trailing_pe: float | None = None
    revenue_growth: float | None = None
    profit_margin: float | None = None
    debt_to_equity: float | None = None
    market_cap: float | None = None


class AnalyzeRequest(BaseModel):
    as_of: date
    series: dict[str, PriceSeries]
    benchmark: str = "SPY"
    volatility_index: str | None = "^VIX"
    fundamentals: dict[str, Fundamentals] = Field(default_factory=dict)
    top_n: int = 10


class StockAnalysis(BaseModel):
    symbol: str
    rank: int
    score: float
    rating: str
    price: float
    stop_loss: float | None
    target_weight: float | None
    components: dict[str, float]
    metrics: dict[str, Any]
    reasons: list[str]
    cautions: list[str]


class MarketRegime(BaseModel):
    label: str
    equity_exposure: float
    summary: str
    metrics: dict[str, Any]


class AnalyzeResponse(BaseModel):
    as_of: date
    model_version: str
    regime: MarketRegime
    recommendations: list[StockAnalysis]
    skipped: dict[str, str]


class IndicatorRequest(BaseModel):
    series: PriceSeries


class PerformanceRec(BaseModel):
    run_date: date
    symbol: str
    rating: str
    score: float


class PerformanceRequest(BaseModel):
    recommendations: list[PerformanceRec]
    closes: dict[str, dict[date, float]]
    benchmark: str = "SPY"
    horizons: list[int] = Field(default_factory=lambda: [5, 21, 63])
