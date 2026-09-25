"""Social-listening clustering service: its own database, embeddings saved once, only new
articles processed each run."""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import BackgroundTasks, FastAPI
from sqlalchemy import select

from . import pipeline
from .config import get_settings
from .db import init_db, session_scope
from .embed import get_embedder
from .models import Article, Cluster, ClusterRun, Point

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    scheduler.add_job(pipeline.run_all, "interval", hours=3, id="refresh", max_instances=1)  # catch anything missed
    scheduler.start()
    threading.Thread(target=pipeline.run_all, daemon=True).start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Social Listening Clustering Service", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "embed_backend": get_settings().embed_backend}


@app.get("/status")
def status() -> dict[str, Any]:
    s = get_settings()
    emb = get_embedder()
    with session_scope() as session:
        run = session.scalar(select(ClusterRun).order_by(ClusterRun.id.desc()).limit(1))
        return {
            "job": pipeline.status,
            "embedder": {"model": emb.name, "device": emb.device},
            "counts": pipeline.counts(session),
            "last_run": _run_dict(run) if run else None,
            "platforms": [s.platform],
        }


@app.post("/run", status_code=202)
def run(background: BackgroundTasks) -> dict[str, Any]:
    if pipeline.status["running"]:
        return {"accepted": False, "reason": "already running"}
    background.add_task(pipeline.run_all)
    return {"accepted": True}


def _run_dict(r: ClusterRun) -> dict[str, Any]:
    return {
        "id": r.id, "created_at": r.created_at.isoformat(), "embed_model": r.embed_model, "params": r.params,
        "n_articles": r.n_articles, "n_clusters": r.n_clusters, "n_noise": r.n_noise,
        "new_embeddings": r.new_embeddings, "new_summaries": r.new_summaries, "seconds": r.seconds,
    }


@app.get("/map")
def cluster_map() -> dict[str, Any]:
    """Everything the interactive map needs for the latest run; filtering happens in the browser."""
    with session_scope() as session:
        run = session.scalar(select(ClusterRun).where(ClusterRun.n_articles > 0).order_by(ClusterRun.id.desc()).limit(1))
        if run is None:
            return {"run": None, "clusters": [], "points": []}
        clusters = session.scalars(select(Cluster).where(Cluster.run_id == run.id).order_by(Cluster.size.desc())).all()
        rows = session.execute(select(Point, Article).join(Article, Article.id == Point.article_id).where(Point.run_id == run.id)).all()
        return {
            "run": _run_dict(run),
            "clusters": [
                {
                    "label": c.label, "stable_id": c.stable_id, "size": c.size, "headline": c.headline, "summary": c.summary,
                    "summary_method": c.summary_method, "keywords": c.keywords, "sentiment": c.sentiment, "tickers": c.tickers,
                    "ticker_names": c.ticker_names, "sectors": c.sectors, "sources": c.sources, "platforms": c.platforms,
                    "cx": c.cx, "cy": c.cy, "first_published": c.first_published.isoformat(), "last_published": c.last_published.isoformat(),
                    "top_article_ids": c.top_article_ids,
                }
                for c in clusters
            ],
            "points": [
                {
                    "id": a.id, "label": p.label, "x": round(p.x, 4), "y": round(p.y, 4), "probability": round(p.probability, 3),
                    "title": a.title, "summary": (a.summary or "")[:300], "url": a.url, "publisher": a.publisher,
                    "source_api": a.source_api, "platform": a.platform, "kind": a.kind, "published_at": a.published_at.isoformat(),
                    "sentiment": a.sentiment, "sentiment_method": a.sentiment_method, "tickers": a.tickers,
                    "ticker_names": a.ticker_names, "sectors": a.sectors,
                }
                for p, a in rows
            ],
        }
