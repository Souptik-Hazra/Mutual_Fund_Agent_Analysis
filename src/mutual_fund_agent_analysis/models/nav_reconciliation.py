"""Persisted cross-provider NAV reconciliation results."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    PrimaryKeyConstraint,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mutual_fund_agent_analysis.database.base import Base


class NavReconciliation(Base):
    """One deterministic canonical NAV decision per scheme and NAV date."""

    __tablename__ = "nav_reconciliations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('single_source', 'matched', 'conflict')",
            name="ck_nav_reconciliations_status",
        ),
        PrimaryKeyConstraint("scheme_code", "nav_date", name="pk_nav_reconciliations"),
    )

    scheme_code: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("mutual_fund_schemes.scheme_code", ondelete="CASCADE"),
        nullable=False,
    )
    nav_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_values: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    canonical_nav: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    canonical_source: Mapped[str] = mapped_column(String(40), nullable=False)
    absolute_difference: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    relative_difference: Mapped[Decimal | None] = mapped_column(Numeric(20, 12))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    tolerance: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
