"""Fast lexicon sentiment (VADER) tuned with finance vocabulary.

Used for every article as a baseline, and as the final score when no LLM is available.
"""
from __future__ import annotations

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from .models import Article

FINANCE_LEXICON = {
    "beat": 2.0, "beats": 2.0, "tops": 1.5, "upgrade": 2.0, "upgrades": 2.0, "upgraded": 2.0, "outperform": 1.8,
    "raises": 1.2, "raised": 1.2, "record": 1.5, "surge": 2.2, "surges": 2.2, "soar": 2.4, "soars": 2.4, "rally": 1.8,
    "bullish": 2.0, "buyback": 1.3, "dividend": 0.8, "approval": 1.8, "approved": 1.8, "partnership": 1.0, "expands": 1.0,
    "miss": -2.0, "misses": -2.0, "missed": -2.0, "downgrade": -2.0, "downgrades": -2.0, "downgraded": -2.0,
    "underperform": -1.8, "cuts": -1.2, "cut": -1.0, "plunge": -2.6, "plunges": -2.6, "tumble": -2.2, "tumbles": -2.2,
    "slump": -2.0, "bearish": -2.0, "lawsuit": -1.6, "probe": -1.6, "investigation": -1.6, "recall": -1.6,
    "layoffs": -1.5, "fraud": -3.0, "antitrust": -1.2, "tariff": -1.0, "tariffs": -1.0, "warning": -1.5, "halt": -1.5,
    "volatility": -0.5, "bankruptcy": -3.0, "default": -2.0, "delay": -1.2, "delayed": -1.2, "weak": -1.5,
}

_analyzer = SentimentIntensityAnalyzer()
_analyzer.lexicon.update(FINANCE_LEXICON)


def score_text(text: str) -> float:
    return float(_analyzer.polarity_scores(text)["compound"])


def apply_vader(articles: list[Article]) -> list[Article]:
    for a in articles:
        if a.sentiment is None:  # filings already carry a rule-based score
            a.sentiment = round(score_text(f"{a.title}. {a.summary}"), 3)
            a.sentiment_method = "vader"
    return articles


def weighted_sentiment(articles: list[Article]) -> float | None:
    scored = [(a.sentiment, max(a.rank, 0.05)) for a in articles if a.sentiment is not None]
    if not scored:
        return None
    return round(sum(s * w for s, w in scored) / sum(w for _, w in scored), 3)
