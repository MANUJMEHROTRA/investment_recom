"""Source reputation and relevance filtering - the "pick relevant news" step."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from .models import Article

# 1.0 = primary / top-tier newsroom, lower = aggregators and opinion sites.
TRUST = {
    "sec edgar": 1.0, "reuters": 1.0, "bloomberg": 1.0, "the wall street journal": 1.0, "wsj": 1.0,
    "financial times": 1.0, "associated press": 1.0, "ap": 1.0, "cnbc": 0.95, "barron's": 0.95,
    "marketwatch": 0.9, "the economist": 0.95, "yahoo finance": 0.85, "morningstar": 0.85,
    "investor's business daily": 0.8, "fortune": 0.8, "forbes": 0.75, "business insider": 0.75,
    "axios": 0.8, "the new york times": 0.95, "cnn business": 0.8, "fox business": 0.7,
    "investopedia": 0.75, "thestreet": 0.65, "kiplinger": 0.75, "benzinga": 0.6, "motley fool": 0.55,
    "the motley fool": 0.55, "seeking alpha": 0.55, "zacks": 0.5, "gurufocus": 0.5, "simply wall st": 0.5,
    "investorplace": 0.4, "insider monkey": 0.3, "24/7 wall st.": 0.45,
}


def trust_of(publisher: str) -> float:
    p = publisher.strip().lower()
    if p in TRUST:
        return TRUST[p]
    for name, score in TRUST.items():
        if len(name) > 3 and name in p:
            return score
    return 0.5


def _mentions(text: str, terms: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(t)}\b", text, re.IGNORECASE) for t in terms if t)


def rank_and_filter(articles: list[Article], terms: list[str], limit: int, min_trust: float, now: datetime | None = None) -> list[Article]:
    """Dedupe, score each article by trust x relevance x recency, keep the best `limit`."""
    now = now or datetime.now(timezone.utc)
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    kept: list[Article] = []
    for a in articles:
        title_key = re.sub(r"\W+", " ", a.title.lower()).strip()[:80]
        if a.url in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(a.url)
        seen_titles.add(title_key)

        a.trust = trust_of(a.publisher)
        if a.trust < min_trust:
            continue
        if a.kind != "news" or not terms:
            a.relevance = 1.0
        elif _mentions(a.title, terms):
            a.relevance = 1.0
        elif _mentions(a.summary, terms):
            a.relevance = 0.75
        else:
            a.relevance = 0.4  # returned by a ticker-specific endpoint but doesn't name the company
        if a.relevance < 0.5:
            continue
        published = a.published_at if a.published_at.tzinfo else a.published_at.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now - published).total_seconds() / 86400)
        a.rank = round(a.trust * a.relevance * math.exp(-age_days / 3), 4)
        kept.append(a)
    kept.sort(key=lambda x: x.rank, reverse=True)
    return kept[:limit]


def name_terms(symbol: str, name: str | None) -> list[str]:
    """Search terms for relevance: the ticker plus the distinctive part of the company name."""
    terms = [symbol.replace("-", ".") if "-" in symbol else symbol]
    if name:
        cleaned = re.sub(r"[,.]|\b(inc|corp|corporation|company|co|ltd|plc|holdings|group|class [ab]|the)\b", " ", name, flags=re.IGNORECASE)
        words = [w for w in cleaned.split() if len(w) > 1]
        if words:
            terms.append(words[0])
            if len(words) > 1:
                terms.append(" ".join(words[:2]))
    return terms
