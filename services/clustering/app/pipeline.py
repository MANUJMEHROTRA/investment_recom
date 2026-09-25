"""Incremental pipeline. Each run:
  ingest   - pull only articles the backend stored since the last cursor
  embed    - embed only articles without a saved vector for the current model
  cluster  - UMAP + HDBSCAN over the recent window (cheap: a few thousand points)
  summarise- LLM only for clusters whose membership changed (cached by member hash)
"""
from __future__ import annotations

import logging
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import cluster as algo
from .config import get_settings
from .db import session_scope
from .embed import article_text, get_embedder
from .models import Article, Cluster, ClusterRun, Cursor, Embedding, Point, SummaryCache
from .summarize import _provider, summarise

log = logging.getLogger(__name__)
_lock = threading.Lock()
status: dict[str, Any] = {"running": False, "stage": "idle", "error": None, "last_finished": None}


# ---------------------------------------------------------------- ingest

def ingest(session: Session) -> int:
    s = get_settings()
    cur = session.get(Cursor, "backend_news") or Cursor(key="backend_news", value=0)
    total = 0
    while True:
        r = httpx.get(f"{s.backend_url}/api/news/feed", params={"after_pk": cur.value, "limit": 2000}, timeout=60)
        r.raise_for_status()
        data = r.json()
        items = data["items"]
        if not items:
            break
        grouped: dict[str, list[dict]] = defaultdict(list)
        for it in items:
            grouped[it["id"]].append(it)
        for aid, rows in grouped.items():
            a = session.get(Article, aid)
            first = rows[0]
            if a is None:
                a = Article(
                    id=aid, url=first["url"], title=first["title"], summary=first.get("summary"), publisher=first["publisher"],
                    source_api=first["source_api"], platform=s.platform, kind=first["kind"],
                    published_at=datetime.fromisoformat(first["published_at"]), sentiment=first.get("sentiment"),
                    sentiment_method=first.get("sentiment_method"), tickers=[], ticker_names={}, sectors=[],
                )
                session.add(a)
            tickers, names, sectors = set(a.tickers or []), dict(a.ticker_names or {}), set(a.sectors or [])
            for row in rows:
                topic = row["topic"]
                if not (topic.startswith("sector:") or topic in ("macro", "fx")):
                    tickers.add(topic)
                    if row.get("symbol_name"):
                        names[topic] = row["symbol_name"]
                if row.get("sector"):
                    sectors.add(row["sector"])
                if row.get("sentiment_method") == "llm":  # prefer the LLM's reading when one exists
                    a.sentiment, a.sentiment_method = row["sentiment"], "llm"
            a.tickers, a.ticker_names, a.sectors = sorted(tickers), names, sorted(sectors)
        cur.value = data["next_after_pk"]
        session.merge(cur)
        session.commit()
        total += len(grouped)
    return total


# ---------------------------------------------------------------- embed

def embed_new(session: Session) -> int:
    emb = get_embedder()
    todo = session.execute(
        select(Article.id, Article.title, Article.summary)
        .outerjoin(Embedding, (Embedding.article_id == Article.id) & (Embedding.model == emb.name))
        .where(Embedding.article_id.is_(None))
    ).all()
    for i in range(0, len(todo), 256):
        batch = todo[i : i + 256]
        vecs = emb.embed([article_text(t, s) for _, t, s in batch])
        for (aid, _, _), v in zip(batch, vecs):
            session.add(Embedding(article_id=aid, model=emb.name, dim=len(v), vector=v.tolist()))
        session.commit()
    return len(todo)


# ---------------------------------------------------------------- cluster

def run_clustering(session: Session, new_embeddings: int, t0: float) -> ClusterRun:
    s = get_settings()
    emb = get_embedder()
    since = datetime.now(timezone.utc) - timedelta(days=s.window_days)
    rows = session.execute(
        select(Article, Embedding.vector)
        .join(Embedding, (Embedding.article_id == Article.id) & (Embedding.model == emb.name))
        .where(Article.published_at >= since)
        .order_by(Article.published_at)
    ).all()
    params = {
        "window_days": s.window_days, "min_cluster_size": s.min_cluster_size, "min_samples": s.min_samples,
        "umap_neighbors": s.umap_neighbors, "umap_cluster_dims": s.umap_cluster_dims, "merge_similarity": s.merge_similarity,
        "algorithm": "UMAP(cosine) -> HDBSCAN -> centroid merge", "embed_device": emb.device,
    }
    run = ClusterRun(embed_model=emb.name, params=params, n_articles=len(rows), n_clusters=0, n_noise=0, new_embeddings=new_embeddings)
    session.add(run)
    session.flush()
    if len(rows) < max(10, s.min_cluster_size * 2):
        run.n_noise = len(rows)
        session.commit()
        return run

    arts = [r[0] for r in rows]
    x = np.asarray([np.asarray(r[1], dtype=np.float32) for r in rows])
    z = algo.reduce(x, s.umap_cluster_dims, s.umap_neighbors, s.random_state, min_dist=0.0)
    labels, probs = algo.density_cluster(z, s.min_cluster_size, s.min_samples)
    labels = algo.merge_duplicates(x, labels, s.merge_similarity)
    xy = algo.reduce(x, 2, s.umap_neighbors, s.random_state, min_dist=0.15)
    xy = (xy - xy.min(axis=0)) / np.where(np.ptp(xy, axis=0) == 0, 1, np.ptp(xy, axis=0))

    members: dict[int, list[int]] = defaultdict(list)
    for i, lab in enumerate(labels):
        members[int(lab)].append(i)
    clusters = {k: v for k, v in members.items() if k != algo.NOISE}

    prev_run = session.scalar(select(ClusterRun).where(ClusterRun.id < run.id, ClusterRun.n_clusters > 0).order_by(ClusterRun.id.desc()).limit(1))
    previous: dict[str, set[str]] = {}
    if prev_run:
        prev_members: dict[int, set[str]] = defaultdict(set)
        for p in session.scalars(select(Point).where(Point.run_id == prev_run.id, Point.label != algo.NOISE)):
            prev_members[p.label].add(p.article_id)
        for c in session.scalars(select(Cluster).where(Cluster.run_id == prev_run.id)):
            previous[c.stable_id] = prev_members.get(c.label, set())
    stable = algo.assign_stable_ids({k: {arts[i].id for i in v} for k, v in clusters.items()}, previous)
    kw = algo.keywords({k: " ".join(arts[i].title + " " + (arts[i].summary or "")[:300] for i in v) for k, v in clusters.items()})

    provider = _provider()
    new_summaries = 0
    for label, idx in clusters.items():
        idx_arr = np.array(idx)
        order = idx_arr[np.argsort(-algo.centrality(x, idx_arr))]
        top = [arts[i] for i in order]
        ids = [a.id for a in top]
        mh = algo.member_hash(ids)
        cached = session.get(SummaryCache, mh)
        tick = Counter(t for a in top for t in a.tickers)
        if cached is None:
            summ, method = summarise([a.title for a in top], [a.summary or "" for a in top], [t for t, _ in tick.most_common()], kw.get(label, []), provider)
            cached = SummaryCache(member_hash=mh, headline=summ.headline[:300], summary=summ.summary, sentiment=summ.sentiment, method=method)
            session.add(cached)
            new_summaries += 1
        sents = [a.sentiment for a in top if a.sentiment is not None]
        names = {t: n for a in top for t, n in (a.ticker_names or {}).items()}
        session.add(
            Cluster(
                run_id=run.id, label=label, stable_id=stable[label], size=len(idx), headline=cached.headline, summary=cached.summary,
                summary_method=cached.method, keywords=kw.get(label, []),
                sentiment=round(float(np.mean(sents)), 3) if sents else None,
                tickers=dict(tick.most_common()), ticker_names=names,
                sectors=dict(Counter(sct for a in top for sct in a.sectors).most_common()),
                sources=dict(Counter(a.source_api for a in top)), platforms=dict(Counter(a.platform for a in top)),
                cx=float(xy[idx_arr, 0].mean()), cy=float(xy[idx_arr, 1].mean()),
                first_published=min(a.published_at for a in top), last_published=max(a.published_at for a in top),
                member_hash=mh, top_article_ids=ids[:8],
            )
        )
    for i, a in enumerate(arts):
        session.add(Point(run_id=run.id, article_id=a.id, label=int(labels[i]), x=float(xy[i, 0]), y=float(xy[i, 1]), probability=float(probs[i])))
    run.n_clusters = len(clusters)
    run.n_noise = int((labels == algo.NOISE).sum())
    run.new_summaries = new_summaries
    run.seconds = round(time.time() - t0, 1)
    session.commit()
    return run


def run_all() -> None:
    if not _lock.acquire(blocking=False):
        return
    status.update(running=True, error=None)
    t0 = time.time()
    try:
        with session_scope() as session:
            status["stage"] = "ingesting new articles"
            n_in = ingest(session)
            status["stage"] = f"embedding new articles ({get_embedder().device})"
            n_emb = embed_new(session)
            status["stage"] = "clustering (UMAP + HDBSCAN)"
            run = run_clustering(session, n_emb, t0)
            log.info("run %s: %d ingested, %d embedded, %d clusters, %d new summaries", run.id, n_in, n_emb, run.n_clusters, run.new_summaries)
        status["stage"] = "idle"
    except Exception as exc:  # noqa: BLE001
        log.exception("clustering run failed")
        status.update(error=f"{exc.__class__.__name__}: {exc}", stage="failed")
    finally:
        status.update(running=False, last_finished=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        _lock.release()


def counts(session: Session) -> dict[str, int]:
    return {
        "articles": session.scalar(select(func.count()).select_from(Article)) or 0,
        "embeddings": session.scalar(select(func.count()).select_from(Embedding)) or 0,
        "runs": session.scalar(select(func.count()).select_from(ClusterRun)) or 0,
        "cached_summaries": session.scalar(select(func.count()).select_from(SummaryCache)) or 0,
    }
