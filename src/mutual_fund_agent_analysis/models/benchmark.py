"""Benchmark master, TRI observations, and ingestion audit models."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Identity,
    Integer,
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
        ForeignKeyConstraint(
            ["benchmark_code"],
            ["benchmark_indices.benchmark_code"],
            ondelete="CASCADE",
        ),
        PrimaryKeyConstraint(
            "benchmark_code",
            "observation_date",
            "source",
            name="pk_benchmark_observations",
        ),
    )

    benchmark_code: Mapped[str] = mapped_column(String(80), nullable=False)
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    tri_value: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    ntr_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    raw_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class BenchmarkSyncRun(Base):
    """Append-only audit record for a successful benchmark data fetch."""

    __tablename__ = "benchmark_sync_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["benchmark_code"],
            ["benchmark_indices.benchmark_code"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    benchmark_code: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
