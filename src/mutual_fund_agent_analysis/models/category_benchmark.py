"""Effective-dated category-to-benchmark mappings."""
from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Identity, Integer, String, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from mutual_fund_agent_analysis.database.base import Base

class CategoryBenchmarkMapping(Base):
    """Explicit mapping; no benchmark is inferred when a mapping is absent."""
    __tablename__ = "category_benchmark_mappings"
    __table_args__ = (
        UniqueConstraint("scheme_category", "scheme_type", "plan_type", "option_type", "effective_from", name="uq_category_benchmark_effective"),
        Index("ix_category_benchmark_lookup", "scheme_category", "scheme_type", "plan_type", "option_type", "effective_from", "effective_to"),
    )
    mapping_id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    scheme_category: Mapped[str] = mapped_column(String(250), nullable=False)
    scheme_type: Mapped[str | None] = mapped_column(String(120))
    plan_type: Mapped[str | None] = mapped_column(String(20))
    option_type: Mapped[str | None] = mapped_column(String(30))
    benchmark_code: Mapped[str] = mapped_column(String(80), nullable=False)
    benchmark_source: Mapped[str] = mapped_column(String(40), nullable=False, default="niftyindices")
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    source_key: Mapped[str | None] = mapped_column(String(60), ForeignKey("data_sources.source_key", ondelete="RESTRICT"))
    rationale: Mapped[str] = mapped_column(String(1000), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
