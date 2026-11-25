"""Personal investor transaction ledger."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from mutual_fund_agent_analysis.database.base import Base

_ID = BigInteger().with_variant(Integer, "sqlite")

_UNIT_TRANSACTION_TYPES = (
    "'purchase', 'sip', 'additional_purchase', 'redemption', 'switch_in', 'switch_out'"
)


class InvestorTransaction(Base):
    """One user-entered transaction; amounts and units are stored as positive magnitudes."""

    __tablename__ = "investor_transactions"
    __table_args__ = (
        CheckConstraint(
            "transaction_type IN "
            "('purchase', 'sip', 'additional_purchase', 'redemption', "
            "'switch_in', 'switch_out', 'dividend_payout', 'charges', 'tax')",
            name="ck_investor_transactions_type",
        ),
        CheckConstraint("amount > 0", name="ck_investor_transactions_amount"),
        CheckConstraint(
            "("
            "transaction_type IN "
            "('purchase', 'sip', 'additional_purchase', 'redemption', 'switch_in', 'switch_out') "
            "AND units IS NOT NULL AND units > 0"
            ") OR ("
            "transaction_type IN ('dividend_payout', 'charges', 'tax') AND units IS NULL"
            ")",
            name="ck_investor_transactions_units",
        ),
        CheckConstraint("nav IS NULL OR nav > 0", name="ck_investor_transactions_nav"),
        CheckConstraint("currency = 'INR'", name="ck_investor_transactions_currency"),
        UniqueConstraint(
            "scheme_code",
            "external_reference",
            name="uq_investor_transaction_external_reference",
        ),
        Index("ix_investor_transactions_scheme_date", "scheme_code", "transaction_date"),
    )

    transaction_id: Mapped[int] = mapped_column(_ID, primary_key=True, autoincrement=True)
    scheme_code: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("mutual_fund_schemes.scheme_code", ondelete="CASCADE"),
        nullable=False,
    )
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    units: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    nav: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    folio_reference: Mapped[str | None] = mapped_column(String(100))
    external_reference: Mapped[str | None] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
