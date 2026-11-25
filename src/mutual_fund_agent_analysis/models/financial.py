"""Versioned scheme metadata and distribution observations."""

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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mutual_fund_agent_analysis.database.base import Base

_ID = BigInteger().with_variant(Integer, "sqlite")
_JSON = JSONB().with_variant(JSON(), "sqlite")


class SchemeMetadataObservation(Base):
    """Source-attributed, effective-dated observation of scheme product metadata."""

    __tablename__ = "scheme_metadata_observations"
    __table_args__ = (
        UniqueConstraint(
            "scheme_code", "source_key", "content_hash",
            name="uq_scheme_metadata_source_hash",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_scheme_metadata_valid_range",
        ),
        CheckConstraint(
            "plan_type IS NULL OR plan_type IN ('direct', 'regular', 'unknown')",
            name="ck_scheme_metadata_plan",
        ),
        CheckConstraint(
            "option_type IS NULL OR option_type IN "
            "('growth', 'idcw_payout', 'idcw_reinvestment', 'idcw_transfer', 'unknown')",
            name="ck_scheme_metadata_option",
        ),
        CheckConstraint(
            "lifecycle_type IS NULL OR lifecycle_type IN "
            "('open_ended', 'close_ended', 'interval', 'unknown')",
            name="ck_scheme_metadata_lifecycle",
        ),
        CheckConstraint(
            "expense_ratio IS NULL OR expense_ratio BETWEEN 0 AND 100",
            name="ck_scheme_metadata_expense_ratio",
        ),
        CheckConstraint(
            "verification_status IN ('unverified', 'verified', 'disputed', 'retracted')",
            name="ck_scheme_metadata_verification",
        ),
        Index("ix_scheme_metadata_effective", "scheme_code", "valid_from", "valid_to"),
    )

    metadata_id: Mapped[int] = mapped_column(_ID, Identity(), primary_key=True)
    scheme_code: Mapped[int] = mapped_column(
        ForeignKey("mutual_fund_schemes.scheme_code", ondelete="CASCADE"), nullable=False
    )
    source_key: Mapped[str] = mapped_column(
        ForeignKey("data_sources.source_key", ondelete="RESTRICT"), nullable=False
    )
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    plan_type: Mapped[str | None] = mapped_column(String(20))
    option_type: Mapped[str | None] = mapped_column(String(30))
    lifecycle_type: Mapped[str | None] = mapped_column(String(20))
    expense_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    expense_ratio_effective_date: Mapped[date | None] = mapped_column(Date)
    benchmark_code: Mapped[str | None] = mapped_column(String(80))
    launch_date: Mapped[date | None] = mapped_column(Date)
    closure_date: Mapped[date | None] = mapped_column(Date)
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unverified"
    )
    verification_note: Mapped[str | None] = mapped_column(String(1000))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", _JSON, nullable=False, default=dict
    )


class DistributionObservation(Base):
    """Versioned scheme IDCW declaration with auditable source and correction chain."""

    __tablename__ = "distribution_observations"
    __table_args__ = (
        UniqueConstraint(
            "scheme_code", "source_key", "external_id", "revision",
            name="uq_distribution_source_revision",
        ),
        CheckConstraint("amount_per_unit > 0", name="ck_distribution_amount_positive"),
        CheckConstraint("revision >= 1", name="ck_distribution_revision_positive"),
        CheckConstraint(
            "record_date IS NULL OR record_date >= ex_date",
            name="ck_distribution_record_date",
        ),
        CheckConstraint(
            "payment_date IS NULL OR record_date IS NULL OR payment_date >= record_date",
            name="ck_distribution_payment_date",
        ),
        CheckConstraint(
            "option_type IN ('idcw_payout', 'idcw_reinvestment', 'idcw_transfer')",
            name="ck_distribution_option",
        ),
        CheckConstraint(
            "status IN ('active', 'revised', 'cancelled')",
            name="ck_distribution_status",
        ),
        CheckConstraint(
            "verification_status IN ('unverified', 'verified', 'disputed', 'retracted')",
            name="ck_distribution_verification",
        ),
        Index("ix_distribution_scheme_ex_date", "scheme_code", "ex_date"),
    )

    distribution_id: Mapped[int] = mapped_column(_ID, Identity(), primary_key=True)
    scheme_code: Mapped[int] = mapped_column(
        ForeignKey("mutual_fund_schemes.scheme_code", ondelete="CASCADE"), nullable=False
    )
    source_key: Mapped[str] = mapped_column(
        ForeignKey("data_sources.source_key", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_distribution_id: Mapped[int | None] = mapped_column(
        ForeignKey("distribution_observations.distribution_id", ondelete="RESTRICT")
    )
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ex_date: Mapped[date] = mapped_column(Date, nullable=False)
    record_date: Mapped[date | None] = mapped_column(Date)
    payment_date: Mapped[date | None] = mapped_column(Date)
    amount_per_unit: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    option_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unverified"
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", _JSON, nullable=False, default=dict
    )


class DistributionCoverageAttestation(Base):
    """Official-source attestation that all distributions in a date interval were captured."""

    __tablename__ = "distribution_coverage_attestations"
    __table_args__ = (
        UniqueConstraint(
            "scheme_code", "source_key", "external_id", "content_hash",
            name="uq_distribution_coverage_attestation",
        ),
        CheckConstraint("end_date >= start_date", name="ck_distribution_coverage_date_range"),
        CheckConstraint(
            "verification_status IN ('unverified', 'verified', 'disputed', 'retracted')",
            name="ck_distribution_coverage_verification",
        ),
        Index("ix_distribution_coverage_scheme_dates", "scheme_code", "start_date", "end_date"),
    )

    attestation_id: Mapped[int] = mapped_column(_ID, Identity(), primary_key=True)
    scheme_code: Mapped[int] = mapped_column(
        ForeignKey("mutual_fund_schemes.scheme_code", ondelete="CASCADE"), nullable=False
    )
    source_key: Mapped[str] = mapped_column(
        ForeignKey("data_sources.source_key", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    coverage_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unverified"
    )
    verification_note: Mapped[str | None] = mapped_column(String(1000))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", _JSON, nullable=False, default=dict
    )
