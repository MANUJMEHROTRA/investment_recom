from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, BigInteger, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JsonType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Ticker(Base):
    __tablename__ = "tickers"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200))
    sector: Mapped[str | None] = mapped_column(String(100))
    industry: Mapped[str | None] = mapped_column(String(150))
    quote_type: Mapped[str | None] = mapped_column(String(30))
    market_cap: Mapped[float | None] = mapped_column(Float)
    forward_pe: Mapped[float | None] = mapped_column(Float)
    trailing_pe: Mapped[float | None] = mapped_column(Float)
    revenue_growth: Mapped[float | None] = mapped_column(Float)
    profit_margin: Mapped[float | None] = mapped_column(Float)
    debt_to_equity: Mapped[float | None] = mapped_column(Float)
    fundamentals_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DailyPrice(Base):
    __tablename__ = "daily_prices"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int | None] = mapped_column(BigInteger)


class RecommendationRun(Base):
    """One analysis per market date. Re-running the same date replaces it."""

    __tablename__ = "recommendation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    source: Mapped[str] = mapped_column(String(20))  # scheduled | manual | startup | backfill
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    model_version: Mapped[str] = mapped_column(String(20))
    regime_label: Mapped[str] = mapped_column(String(20))
    equity_exposure: Mapped[float] = mapped_column(Float)
    regime: Mapped[dict] = mapped_column(JsonType)
    universe_size: Mapped[int] = mapped_column(Integer)
    skipped: Mapped[dict] = mapped_column(JsonType, default=dict)

    recommendations: Mapped[list[Recommendation]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="Recommendation.rank"
    )


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (UniqueConstraint("run_id", "symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("recommendation_runs.id", ondelete="CASCADE"), index=True)
    run_date: Mapped[date] = mapped_column(Date, index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    rating: Mapped[str] = mapped_column(String(20))
    price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float)
    target_weight: Mapped[float | None] = mapped_column(Float)
    components: Mapped[dict] = mapped_column(JsonType)
    metrics: Mapped[dict] = mapped_column(JsonType)
    reasons: Mapped[list] = mapped_column(JsonType)
    cautions: Mapped[list] = mapped_column(JsonType)

    run: Mapped[RecommendationRun] = relationship(back_populates="recommendations")


class Holding(Base):
    """A position you own - entered on the Portfolio page, used for exit recommendations."""

    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    avg_cost: Mapped[float] = mapped_column(Float)  # USD per share
    buy_date: Mapped[date | None] = mapped_column(Date)
    buy_fx_rate: Mapped[float | None] = mapped_column(Float)  # INR per USD when bought; looked up if blank
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DailyBrief(Base):
    """The pre-market, news-backed brief produced by the agent service - one per day."""

    __tablename__ = "daily_briefs"

    brief_date: Mapped[date] = mapped_column(Date, primary_key=True)
    run_date: Mapped[date] = mapped_column(Date)  # market date of the price data it used
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    llm_provider: Mapped[str] = mapped_column(String(30))
    llm_model: Mapped[str] = mapped_column(String(80))
    content: Mapped[dict] = mapped_column(JsonType)


class NewsArticle(Base):
    __tablename__ = "news_articles"
    __table_args__ = (UniqueConstraint("id", "topic"),)

    pk: Mapped[int] = mapped_column(Integer, primary_key=True)
    id: Mapped[str] = mapped_column(String(24), index=True)
    topic: Mapped[str] = mapped_column(String(64), index=True)  # ticker, "sector:<name>", "macro", "fx"
    source_api: Mapped[str] = mapped_column(String(20))
    publisher: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(String(2000))
    url: Mapped[str] = mapped_column(String(1000))
    kind: Mapped[str] = mapped_column(String(20))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sentiment: Mapped[float | None] = mapped_column(Float)
    sentiment_method: Mapped[str | None] = mapped_column(String(20))
    takeaway: Mapped[str | None] = mapped_column(String(1000))
    first_seen: Mapped[date] = mapped_column(Date)
