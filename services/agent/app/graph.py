"""The morning-brief agent, as a LangGraph workflow.

    plan ──► gather_news (one branch per company / sector / macro topic, in parallel)
               │
             join ──► analyze_pick    (one per buy candidate)   ─┐
                  ├─► analyze_exit    (one per holding)          ├─► compose ──► END
                  └─► analyze_sectors (sector rotation + macro)  ─┘

Every LLM step has a deterministic rules-based fallback, so a brief is always produced.
The LLM refers to articles only by id; `compose` maps ids back to real URLs, so a
link in the output can never be invented.
"""
from __future__ import annotations

import logging
import operator
import re
from datetime import date, datetime, timezone
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .config import get_settings
from .llm import get_llm
from .news import sources
from .news.models import Article
from .news.sentiment import apply_vader, weighted_sentiment
from .news.trust import name_terms, rank_and_filter
from .schemas import (
    ArticleAssessment,
    BriefRequest,
    Candidate,
    ExitAnalysis,
    HoldingIn,
    PickAnalysis,
    SectorBriefAnalysis,
    SectorStance,
)

log = logging.getLogger(__name__)

SECTOR_TERMS = {
    "Technology": ["tech", "technology", "semiconductor", "chip", "chips", "software", "AI", "cloud"],
    "Healthcare": ["health", "healthcare", "pharma", "biotech", "drug", "medical", "FDA"],
    "Financial Services": ["bank", "banks", "financial", "lender", "insurer", "Fed", "rates", "credit"],
    "Energy": ["oil", "energy", "crude", "natural gas", "OPEC", "refiner"],
    "Industrials": ["industrial", "manufacturing", "aerospace", "defense", "transport", "railroad", "airline"],
    "Consumer Cyclical": ["retail", "consumer", "auto", "automaker", "housing", "travel", "restaurant"],
    "Consumer Defensive": ["staples", "grocery", "food", "beverage", "household"],
    "Utilities": ["utility", "utilities", "power", "electricity", "grid"],
    "Basic Materials": ["materials", "metals", "mining", "chemical", "copper", "gold", "steel"],
    "Real Estate": ["real estate", "REIT", "property", "mortgage", "housing"],
    "Communication Services": ["media", "telecom", "streaming", "advertising", "social media"],
}
MACRO_TOPIC = "macro"
FX_TOPIC = "fx"

SYSTEM = (
    "You are a careful equity research analyst. Your reader lives in India and invests in US stocks with rupees, "
    "for the long term, with a modest portfolio. Base every statement on the quantitative data and the numbered "
    "articles provided. Cite articles only by their ids in square brackets, e.g. [A2]. Never invent facts, figures, "
    "events or sources; if the news is thin, old or irrelevant, say so plainly and lean on the quantitative data. "
    "Weigh trusted sources and official SEC filings above opinion pieces. Be concise and specific. "
    "This is research to support the reader's own decision, not personalised financial advice."
)


# ---------------------------------------------------------------- state

def _merge(a: dict, b: dict) -> dict:
    return {**a, **b}


class BriefState(TypedDict, total=False):
    request: dict[str, Any]
    articles: Annotated[dict[str, list[dict]], _merge]
    picks: Annotated[list[dict], operator.add]
    exits: Annotated[list[dict], operator.add]
    sector_view: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]
    llm: dict[str, str]
    brief: dict[str, Any]


# ---------------------------------------------------------------- helpers

def _req(state: dict) -> BriefRequest:
    return BriefRequest.model_validate(state["request"])


def _label(articles: list[Article]) -> tuple[str, dict[str, Article]]:
    """Numbered article list for a prompt, plus the id -> article map used to resolve citations."""
    lines, mapping = [], {}
    for i, a in enumerate(articles, start=1):
        key = f"A{i}"
        mapping[key] = a
        lines.append(
            f"[{key}] {a.publisher} · {a.published_at:%Y-%m-%d} · trust {a.trust:.2f} · {a.kind}\n"
            f"    {a.title}\n    {a.summary[:400]}"
        )
    return ("\n".join(lines) or "(no relevant articles found in the last few days)"), mapping


def _apply_assessments(mapping: dict[str, Article], assessments: list[ArticleAssessment]) -> None:
    for a in assessments:
        art = mapping.get(a.id.strip("[] "))
        if art is not None:
            art.sentiment = round(_clamp(a.sentiment, -1, 1), 3)
            art.sentiment_method = "llm"
            art.takeaway = a.takeaway
            art.relevance = round(_clamp(a.relevance, 0, 1), 2)


class Citer:
    """Rewrites the LLM's per-prompt ids ([A3]) into [1], [2]... matching one evidence list,
    so every citation in the prose points at a real, linked article. Unknown ids are dropped."""

    def __init__(self, mapping: dict[str, Article], preferred: list[str] | None = None):
        self.mapping = mapping
        self.evidence: list[dict] = []
        self._num: dict[str, int] = {}
        for i in preferred or []:
            self._ref(i)

    def _ref(self, raw: str) -> int | None:
        art = self.mapping.get(raw.strip("[] "))
        if art is None:
            return None
        if art.id not in self._num:
            self.evidence.append(_public(art))
            self._num[art.id] = len(self.evidence)
        return self._num[art.id]

    def text(self, s: str) -> str:
        def repl(m: re.Match) -> str:  # handles [A1], (A1) and [A1, A3]
            nums = [n for n in (self._ref(x) for x in re.split(r"\s*,\s*", m.group(1))) if n]
            return " " + "".join(f"[{n}]" for n in nums) if nums else ""

        return re.sub(r"\s?[\[(](A\d+(?:\s*,\s*A\d+)*)[\])]", repl, s).strip()  # [A1] or (A1)

    def texts(self, items: list[str]) -> list[str]:
        return [t for t in (self.text(x) for x in items) if t]


def _public(a: Article) -> dict:
    return a.model_dump(mode="json", include={"id", "publisher", "title", "url", "published_at", "sentiment", "sentiment_method", "takeaway", "kind", "trust", "source_api"})


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


def _pct(v: float | None, signed: bool = True) -> str:
    return "n/a" if v is None else f"{v * 100:+.1f}%" if signed else f"{v * 100:.1f}%"


def sentiment_label(s: float | None) -> str:
    if s is None:
        return "No news"
    return "Positive" if s >= 0.25 else "Slightly positive" if s >= 0.05 else "Negative" if s <= -0.25 else "Slightly negative" if s <= -0.05 else "Neutral"


def _fx_move(v: float | None, period: str) -> str:
    if v is None:
        return ""
    if abs(v) < 0.001:
        return f"the rupee was flat against the dollar over {period}"
    return f"the rupee {'weakened' if v > 0 else 'strengthened'} {abs(v) * 100:.1f}% against the dollar over {period}"


def _fx_line(fx: dict) -> str:
    """Plain-language FX facts. Stated explicitly because 'USD/INR +3%' is easy to misread."""
    if not fx:
        return "USD/INR data unavailable."
    moves = [m for m in (_fx_move(fx.get("ret_1m"), "1 month"), _fx_move(fx.get("ret_3m"), "3 months"), _fx_move(fx.get("ret_1y"), "1 year")) if m]
    return (
        f"1 US dollar = {fx.get('rate', 'n/a')} rupees. " + ("; ".join(moves) + ". " if moves else "")
        + "A weakening rupee ADDS to an Indian investor's rupee returns on US stocks; a strengthening rupee SUBTRACTS from them. "
        f"Assume about {fx.get('markup_pct', 1.0)}% FX cost each way."
    )


def inr_note(fx: dict) -> str:
    """Deterministic INR guidance - numbers from code, never from the LLM."""
    if not fx:
        return "USD/INR data unavailable."
    y = fx.get("ret_1y")
    effect = (
        f"Over the last year that currency move alone added about {y * 100:.1f}% to rupee returns on US holdings."
        if y and y > 0 else
        f"Over the last year that currency move alone cost about {abs(y) * 100:.1f}% of rupee returns on US holdings."
        if y and y < 0 else ""
    )
    trend = fx.get("trend", "")
    return (
        f"1 USD = ₹{fx.get('rate')}: {_fx_move(fx.get('ret_1y'), '1 year') or 'no 1-year data'}. {effect} "
        f"Trend: {trend.lower()} (vs 200-day average). Converting costs ~{fx.get('markup_pct', 1.0)}% each way, so a round trip needs "
        f"~{2 * fx.get('markup_pct', 1.0):.1f}% of gains just to break even - favour fewer, longer-held positions over frequent trading."
    ).strip()


# ---------------------------------------------------------------- nodes

def plan(state: BriefState) -> dict:
    llm = get_llm()
    return {"llm": {"provider": llm.name, "model": llm.model}}


def fan_out_news(state: BriefState) -> list[Send]:
    req = _req(state)
    tasks: list[dict] = []
    seen: set[str] = set()
    for c in [*req.candidates, *req.holdings]:
        if c.symbol not in seen:
            seen.add(c.symbol)
            tasks.append({"kind": "company", "topic": c.symbol, "terms": name_terms(c.symbol, c.name)})
    for s in req.sectors:
        tasks.append({"kind": "sector", "topic": f"sector:{s.sector}", "etf": s.etf, "terms": SECTOR_TERMS.get(s.sector, [s.sector])})
    tasks.append({"kind": "macro", "topic": MACRO_TOPIC, "terms": []})
    tasks.append({"kind": "fx", "topic": FX_TOPIC, "terms": ["rupee", "INR", "RBI", "dollar", "Fed"]})
    return [Send("gather_news", {"task": t, "as_of": req.as_of.isoformat()}) for t in tasks]


def gather_news(payload: dict) -> dict:
    s = get_settings()
    task, as_of = payload["task"], date.fromisoformat(payload["as_of"])
    topic, kind = task["topic"], task["kind"]
    raw: list[Article] = []
    try:
        if kind == "company":
            raw += sources.yahoo_news(topic)
            raw += sources.finnhub_company_news(topic, as_of)
            raw += sources.sec_filings(topic, as_of)
            limit = s.max_articles_per_symbol
        elif kind == "sector":
            raw += sources.yahoo_news(task["etf"], topic=topic)
            limit = 5
        elif kind == "macro":
            raw += sources.yahoo_news("SPY", topic=topic) + sources.yahoo_news("^GSPC", topic=topic)
            raw += sources.finnhub_market_news(topic)
            limit = s.max_articles_per_topic
        else:  # fx
            raw += sources.yahoo_news("INR=X", topic=topic)
            limit = 4
    except Exception as exc:  # noqa: BLE001
        log.exception("news gathering failed for %s", topic)
        return {"errors": [f"news {topic}: {exc}"]}

    for a in raw:
        a.topic = topic
    kept = apply_vader(rank_and_filter(raw, task["terms"], limit, s.min_source_trust))
    return {"articles": {topic: [a.model_dump(mode="json") for a in kept]}}


def join(state: BriefState) -> dict:
    return {}


def fan_out_analysis(state: BriefState) -> list[Send]:
    req = _req(state)
    arts = state.get("articles", {})
    base = {"llm": state.get("llm", {}), "regime": req.regime, "fx": req.fx}
    sends = [Send("analyze_pick", {**base, "candidate": c.model_dump(mode="json"), "articles": arts.get(c.symbol, [])}) for c in req.candidates]
    sends += [Send("analyze_exit", {**base, "holding": h.model_dump(mode="json"), "articles": arts.get(h.symbol, [])}) for h in req.holdings]
    sends.append(
        Send(
            "analyze_sectors",
            {
                **base,
                "sectors": [x.model_dump(mode="json") for x in req.sectors],
                "sector_articles": {k: v for k, v in arts.items() if k.startswith("sector:")},
                "macro": arts.get(MACRO_TOPIC, []),
                "fx_news": arts.get(FX_TOPIC, []),
            },
        )
    )
    return sends


def analyze_pick(payload: dict) -> dict:
    c = Candidate.model_validate(payload["candidate"])
    articles = [Article.model_validate(a) for a in payload["articles"]]
    listing, mapping = _label(articles)
    m = c.metrics
    prompt = f"""Evaluate {c.symbol} ({c.name or 'n/a'}; {c.sector or 'n/a'}; {c.cap_category or 'n/a'} cap) as a buy today ({payload['regime'].get('label')} market).

QUANTITATIVE MODEL (rank #{c.rank}, score {c.score:.1f}/100, rating {c.rating})
Component scores: {', '.join(f'{k} {v:.0f}' for k, v in c.components.items())}
Price ${c.price:,.2f}; stop-loss ${c.stop_loss or 0:,.2f}; 12-1m return {_pct(m.get('ret_12m_ex1m'))}; 3m {_pct(m.get('ret_3m'))}; vs S&P 6m {_pct(m.get('rs_6m'))}; RSI {m.get('rsi14') or 'n/a'}; volatility {_pct(m.get('volatility_3m'), False)}; max drawdown 1y {_pct(m.get('max_drawdown_1y'))}.
Model reasons: {' | '.join(c.reasons) or 'none'}
Model cautions: {' | '.join(c.cautions) or 'none'}
Currency: {_fx_line(payload['fx'])}

NEWS AND FILINGS (last few days)
{listing}

Assess each article's impact, then decide conviction. Downgrade conviction if credible news contradicts the quantitative picture (e.g. guidance cut, investigation, restatement). Mention the INR angle only if it materially changes the case."""
    result = get_llm().structured(SYSTEM, prompt, PickAnalysis)

    vader = weighted_sentiment(articles)
    if result is not None:
        _apply_assessments(mapping, result.article_assessments)
        news = _clamp(result.news_sentiment, -1, 1) if articles else None
        cite = Citer(mapping, result.evidence_ids)
        out = {
            "method": "llm",
            "conviction": result.conviction,
            "thesis": cite.text(result.thesis),
            "catalysts": cite.texts(result.catalysts),
            "risks": cite.texts(result.risks),
        }
        out["evidence"] = cite.evidence or [_public(a) for a in articles[:3]]
    else:
        news = vader
        conviction = (
            "High" if c.score >= 78 and (news or 0) >= -0.1 else
            "Medium" if c.score >= 65 and (news or 0) > -0.3 else
            "Low" if c.score >= 45 else "Avoid"
        )
        top = articles[0] if articles else None
        news_line = (
            f" News flow is {sentiment_label(news).lower()} across {len(articles)} recent articles; most relevant: \"{top.title}\" ({top.publisher})."
            if top else " No relevant news in the last few days, so this rests on price and fundamentals alone."
        )
        out = {
            "method": "rules",
            "conviction": conviction,
            "thesis": f"{c.symbol} ranks #{c.rank} with a quantitative score of {c.score:.0f}/100 ({c.rating}). " + " ".join(c.reasons[:3]) + news_line,
            "catalysts": [a.title for a in articles if (a.sentiment or 0) > 0.2][:3],
            "risks": c.cautions[:3] + [a.title for a in articles if (a.sentiment or 0) < -0.2][:2],
            "evidence": [_public(a) for a in articles[:3]],
        }

    adjusted = round(c.score + 8 * (news or 0), 2)
    buyable = c.rating in ("Strong Buy", "Buy")
    # The verdict rests on the numbers and the measured news tone; the LLM's conviction can veto
    # ("Avoid") but a small model's hedged "Low" alone doesn't overturn strong, positively-covered data.
    news_risk = news is not None and news <= -0.3
    if buyable and (news_risk or out["conviction"] == "Avoid"):
        verdict = "Wait - news risk"
    elif buyable and c.rating == "Strong Buy" and (news is None or news >= -0.1) and out["conviction"] in ("High", "Medium"):
        verdict = "Strong pick"
    elif buyable:
        verdict = "Pick"
    else:
        verdict = "Watch"
    return {
        "picks": [
            {
                **c.model_dump(mode="json", include={"symbol", "name", "sector", "cap_category", "rank", "score", "rating", "price", "target_weight", "stop_loss"}),
                **out,
                "news_sentiment": news,
                "vader_sentiment": vader,
                "sentiment_label": sentiment_label(news),
                "adjusted_score": adjusted,
                "verdict": verdict,
                "articles": [_public(a) for a in articles],
            }
        ]
    }


def analyze_exit(payload: dict) -> dict:
    h = HoldingIn.model_validate(payload["holding"])
    articles = [Article.model_validate(a) for a in payload["articles"]]
    listing, mapping = _label(articles)
    sig = h.signal
    prompt = f"""The reader holds {h.quantity:g} shares of {h.symbol} ({h.name or 'n/a'}; {h.sector or 'n/a'}) bought at ${h.avg_cost:,.2f}.
Current price ${h.price or 0:,.2f}. Gain/loss in USD {_pct(h.pnl_pct)}; in INR {_pct(h.pnl_inr_pct)} (FX effect ₹{h.fx_gain_inr or 0:,.0f}).

QUANTITATIVE EXIT SIGNAL: {sig.get('action', 'n/a')} (exit points {sig.get('exit_points')}, hold points {sig.get('hold_points')})
Current model rating {sig.get('rating', 'n/a')}, score {sig.get('score', 'n/a')}; trailing stop ${sig.get('trailing_stop') or 0:,.2f}.
Signals favouring exit: {' | '.join(sig.get('reasons_to_exit', [])) or 'none'}
Signals favouring hold: {' | '.join(sig.get('reasons_to_hold', [])) or 'none'}
Market: {payload['regime'].get('label')}. Currency: {_fx_line(payload['fx'])}

NEWS AND FILINGS
{listing}

Decide Add / Hold / Trim / Exit. Respect hard risk signals (trailing stop hit, confirmed downtrend) unless the evidence clearly argues otherwise, and say why. Consider the INR gain and the cost of re-entering (FX markup) before recommending a full exit on a small signal."""
    result = get_llm().structured(SYSTEM, prompt, ExitAnalysis)
    vader = weighted_sentiment(articles)
    base = {
        **h.model_dump(mode="json", exclude={"signal"}),
        "quant_action": sig.get("action"),
        "signal": sig,
        "articles": None,
    }
    if result is not None:
        _apply_assessments(mapping, result.article_assessments)
        cite = Citer(mapping, result.evidence_ids)
        base.update(
            method="llm", action=result.action, confidence=result.confidence, rationale=cite.text(result.rationale),
            # Factual reasons come from the rules; the LLM contributes only points it backs with an article.
            reasons_to_exit=sig.get("reasons_to_exit", []) + [t for t in cite.texts(result.reasons_to_exit) if re.search(r"\[\d+\]", t)],
            reasons_to_hold=sig.get("reasons_to_hold", []) + [t for t in cite.texts(result.reasons_to_hold) if re.search(r"\[\d+\]", t)],
            news_sentiment=_clamp(result.news_sentiment, -1, 1) if articles else None,
        )
        base["evidence"] = cite.evidence or [_public(a) for a in articles[:3]]
    else:
        action = sig.get("action", "Hold")
        if action == "Hold" and vader is not None and vader <= -0.35:
            action = "Trim"
        base.update(
            method="rules", action=action, confidence="Medium",
            rationale=(
                f"Quantitative exit signal is {sig.get('action', 'Hold')}. "
                + (" ".join(sig.get("reasons_to_exit", [])[:2]) or "No exit triggers fired.")
                + f" News sentiment is {sentiment_label(vader).lower()}."
            ),
            reasons_to_exit=sig.get("reasons_to_exit", []), reasons_to_hold=sig.get("reasons_to_hold", []),
            news_sentiment=vader, evidence=[_public(a) for a in articles[:3]],
        )
    base["sentiment_label"] = sentiment_label(base["news_sentiment"])
    base["articles"] = [_public(a) for a in articles]
    return {"exits": [base]}


def analyze_sectors(payload: dict) -> dict:
    sectors = payload["sectors"]
    pool: list[Article] = []
    for topic in [f"sector:{s['sector']}" for s in sectors[:4] + sectors[-3:]]:  # leaders and laggards
        pool += [Article.model_validate(a) for a in payload["sector_articles"].get(topic, [])[:3]]
    pool += [Article.model_validate(a) for a in payload["macro"][:6]]
    pool += [Article.model_validate(a) for a in payload["fx_news"][:3]]
    uniq = list({a.id: a for a in pool}.values())
    listing, mapping = _label(uniq)

    table = "\n".join(
        f"{s['rank']:>2}. {s['sector']} ({s['etf']}): 1w {_pct(s.get('ret_1w'))}, 1m {_pct(s.get('ret_1m'))}, 3m {_pct(s.get('ret_3m'))}, "
        f"vs S&P 1m {_pct(s.get('rs_1m'))} 3m {_pct(s.get('rs_3m'))}, rotation {s['quadrant']}, "
        f"{_pct(s.get('breadth_50'), False)} of stocks above 50-day, avg model score {s.get('avg_score') or 'n/a'}, "
        f"buys {s.get('buy_count')}/{s.get('stock_count')}, top names {', '.join(s.get('top_symbols', [])) or '-'}"
        for s in sectors
    )
    regime = payload["regime"]
    prompt = f"""Write today's sector briefing.

MARKET REGIME: {regime.get('label')} - {regime.get('summary', '')}
CURRENCY: {_fx_line(payload['fx'])}

SECTOR STATISTICS (ranked; 'rotation' uses relative strength vs the S&P 500: Leading = strong and strengthening,
Weakening = strong but fading, Improving = weak but recovering, Lagging = weak and fading)
{table}

NEWS
{listing}

Give every one of the {len(sectors)} sectors a stance, using the sector names exactly as listed. The headline must state the day's key takeaway (not a title or a date). Explain which sectors deserve new money now and why, with the statistics as proof and articles as evidence. Name 1-3 example stocks from 'top names' for Overweight sectors."""
    result = get_llm().structured(SYSTEM, prompt, SectorBriefAnalysis)

    by_name = {s["sector"]: s for s in sectors}
    sector_cites: dict[str, Citer] = {}

    def canon(name: str) -> str | None:
        n = name.lower().split("(")[0].strip()
        for real in by_name:
            if n == real.lower() or n.startswith(real.lower()) or real.lower().startswith(n):
                return real
        return None

    def consistent(stance: str, quadrant: str) -> bool:
        """Reject a stance that contradicts the measured rotation (a small model sometimes misreads the table)."""
        return not ((quadrant == "Leading" and stance == "Underweight") or (quadrant == "Lagging" and stance == "Overweight"))

    rules_stances = {}
    for s_ in sectors:
        stance = {"Leading": "Overweight", "Improving": "Overweight" if (s_.get("rs_1m") or 0) > 0.01 else "Neutral", "Weakening": "Neutral"}.get(s_["quadrant"], "Underweight")
        rules_stances[s_["sector"]] = SectorStance(
            sector=s_["sector"], stance=stance, evidence_ids=[],
            rationale=f"{s_['quadrant']} vs the S&P 500: {_pct(s_.get('rs_3m'))} relative over 3 months and {_pct(s_.get('rs_1m'))} over 1 month; "
            f"{_pct(s_.get('breadth_50'), False)} of its tracked stocks are above their 50-day average.",
        )

    if result is not None:
        stances = dict(rules_stances)
        for x in result.sectors:
            real = canon(x.sector)
            if real and x.rationale.strip() and consistent(x.stance, by_name[real]["quadrant"]):
                x.sector = real
                stances[real] = x
        cite = Citer(mapping, result.evidence_ids)
        view = {
            "method": "llm",
            "headline": cite.text(result.headline),
            "market_narrative": cite.text(result.market_narrative),
            "key_risks": cite.texts(result.key_risks),
            "inr_investor_note": inr_note(payload["fx"]),
        }
        view["evidence"] = cite.evidence
        for x in result.sectors:
            c = Citer(mapping, x.evidence_ids)
            x.rationale = c.text(x.rationale)
            sector_cites[x.sector] = c
    else:
        stances = rules_stances
        leaders = [s["sector"] for s in sectors[:3]]
        laggards = [s["sector"] for s in sectors[-2:]]
        fx = payload["fx"]
        view = {
            "method": "rules",
            "headline": f"Leadership: {', '.join(leaders)}. Lagging: {', '.join(laggards)}. Market {regime.get('label')}.",
            "market_narrative": regime.get("summary", "") + (f" Top market headline: \"{uniq[0].title}\" ({uniq[0].publisher})." if uniq else ""),
            "key_risks": [a.title for a in uniq if (a.sentiment or 0) < -0.3][:3],
            "inr_investor_note": inr_note(fx),
            "evidence": [_public(a) for a in uniq[:4]],
        }
    view["sectors"] = [
        {
            **s,
            "stance": stances[s["sector"]].stance if s["sector"] in stances else "Neutral",
            "rationale": stances[s["sector"]].rationale if s["sector"] in stances else "",
            "evidence": sector_cites[s["sector"]].evidence if s["sector"] in sector_cites else [],
            "news_sentiment": weighted_sentiment([Article.model_validate(a) for a in payload["sector_articles"].get(f"sector:{s['sector']}", [])]),
        }
        for s in by_name.values()
    ]
    return {"sector_view": [view]}


def compose(state: BriefState) -> dict:
    req = _req(state)
    picks = sorted(state.get("picks", []), key=lambda p: ({"Strong pick": 0, "Pick": 1, "Wait - news risk": 2, "Watch": 3}[p["verdict"]], -p["adjusted_score"]))
    all_articles = [a for group in state.get("articles", {}).values() for a in group]
    by_source: dict[str, int] = {}
    for a in all_articles:
        by_source[a["source_api"]] = by_source.get(a["source_api"], 0) + 1
    return {
        "brief": {
            "as_of": req.as_of.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "llm": state.get("llm", {}),
            "regime": req.regime,
            "fx": req.fx,
            "market": (state.get("sector_view") or [{}])[0],
            "picks": picks,
            "exits": state.get("exits", []),
            "articles": all_articles,
            "stats": {"articles": len(all_articles), "by_source": by_source, "finnhub_enabled": bool(get_settings().finnhub_api_key)},
            "errors": state.get("errors", []),
        }
    }


def build_graph():
    g = StateGraph(BriefState)
    g.add_node("plan", plan)
    g.add_node("gather_news", gather_news)
    g.add_node("join", join)
    g.add_node("analyze_pick", analyze_pick)
    g.add_node("analyze_exit", analyze_exit)
    g.add_node("analyze_sectors", analyze_sectors)
    g.add_node("compose", compose)
    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", fan_out_news, ["gather_news"])
    g.add_edge("gather_news", "join")
    g.add_conditional_edges("join", fan_out_analysis, ["analyze_pick", "analyze_exit", "analyze_sectors"])
    for node in ("analyze_pick", "analyze_exit", "analyze_sectors"):
        g.add_edge(node, "compose")
    g.add_edge("compose", END)
    return g.compile()


GRAPH = build_graph()


def run_brief(req: BriefRequest) -> dict[str, Any]:
    state = GRAPH.invoke(
        {"request": req.model_dump(mode="json"), "articles": {}, "picks": [], "exits": [], "sector_view": [], "errors": []},
        config={"max_concurrency": max(get_settings().llm_concurrency, 1) * 2},
    )
    return state["brief"]
