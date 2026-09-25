from datetime import date, datetime, timedelta, timezone

import pytest

from app import graph
from app.news import sources
from app.news.models import Article
from app.news.sentiment import score_text
from app.news.trust import name_terms, rank_and_filter, trust_of
from app.schemas import BriefRequest, ExitAnalysis, PickAnalysis, SectorBriefAnalysis

NOW = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)


def art(title, publisher="Reuters", url=None, days=0, summary="", topic="AAPL"):
    url = url or f"https://example.com/{abs(hash(title))}"
    return Article(id=Article.make_id(url), topic=topic, source_api="yahoo", publisher=publisher, title=title,
                   summary=summary, url=url, published_at=NOW - timedelta(days=days))


def test_trust_and_relevance_filtering():
    items = [
        art("Apple beats estimates on iPhone demand"),
        art("Apple beats estimates on iPhone demand"),  # duplicate title
        art("Five stocks to buy now", publisher="Insider Monkey"),  # low trust
        art("Markets drift ahead of Fed", publisher="CNBC"),  # does not mention Apple
        art("Apple faces EU probe", publisher="Bloomberg", days=6),
    ]
    kept = rank_and_filter(items, name_terms("AAPL", "Apple Inc."), limit=10, min_trust=0.4, now=NOW)
    titles = [a.title for a in kept]
    assert titles == ["Apple beats estimates on iPhone demand", "Apple faces EU probe"]
    assert kept[0].rank > kept[1].rank  # newer ranks higher
    assert trust_of("Reuters") == 1.0 and trust_of("Some Blog") == 0.5


def test_finance_sentiment_direction():
    assert score_text("Nvidia beats estimates and raises guidance") > 0.3
    assert score_text("Shares plunge after downgrade and fraud probe") < -0.3


@pytest.fixture()
def request_payload():
    return BriefRequest.model_validate({
        "as_of": "2026-09-25",
        "regime": {"label": "Risk-On", "summary": "Uptrend."},
        "fx": {"rate": 88.2, "ret_1m": 0.004, "ret_3m": 0.012, "ret_1y": 0.035, "markup_pct": 1.0},
        "candidates": [
            {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Technology", "rank": 1, "score": 85, "rating": "Strong Buy", "price": 335.0,
             "reasons": ["Established uptrend."], "cautions": []},
            {"symbol": "XOM", "name": "Exxon Mobil", "sector": "Energy", "rank": 2, "score": 70, "rating": "Buy", "price": 110.0},
        ],
        "holdings": [
            {"symbol": "INTC", "name": "Intel", "quantity": 10, "avg_cost": 40, "price": 25, "pnl_pct": -0.375,
             "signal": {"action": "Exit", "exit_points": 6, "hold_points": 0, "reasons_to_exit": ["Trailing stop hit."], "reasons_to_hold": []}},
        ],
        "sectors": [
            {"sector": "Technology", "etf": "XLK", "rank": 1, "quadrant": "Leading", "rs_1m": 0.02, "rs_3m": 0.05},
            {"sector": "Energy", "etf": "XLE", "rank": 2, "quadrant": "Lagging", "rs_1m": -0.02, "rs_3m": -0.04},
        ],
    })


@pytest.fixture()
def fake_sources(monkeypatch):
    def yahoo(symbol, topic=None):
        t = topic or symbol
        if symbol == "XOM":
            return [art("Exxon shares plunge after fraud probe and downgrade", url="https://news/xom", topic=t)]
        if symbol == "AAPL":
            return [art("Apple beats estimates and raises outlook", url="https://news/aapl", topic=t)]
        return [art(f"Markets rally as tech stocks surge ({symbol})", url=f"https://news/{symbol}", topic=t, publisher="CNBC")]

    monkeypatch.setattr(sources, "yahoo_news", yahoo)
    monkeypatch.setattr(sources, "finnhub_company_news", lambda s, d: [])
    monkeypatch.setattr(sources, "finnhub_market_news", lambda topic="macro": [])
    monkeypatch.setattr(sources, "sec_filings", lambda s, d: [])


class NoLLM:
    name, model = "none", "rules-only"

    def structured(self, system, prompt, schema):
        return None


class FakeLLM:
    """Returns schema-valid answers and cites one real id and one hallucinated id."""
    name, model = "fake", "fake-1"

    def structured(self, system, prompt, schema):
        if schema is PickAnalysis:
            return PickAnalysis(article_assessments=[{"id": "A1", "sentiment": 0.9, "relevance": 1, "takeaway": "Strong quarter."}],
                                news_sentiment=0.7, conviction="High", thesis="Strong [A1].", catalysts=["Earnings [A1]"], risks=[],
                                evidence_ids=["A1", "A99"])
        if schema is ExitAnalysis:
            return ExitAnalysis(article_assessments=[], news_sentiment=-0.2, action="Exit", confidence="High", rationale="Downtrend.",
                                reasons_to_exit=["Trailing stop hit."], reasons_to_hold=[], evidence_ids=[])
        return SectorBriefAnalysis(headline="Tech leads.", market_narrative="Rally [A1].", sectors=[
            {"sector": "Technology", "stance": "Overweight", "rationale": "Leading [A1].", "evidence_ids": ["A1"]}],
            key_risks=[], inr_investor_note="Dollar firm.", evidence_ids=["A1"])


def test_brief_rules_fallback(monkeypatch, request_payload, fake_sources):
    monkeypatch.setattr(graph, "get_llm", lambda: NoLLM())
    brief = graph.run_brief(request_payload)
    picks = {p["symbol"]: p for p in brief["picks"]}
    assert picks["AAPL"]["verdict"] == "Strong pick"
    assert picks["XOM"]["verdict"] == "Wait - news risk"  # buy-rated, but credible negative news
    assert picks["AAPL"]["evidence"][0]["url"] == "https://news/aapl"
    assert brief["exits"][0]["action"] == "Exit"
    assert {s["sector"] for s in brief["market"]["sectors"]} == {"Technology", "Energy"}
    assert brief["llm"]["provider"] == "none"


def test_brief_llm_citations_resolve_only_to_real_articles(monkeypatch, request_payload, fake_sources):
    monkeypatch.setattr(graph, "get_llm", lambda: FakeLLM())
    brief = graph.run_brief(request_payload)
    aapl = next(p for p in brief["picks"] if p["symbol"] == "AAPL")
    assert aapl["method"] == "llm"
    assert [e["url"] for e in aapl["evidence"]] == ["https://news/aapl"]  # "A99" was dropped
    assert aapl["articles"][0]["sentiment_method"] == "llm"
    tech = next(s for s in brief["market"]["sectors"] if s["sector"] == "Technology")
    assert tech["stance"] == "Overweight" and tech["evidence"]


def test_citer_renumbers_and_drops_unknown_ids():
    a1, a2 = art("One", url="https://x/1"), art("Two", url="https://x/2")
    c = graph.Citer({"A1": a1, "A2": a2})
    assert c.text("Growth [A2] and margins [A1, A2]; rumour [A9].") == "Growth [1] and margins [2][1]; rumour."
    assert c.text("Buyback (A1)") == "Buyback [2]"
    assert [e["url"] for e in c.evidence] == ["https://x/2", "https://x/1"]


def test_fx_wording_states_rupee_direction_explicitly():
    weak_rupee = {"rate": 95.9, "ret_1m": 0.005, "ret_3m": 0.012, "ret_1y": 0.081, "markup_pct": 1.0, "trend": "Dollar strengthening"}
    assert "rupee weakened 8.1% against the dollar over 1 year" in graph._fx_line(weak_rupee)
    assert "added about 8.1%" in graph.inr_note(weak_rupee)
    assert "cost about 2.0%" in graph.inr_note({**weak_rupee, "ret_1y": -0.02})


def test_small_model_low_conviction_does_not_override_positive_data(monkeypatch, request_payload, fake_sources):
    class HedgingLLM(FakeLLM):
        def structured(self, system, prompt, schema):
            r = super().structured(system, prompt, schema)
            if schema is PickAnalysis:
                r.conviction = "Low"
            return r

    monkeypatch.setattr(graph, "get_llm", lambda: HedgingLLM())
    brief = graph.run_brief(request_payload)
    aapl = next(p for p in brief["picks"] if p["symbol"] == "AAPL")
    assert aapl["verdict"] == "Pick"  # positive news + Strong Buy; hedged conviction only blocks "Strong pick"


def test_llm_sector_stance_contradicting_data_is_replaced(monkeypatch, request_payload, fake_sources):
    class ContraryLLM(FakeLLM):
        def structured(self, system, prompt, schema):
            r = super().structured(system, prompt, schema)
            if schema is SectorBriefAnalysis:
                r.sectors[0].stance = "Underweight"  # Technology is "Leading" in the data
                r.sectors[0].rationale = "Tech is lagging."
            return r

    monkeypatch.setattr(graph, "get_llm", lambda: ContraryLLM())
    tech = next(s for s in graph.run_brief(request_payload)["market"]["sectors"] if s["sector"] == "Technology")
    assert tech["stance"] == "Overweight" and "Leading" in tech["rationale"]
