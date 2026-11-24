"""Historical mutual fund NAV observations."""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mutual_fund_agent_analysis.database.base import Base

if TYPE_CHECKING:
    from mutual_fund_agent_analysis.models.scheme import MutualFundScheme


class NavObservation(Base):
    """One source-reported NAV value per scheme and valuation date."""

    __tablename__ = "nav_observations"
    __table_args__ = (CheckConstraint("nav > 0", name="ck_nav_observations_positive_nav"),)

    scheme_code: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("mutual_fund_schemes.scheme_code", ondelete="CASCADE"),
        primary_key=True,
    )
    nav_date: Mapped[date] = mapped_column(Date, primary_key=True)
    nav: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    scheme: Mapped["MutualFundScheme"] = relationship(back_populates="nav_observations")
