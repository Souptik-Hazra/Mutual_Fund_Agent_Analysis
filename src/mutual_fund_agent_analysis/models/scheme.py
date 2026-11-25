"""Mutual fund scheme master model."""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mutual_fund_agent_analysis.database.base import Base

if TYPE_CHECKING:
    from mutual_fund_agent_analysis.models.nav import NavObservation


class MutualFundScheme(Base):
    """Canonical scheme metadata keyed by the AMFI scheme code."""

    __tablename__ = "mutual_fund_schemes"

    scheme_code: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scheme_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    fund_house: Mapped[str | None] = mapped_column(String(250))
    scheme_type: Mapped[str | None] = mapped_column(String(120))
    scheme_category: Mapped[str | None] = mapped_column(String(250))
    isin_growth: Mapped[str | None] = mapped_column(String(12), index=True)
    isin_div_reinvestment: Mapped[str | None] = mapped_column(String(12), index=True)
    lifecycle_type: Mapped[str | None] = mapped_column(String(20))
    plan_type: Mapped[str | None] = mapped_column(String(20))
    option_type: Mapped[str | None] = mapped_column(String(30))
    launch_date: Mapped[date | None] = mapped_column(Date)
    closure_date: Mapped[date | None] = mapped_column(Date)
    effective_expense_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    expense_ratio_effective_date: Mapped[date | None] = mapped_column(Date)
    expense_ratio_source_key: Mapped[str | None] = mapped_column(
        ForeignKey("data_sources.source_key", ondelete="RESTRICT")
    )
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="mfapi")
    source_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    nav_observations: Mapped[list["NavObservation"]] = relationship(
        back_populates="scheme", cascade="all, delete-orphan"
    )
