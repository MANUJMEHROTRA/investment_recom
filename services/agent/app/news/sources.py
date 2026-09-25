"""Three free news sources.

* Yahoo Finance  - per-ticker headlines via the open-source yfinance library (no key)
* Finnhub        - company + general market news from wire services (free key, optional)
* SEC EDGAR      - official 8-K/10-Q/10-K filings and Form 4 insider trades (no key)
"""
from __future__ import annotations

import logging
import threading
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

import httpx
import yfinance as yf

from ..config import get_settings
from .models import Article

log = logging.getLogger(__name__)


def _dt(value) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


# ---------------------------------------------------------------- Yahoo Finance

def yahoo_news(symbol: str, topic: str | None = None) -> list[Article]:
    out: list[Article] = []
    try:
        # The default 10 items are often generic market pieces; a deeper pull finds the company-specific ones.
        items = yf.Ticker(symbol).get_news(count=40) or []
    except Exception:  # noqa: BLE001
        log.warning("yahoo news failed for %s", symbol, exc_info=True)
        return out
    for item in items:
        c = item.get("content", item)  # yfinance >=0.2.50 nests the payload under "content"
        url = ((c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url") or c.get("link"))
        title = c.get("title")
        if not url or not title or c.get("contentType") == "VIDEO":
            continue
        out.append(
            Article(
                id=Article.make_id(url),
                topic=topic or symbol,
                source_api="yahoo",
                publisher=(c.get("provider") or {}).get("displayName") or c.get("publisher") or "Yahoo Finance",
                title=title,
                summary=(c.get("summary") or "")[:600],
                url=url,
                published_at=_dt(c.get("pubDate") or c.get("providerPublishTime") or time.time()),
            )
        )
    return out


# ---------------------------------------------------------------- Finnhub

FINNHUB = "https://finnhub.io/api/v1"


def _finnhub_rows(rows: list[dict], topic: str) -> list[Article]:
    out = []
    for r in rows:
        url, title = r.get("url"), r.get("headline")
        if not url or not title:
            continue
        out.append(
            Article(
                id=Article.make_id(url),
                topic=topic,
                source_api="finnhub",
                publisher=r.get("source") or "Finnhub",
                title=title,
                summary=(r.get("summary") or "")[:600],
                url=url,
                published_at=_dt(r.get("datetime")),
            )
        )
    return out


def finnhub_company_news(symbol: str, as_of: date) -> list[Article]:
    key = get_settings().finnhub_api_key
    if not key:
        return []
    start = as_of - timedelta(days=get_settings().news_lookback_days)
    try:
        r = httpx.get(
            f"{FINNHUB}/company-news",
            params={"symbol": symbol, "from": start.isoformat(), "to": as_of.isoformat(), "token": key},
            timeout=20,
        )
        r.raise_for_status()
        return _finnhub_rows(r.json()[:40], symbol)
    except Exception:  # noqa: BLE001
        log.warning("finnhub company news failed for %s", symbol, exc_info=True)
        return []


def finnhub_market_news(topic: str = "macro") -> list[Article]:
    key = get_settings().finnhub_api_key
    if not key:
        return []
    try:
        r = httpx.get(f"{FINNHUB}/news", params={"category": "general", "token": key}, timeout=20)
        r.raise_for_status()
        return _finnhub_rows(r.json()[:60], topic)
    except Exception:  # noqa: BLE001
        log.warning("finnhub market news failed", exc_info=True)
        return []


# ---------------------------------------------------------------- SEC EDGAR

ITEM_8K = {
    "1.01": "Material definitive agreement", "1.02": "Termination of material agreement", "1.05": "Cybersecurity incident",
    "2.01": "Acquisition or disposition of assets", "2.02": "Results of operations (earnings)", "2.03": "New financial obligation",
    "2.05": "Restructuring / exit costs", "2.06": "Material impairment", "3.01": "Delisting / listing-standard notice",
    "4.01": "Change of auditor", "4.02": "Prior financials should no longer be relied upon", "5.02": "Director or officer change",
    "5.03": "Bylaw / fiscal-year change", "5.07": "Shareholder vote results", "7.01": "Regulation FD disclosure", "8.01": "Other material events",
}
RED_FLAG_ITEMS = {"1.05", "2.06", "3.01", "4.01", "4.02", "2.05"}

_sec_lock = threading.Lock()
_cik_map: dict[str, int] = {}


def _sec_get(url: str) -> httpx.Response:
    # SEC fair-access policy: identify yourself and stay under 10 requests/second.
    with _sec_lock:
        time.sleep(0.15)
        r = httpx.get(url, headers={"User-Agent": get_settings().sec_user_agent}, timeout=20)
    r.raise_for_status()
    return r


def _cik(symbol: str) -> int | None:
    if not _cik_map:
        data = _sec_get("https://www.sec.gov/files/company_tickers.json").json()
        _cik_map.update({row["ticker"].upper(): int(row["cik_str"]) for row in data.values()})
    return _cik_map.get(symbol.upper()) or _cik_map.get(symbol.upper().replace("-", "."))


def _parse_form4(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    owner = root.findtext(".//reportingOwner/reportingOwnerId/rptOwnerName") or "Insider"
    title = root.findtext(".//reportingOwnerRelationship/officerTitle") or (
        "Director" if root.findtext(".//reportingOwnerRelationship/isDirector") in ("1", "true") else ""
    )
    trades = []
    for t in root.findall(".//nonDerivativeTable/nonDerivativeTransaction"):
        code = t.findtext("transactionCoding/transactionCode")
        if code not in ("P", "S"):  # open-market purchase / sale; skip grants, exercises, gifts
            continue
        shares = float(t.findtext("transactionAmounts/transactionShares/value") or 0)
        price = float(t.findtext("transactionAmounts/transactionPricePerShare/value") or 0)
        trades.append({"owner": owner.title(), "title": title, "code": code, "shares": shares, "price": price})
    return trades


def sec_filings(symbol: str, as_of: date, lookback_days: int = 14, max_form4: int = 4) -> list[Article]:
    out: list[Article] = []
    try:
        cik = _cik(symbol)
        if cik is None:
            return out  # ETFs and some foreign issuers have no EDGAR company filings
        recent = _sec_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()["filings"]["recent"]
    except Exception:  # noqa: BLE001
        log.warning("sec lookup failed for %s", symbol, exc_info=True)
        return out

    cutoff = as_of - timedelta(days=lookback_days)
    form4_seen = 0
    for i, form in enumerate(recent["form"]):
        filed = date.fromisoformat(recent["filingDate"][i])
        if filed < cutoff:
            break
        acc = recent["accessionNumber"][i]
        folder = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}"
        index_url = f"{folder}/{acc}-index.htm"
        published = datetime.combine(filed, datetime.min.time(), tzinfo=timezone.utc)

        if form in ("8-K", "10-Q", "10-K"):
            items = [x.strip() for x in (recent["items"][i] or "").split(",") if x.strip()]
            described = [f"Item {x} {ITEM_8K[x]}" for x in items if x in ITEM_8K]
            title = {
                "10-Q": "Quarterly report (10-Q) filed",
                "10-K": "Annual report (10-K) filed",
            }.get(form, f"8-K: {'; '.join(described) or 'current report'}")
            red = [x for x in items if x in RED_FLAG_ITEMS]
            out.append(
                Article(
                    id=Article.make_id(index_url), topic=symbol, source_api="sec", publisher="SEC EDGAR", title=title,
                    summary=f"Official {form} filing on {filed}." + (" Contains red-flag items: " + ", ".join(red) if red else ""),
                    url=index_url, published_at=published, kind="filing",
                    sentiment=-0.5 if red else 0.0, sentiment_method="filing-rule", extra={"form": form, "items": items},
                )
            )
        elif form == "4" and form4_seen < max_form4:
            form4_seen += 1
            doc = recent["primaryDocument"][i].split("/")[-1]  # strip the xsl rendering prefix to get raw XML
            try:
                trades = _parse_form4(_sec_get(f"{folder}/{doc}").text)
            except Exception:  # noqa: BLE001
                continue
            for t in trades:
                verb = "bought" if t["code"] == "P" else "sold"
                who = f"{t['owner']}{' (' + t['title'] + ')' if t['title'] else ''}"
                out.append(
                    Article(
                        id=Article.make_id(index_url + t["code"] + str(t["shares"])), topic=symbol, source_api="sec",
                        publisher="SEC EDGAR", title=f"Insider {verb}: {who} {verb} {t['shares']:,.0f} shares at ${t['price']:,.2f}",
                        summary=f"Form 4 filed {filed}. Open-market {'purchase' if t['code'] == 'P' else 'sale'} worth ~${t['shares'] * t['price']:,.0f}. "
                        "Insider sales are often pre-planned (10b5-1) and weaker signals than purchases.",
                        url=index_url, published_at=published, kind="insider",
                        sentiment=0.5 if t["code"] == "P" else -0.15, sentiment_method="filing-rule", extra=t,
                    )
                )
    return out
