"""Audit records for successful provider synchronization runs."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mutual_fund_agent_analysis.database.base import Base


class ProviderSyncRun(Base):
    """One completed provider fetch, including its original response payload."""

    __tablename__ = "provider_sync_runs"
    __table_args__ = (
        Index("ix_provider_sync_runs_scheme_source_fetched", "scheme_code", "source", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    scheme_code: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("mutual_fund_schemes.scheme_code", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
