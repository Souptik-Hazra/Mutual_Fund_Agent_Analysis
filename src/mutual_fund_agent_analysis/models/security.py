"""Versioned market observations for securities disclosed by mutual funds."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
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


class SecurityMarketObservation(Base):
    """Immutable provider observation; market values are never inferred from fund NAV."""

    __tablename__ = "security_market_observations"
    __table_args__ = (
        UniqueConstraint(
            "source_key", "security_key", "observed_at", "content_hash",
            name="uq_security_market_observation_version",
        ),
        CheckConstraint("last_price > 0", name="ck_security_market_price_positive"),
        CheckConstraint(
            "change_pct IS NULL OR change_pct >= -100",
            name="ck_security_market_change_floor",
        ),
        CheckConstraint(
            "market_status IN ('trading', 'halted', 'closed', 'unknown')",
            name="ck_security_market_status",
        ),
        Index("ix_security_market_latest", "security_key", "observed_at"),
        Index("ix_security_market_isin", "isin", "observed_at"),
    )

    observation_id: Mapped[int] = mapped_column(_ID, Identity(), primary_key=True)
    security_key: Mapped[str] = mapped_column(String(160), nullable=False)
    isin: Mapped[str | None] = mapped_column(String(20))
    security_name: Mapped[str] = mapped_column(String(300), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(40))
    exchange: Mapped[str | None] = mapped_column(String(12))
    source_key: Mapped[str] = mapped_column(
        ForeignKey("data_sources.source_key", ondelete="RESTRICT"), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(String(1000))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fundamentals_as_of: Mapped[date | None] = mapped_column(Date)
    last_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    day_high: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    day_low: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    market_status: Mapped[str] = mapped_column(String(12), nullable=False, default="unknown")
    fundamentals_json: Mapped[dict[str, Any]] = mapped_column(
        "fundamentals", _JSON, nullable=False, default=dict
    )
    corporate_events_json: Mapped[list[dict[str, Any]]] = mapped_column(
        "corporate_events", _JSON, nullable=False, default=list
    )
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
