from __future__ import annotations

from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JsonType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Article(Base):
    """One news item (deduplicated by URL hash) with every stock / sector it was collected for."""

    __tablename__ = "articles"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    url: Mapped[str] = mapped_column(String(1000))
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(Text)
    publisher: Mapped[str] = mapped_column(String(120))
    source_api: Mapped[str] = mapped_column(String(20))  # yahoo | finnhub | sec
    platform: Mapped[str] = mapped_column(String(20), default="News")  # News now; Twitter / LinkedIn later
    kind: Mapped[str] = mapped_column(String(20))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sentiment: Mapped[float | None] = mapped_column(Float)
    sentiment_method: Mapped[str | None] = mapped_column(String(20))
    tickers: Mapped[list] = mapped_column(JsonType, default=list)
    ticker_names: Mapped[dict] = mapped_column(JsonType, default=dict)
    sectors: Mapped[list] = mapped_column(JsonType, default=list)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Embedding(Base):
    """Saved once per (article, model) - never recomputed."""

    __tablename__ = "embeddings"

    article_id: Mapped[str] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    model: Mapped[str] = mapped_column(String(120), primary_key=True)
    dim: Mapped[int] = mapped_column(Integer)
    vector: Mapped[list[float]] = mapped_column(Vector())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Cursor(Base):
    __tablename__ = "ingest_cursor"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[int] = mapped_column(Integer)


class ClusterRun(Base):
    __tablename__ = "cluster_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    embed_model: Mapped[str] = mapped_column(String(120))
    params: Mapped[dict] = mapped_column(JsonType)
    n_articles: Mapped[int] = mapped_column(Integer)
    n_clusters: Mapped[int] = mapped_column(Integer)
    n_noise: Mapped[int] = mapped_column(Integer)
    new_embeddings: Mapped[int] = mapped_column(Integer, default=0)
    new_summaries: Mapped[int] = mapped_column(Integer, default=0)
    seconds: Mapped[float] = mapped_column(Float, default=0)


class Cluster(Base):
    __tablename__ = "clusters"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("cluster_runs.id", ondelete="CASCADE"), index=True)
    label: Mapped[int] = mapped_column(Integer)
    stable_id: Mapped[str] = mapped_column(String(16), index=True)  # persists across runs for the same story
    size: Mapped[int] = mapped_column(Integer)
    headline: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    summary_method: Mapped[str] = mapped_column(String(20))
    keywords: Mapped[list] = mapped_column(JsonType)
    sentiment: Mapped[float | None] = mapped_column(Float)
    tickers: Mapped[dict] = mapped_column(JsonType)  # symbol -> article count
    ticker_names: Mapped[dict] = mapped_column(JsonType)
    sectors: Mapped[dict] = mapped_column(JsonType)
    sources: Mapped[dict] = mapped_column(JsonType)
    platforms: Mapped[dict] = mapped_column(JsonType)
    cx: Mapped[float] = mapped_column(Float)
    cy: Mapped[float] = mapped_column(Float)
    first_published: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_published: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    member_hash: Mapped[str] = mapped_column(String(40))
    top_article_ids: Mapped[list] = mapped_column(JsonType)


class Point(Base):
    __tablename__ = "points"

    run_id: Mapped[int] = mapped_column(ForeignKey("cluster_runs.id", ondelete="CASCADE"), primary_key=True)
    article_id: Mapped[str] = mapped_column(String(24), primary_key=True)
    label: Mapped[int] = mapped_column(Integer)  # -1 = not part of any cluster
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    probability: Mapped[float] = mapped_column(Float)


class SummaryCache(Base):
    """LLM output keyed by the exact member set, so unchanged clusters are never re-summarised."""

    __tablename__ = "summary_cache"

    member_hash: Mapped[str] = mapped_column(String(40), primary_key=True)
    headline: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    sentiment: Mapped[float | None] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
