"""Portfolio, event, social, and document intelligence persistence models."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Identity,
    Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mutual_fund_agent_analysis.database.base import Base

_ID = BigInteger().with_variant(Integer, "sqlite")
_JSON = JSONB().with_variant(JSON(), "sqlite")


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        UniqueConstraint("scheme_code", "effective_date", "source_key", "content_hash",
                         name="uq_portfolio_snapshot_version"),
        Index("ix_portfolio_snapshot_scheme_date", "scheme_code", "effective_date"),
        CheckConstraint("status IN ('complete', 'partial', 'superseded', 'withdrawn')",
                        name="ck_portfolio_snapshot_status"),
    )
    snapshot_id: Mapped[int] = mapped_column(_ID, Identity(), primary_key=True)
    scheme_code: Mapped[int] = mapped_column(ForeignKey("mutual_fund_schemes.scheme_code"), nullable=False)
    source_key: Mapped[str] = mapped_column(ForeignKey("data_sources.source_key"), nullable=False)
    evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_records.evidence_id"))
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    document_url: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="complete")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    total_market_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", _JSON, nullable=False, default=dict)


class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "security_key", "asset_class", name="uq_portfolio_holding_security"),
        Index("ix_portfolio_holding_security", "security_key"),
        CheckConstraint("weight_pct IS NULL OR weight_pct >= 0", name="ck_portfolio_holding_weight"),
        CheckConstraint("market_value IS NULL OR market_value >= 0", name="ck_portfolio_holding_value"),
        CheckConstraint("asset_class IN ('equity', 'debt', 'cash', 'derivative', 'reit_invit', 'gold', 'other')",
                        name="ck_portfolio_holding_asset_class"),
    )
    holding_id: Mapped[int] = mapped_column(_ID, Identity(), primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("portfolio_snapshots.snapshot_id", ondelete="CASCADE"), nullable=False)
    security_key: Mapped[str] = mapped_column(String(160), nullable=False)
    isin: Mapped[str | None] = mapped_column(String(20))
    security_name: Mapped[str] = mapped_column(String(300), nullable=False)
    company_entity_id: Mapped[int | None] = mapped_column(ForeignKey("research_entities.entity_id"))
    sector: Mapped[str | None] = mapped_column(String(160))
    asset_class: Mapped[str] = mapped_column(String(20), nullable=False, default="equity")
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    market_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    weight_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", _JSON, nullable=False, default=dict)


class MarketEvent(Base):
    __tablename__ = "market_events"
    __table_args__ = (
        UniqueConstraint("source_key", "external_id", name="uq_market_event_source_external"),
        Index("ix_market_event_date_status", "event_date", "status"),
        Index("ix_market_event_entity", "related_entity_id", "event_date"),
        CheckConstraint("status IN ('confirmed', 'scheduled', 'reported', 'unverified', 'speculative', 'disproved', 'outdated')",
                        name="ck_market_event_status"),
        CheckConstraint("event_type IN ('results', 'board_meeting', 'dividend', 'record_date', 'split', 'bonus', 'merger', 'acquisition', 'fundraising', 'management', 'regulatory', 'macro', 'filing', 'other')",
                        name="ck_market_event_type"),
    )
    event_id: Mapped[int] = mapped_column(_ID, Identity(), primary_key=True)
    source_key: Mapped[str] = mapped_column(ForeignKey("data_sources.source_key"), nullable=False)
    evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_records.evidence_id"))
    external_id: Mapped[str | None] = mapped_column(String(200))
    related_entity_id: Mapped[int | None] = mapped_column(ForeignKey("research_entities.entity_id"))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False, default="other")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="reported")
    event_date: Mapped[date | None] = mapped_column(Date)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canonical_url: Mapped[str | None] = mapped_column(String(1000))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    supersedes_event_id: Mapped[int | None] = mapped_column(ForeignKey("market_events.event_id"))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", _JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SocialPost(Base):
    __tablename__ = "social_posts"
    __table_args__ = (
        UniqueConstraint("source_key", "external_id", name="uq_social_post_source_external"),
        Index("ix_social_post_entity_time", "related_entity_id", "published_at"),
        Index("ix_social_post_time", "published_at"),
        CheckConstraint("sentiment_label IS NULL OR sentiment_label IN ('positive', 'neutral', 'negative')",
                        name="ck_social_post_sentiment"),
        CheckConstraint("sentiment_score IS NULL OR (sentiment_score >= -1 AND sentiment_score <= 1)",
                        name="ck_social_post_score"),
    )
    post_id: Mapped[int] = mapped_column(_ID, Identity(), primary_key=True)
    source_key: Mapped[str] = mapped_column(ForeignKey("data_sources.source_key"), nullable=False)
    evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_records.evidence_id"))
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    related_entity_id: Mapped[int | None] = mapped_column(ForeignKey("research_entities.entity_id"))
    canonical_url: Mapped[str | None] = mapped_column(String(1000))
    text_excerpt: Mapped[str | None] = mapped_column(String(2000))
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    engagement_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sentiment_label: Mapped[str | None] = mapped_column(String(10))
    sentiment_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    sentiment_model: Mapped[str | None] = mapped_column(String(100))
    is_spam: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", _JSON, nullable=False, default=dict)


class ResearchDocument(Base):
    __tablename__ = "research_documents"
    __table_args__ = (
        UniqueConstraint("source_key", "content_hash", name="uq_research_document_source_hash"),
        Index("ix_research_document_scheme_date", "scheme_code", "effective_date"),
    )
    document_id: Mapped[int] = mapped_column(_ID, Identity(), primary_key=True)
    source_key: Mapped[str] = mapped_column(ForeignKey("data_sources.source_key"), nullable=False)
    scheme_code: Mapped[int | None] = mapped_column(ForeignKey("mutual_fund_schemes.scheme_code"))
    related_entity_id: Mapped[int | None] = mapped_column(ForeignKey("research_entities.entity_id"))
    evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_records.evidence_id"))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(1000))
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_date: Mapped[date | None] = mapped_column(Date)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
        Index("ix_document_chunk_document", "document_id"),
    )
    chunk_id: Mapped[int] = mapped_column(_ID, Identity(), primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("research_documents.document_id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vector_id: Mapped[str | None] = mapped_column(String(100))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", _JSON, nullable=False, default=dict)
