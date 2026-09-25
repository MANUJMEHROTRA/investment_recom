from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel, Field


class Article(BaseModel):
    id: str
    topic: str  # a ticker, "sector:<name>" or "macro"
    source_api: str  # yahoo | finnhub | sec
    publisher: str
    title: str
    summary: str = ""
    url: str
    published_at: datetime
    trust: float = 0.5
    relevance: float = 0.5
    rank: float = 0.0
    sentiment: float | None = None  # -1 .. 1
    sentiment_method: str | None = None  # vader | llm | filing-rule
    takeaway: str | None = None
    kind: str = "news"  # news | filing | insider
    extra: dict = Field(default_factory=dict)

    @staticmethod
    def make_id(url: str) -> str:
        return hashlib.sha1(url.encode()).hexdigest()[:12]
