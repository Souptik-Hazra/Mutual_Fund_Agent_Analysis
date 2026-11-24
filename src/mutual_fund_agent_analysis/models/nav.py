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
    PrimaryKeyConstraint,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mutual_fund_agent_analysis.database.base import Base

if TYPE_CHECKING:
    from mutual_fund_agent_analysis.models.scheme import MutualFundScheme


class NavObservation(Base):
    """One provider-reported NAV value per scheme, date, and source."""

    __tablename__ = "nav_observations"
    __table_args__ = (
        CheckConstraint("nav > 0", name="ck_nav_observations_positive_nav"),
        PrimaryKeyConstraint(
            "scheme_code", "nav_date", "source", name="pk_nav_observations"
        ),
    )

    scheme_code: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("mutual_fund_schemes.scheme_code", ondelete="CASCADE"),
        nullable=False,
    )
    nav_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    nav: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    scheme: Mapped["MutualFundScheme"] = relationship(back_populates="nav_observations")
