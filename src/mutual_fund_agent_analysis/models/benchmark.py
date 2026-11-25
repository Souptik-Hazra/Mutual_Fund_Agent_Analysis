"""Benchmark master and historical total-return observations."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Numeric,
    PrimaryKeyConstraint,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mutual_fund_agent_analysis.database.base import Base


class BenchmarkIndex(Base):
    """Canonical benchmark index master."""

    __tablename__ = "benchmark_indices"

    benchmark_code: Mapped[str] = mapped_column(String(80), primary_key=True)
    benchmark_name: Mapped[str] = mapped_column(String(160), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="niftyindices")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BenchmarkObservation(Base):
    """Daily benchmark TRI/NTR values from a named source."""

    __tablename__ = "benchmark_observations"
    __table_args__ = (
        CheckConstraint("tri_value > 0", name="ck_benchmark_observations_positive_tri"),
        CheckConstraint(
            "ntr_value IS NULL OR ntr_value > 0",
            name="ck_benchmark_observations_positive_ntr",
        ),
        PrimaryKeyConstraint(
            "benchmark_code", "observation_date", "source",
            name="pk_benchmark_observations",
        ),
    )

    benchmark_code: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    tri_value: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    ntr_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    raw_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
