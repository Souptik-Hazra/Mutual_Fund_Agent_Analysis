"""Shared entity, source registry, and evidence provenance models."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mutual_fund_agent_analysis.database.base import Base

_ID_TYPE = BigInteger().with_variant(Integer, "sqlite")
_JSON_TYPE = JSONB().with_variant(JSON(), "sqlite")


class DataSource(Base):
    """Registry entry describing a provider or research source and its authority."""

    __tablename__ = "data_sources"
    __table_args__ = (
        CheckConstraint("authority_tier BETWEEN 1 AND 5", name="ck_data_sources_authority_tier"),
        CheckConstraint(
            "source_type IN ('official', 'provider', 'media', 'social', 'document', 'internal')",
            name="ck_data_sources_source_type",
        ),
    )

    source_key: Mapped[str] = mapped_column(String(60), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    authority_tier: Mapped[int] = mapped_column(nullable=False)
    is_official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    base_url: Mapped[str | None] = mapped_column(String(500))
    terms_url: Mapped[str | None] = mapped_column(String(500))
    attribution_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", _JSON_TYPE, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ResearchEntity(Base):
    """Canonical identity shared by fund, company, security, benchmark, and event data."""

    __tablename__ = "research_entities"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('amc', 'scheme', 'company', 'security', 'sector', "
            "'benchmark', 'index', 'person', 'event', 'regulator', 'other')",
            name="ck_research_entities_type",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive', 'merged')", name="ck_research_entities_status"
        ),
        UniqueConstraint("entity_type", "normalized_name", name="uq_entity_type_normalized_name"),
        Index("ix_research_entities_type_status", "entity_type", "status"),
    )

    entity_id: Mapped[int] = mapped_column(_ID_TYPE, Identity(), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    merged_into_entity_id: Mapped[int | None] = mapped_column(
        _ID_TYPE, ForeignKey("research_entities.entity_id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EntityAlias(Base):
    """A source-aware name or historical alias for a canonical entity."""

    __tablename__ = "entity_aliases"
    __table_args__ = (
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_entity_aliases_valid_range",
        ),
        UniqueConstraint(
            "entity_id", "normalized_alias", "valid_from", name="uq_entity_alias_identity"
        ),
        Index("ix_entity_aliases_normalized", "normalized_alias"),
    )

    alias_id: Mapped[int] = mapped_column(_ID_TYPE, Identity(), primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        _ID_TYPE, ForeignKey("research_entities.entity_id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(300), nullable=False)
    alias_type: Mapped[str] = mapped_column(String(30), nullable=False, default="common")
    source_key: Mapped[str | None] = mapped_column(
        String(60), ForeignKey("data_sources.source_key", ondelete="RESTRICT")
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EntityIdentifier(Base):
    """A stable external identifier such as AMFI scheme code, ISIN, or exchange symbol."""

    __tablename__ = "entity_identifiers"
    __table_args__ = (
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_entity_identifiers_valid_range",
        ),
        UniqueConstraint("namespace", "normalized_value", name="uq_entity_identifier_value"),
        Index("ix_entity_identifiers_entity", "entity_id"),
    )

    identifier_id: Mapped[int] = mapped_column(_ID_TYPE, Identity(), primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        _ID_TYPE, ForeignKey("research_entities.entity_id", ondelete="CASCADE"), nullable=False
    )
    namespace: Mapped[str] = mapped_column(String(60), nullable=False)
    identifier_value: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(160), nullable=False)
    source_key: Mapped[str | None] = mapped_column(
        String(60), ForeignKey("data_sources.source_key", ondelete="RESTRICT")
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EvidenceRecord(Base):
    """Immutable-source reference with publication, retrieval, validity, and trust metadata."""

    __tablename__ = "evidence_records"
    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('unverified', 'corroborated', 'verified', "
            "'disputed', 'retracted')",
            name="ck_evidence_records_verification_status",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_evidence_records_confidence",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_evidence_records_effective_range",
        ),
        UniqueConstraint("source_key", "external_id", name="uq_evidence_source_external_id"),
        Index("ix_evidence_source_published", "source_key", "published_at"),
        Index("ix_evidence_content_hash", "content_hash"),
    )

    evidence_id: Mapped[int] = mapped_column(_ID_TYPE, Identity(), primary_key=True)
    source_key: Mapped[str] = mapped_column(
        String(60), ForeignKey("data_sources.source_key", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str | None] = mapped_column(String(200))
    canonical_url: Mapped[str | None] = mapped_column(String(1000))
    title: Mapped[str | None] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    content_hash: Mapped[str | None] = mapped_column(String(128))
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unverified"
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", _JSON_TYPE, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EntityEvidenceLink(Base):
    """Auditable relationship between a canonical entity and a source evidence item."""

    __tablename__ = "entity_evidence_links"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_entity_evidence_links_confidence",
        ),
        CheckConstraint(
            "resolution_method IN ('identifier', 'exact_alias', 'manual', 'model_reviewed')",
            name="ck_entity_evidence_links_resolution_method",
        ),
        Index("ix_entity_evidence_links_evidence", "evidence_id"),
    )

    entity_id: Mapped[int] = mapped_column(
        _ID_TYPE, ForeignKey("research_entities.entity_id", ondelete="CASCADE"), primary_key=True
    )
    evidence_id: Mapped[int] = mapped_column(
        _ID_TYPE, ForeignKey("evidence_records.evidence_id", ondelete="CASCADE"), primary_key=True
    )
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False, default="mentions")
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    resolution_method: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
