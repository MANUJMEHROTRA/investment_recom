"""Request/response contracts with the backend, and the structured outputs asked of the LLM.

LLM output schemas deliberately avoid numeric range constraints (not every provider's
structured-output mode supports them); values are clamped in code instead."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- from the backend


class Candidate(BaseModel):
    symbol: str
    name: str | None = None
    sector: str | None = None
    cap_category: str | None = None
    rank: int
    score: float
    rating: str
    price: float
    target_weight: float | None = None
    stop_loss: float | None = None
    components: dict[str, float] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


class HoldingIn(BaseModel):
    symbol: str
    name: str | None = None
    sector: str | None = None
    quantity: float
    avg_cost: float
    price: float | None = None
    pnl_pct: float | None = None
    pnl_inr_pct: float | None = None
    fx_gain_inr: float | None = None
    signal: dict[str, Any] = Field(default_factory=dict)  # quant exit signal from the analytics service


class SectorIn(BaseModel):
    sector: str
    etf: str
    rank: int
    quadrant: str
    ret_1w: float | None = None
    ret_1m: float | None = None
    ret_3m: float | None = None
    rs_1m: float | None = None
    rs_3m: float | None = None
    breadth_50: float | None = None
    avg_score: float | None = None
    buy_count: int = 0
    stock_count: int = 0
    top_symbols: list[str] = Field(default_factory=list)


class BriefRequest(BaseModel):
    as_of: date
    regime: dict[str, Any]
    fx: dict[str, Any] = Field(default_factory=dict)
    candidates: list[Candidate] = Field(default_factory=list)
    holdings: list[HoldingIn] = Field(default_factory=list)
    sectors: list[SectorIn] = Field(default_factory=list)


# ---------------------------------------------------------------- asked of the LLM


class ArticleAssessment(BaseModel):
    id: str = Field(description="Article id exactly as given, e.g. A3")
    sentiment: float = Field(description="Impact on the stock price from -1 (very negative) to 1 (very positive)")
    relevance: float = Field(description="0 to 1: how much this article matters for an investment decision")
    takeaway: str = Field(description="One sentence: what an investor should take from this article")


class PickAnalysis(BaseModel):
    article_assessments: list[ArticleAssessment]
    news_sentiment: float = Field(description="Overall news sentiment from -1 to 1, weighting relevant and trusted articles most")
    conviction: Literal["High", "Medium", "Low", "Avoid"] = Field(description="Conviction in buying now, combining the quantitative signals and the news")
    thesis: str = Field(description="3-5 sentence investment rationale citing numbers from the data and article ids like [A2]")
    catalysts: list[str] = Field(description="Upcoming or recent positive drivers, each citing article ids where applicable")
    risks: list[str] = Field(description="Specific risks, each citing article ids where applicable")
    evidence_ids: list[str] = Field(description="Ids of the articles that most support the thesis")


class ExitAnalysis(BaseModel):
    article_assessments: list[ArticleAssessment]
    news_sentiment: float = Field(description="Overall news sentiment from -1 to 1")
    action: Literal["Add", "Hold", "Trim", "Exit"]
    confidence: Literal["High", "Medium", "Low"]
    rationale: str = Field(description="3-5 sentences explaining the action, citing numbers and article ids like [A1]")
    reasons_to_exit: list[str]
    reasons_to_hold: list[str]
    evidence_ids: list[str]


class SectorStance(BaseModel):
    sector: str
    stance: Literal["Overweight", "Neutral", "Underweight"]
    rationale: str = Field(description="2-3 sentences citing the sector statistics and article ids")
    evidence_ids: list[str]


class SectorBriefAnalysis(BaseModel):
    headline: str = Field(description="One-line summary of today's market and sector picture")
    market_narrative: str = Field(description="One paragraph on what is driving markets, citing article ids")
    sectors: list[SectorStance]
    key_risks: list[str]
    inr_investor_note: str = Field(description="1-2 sentences on what the stated rupee move means for an India-based investor buying US stocks")
    evidence_ids: list[str]
