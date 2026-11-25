"""Contracts for the personal investor ledger and investment analytics."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TransactionType = Literal[
    "purchase",
    "sip",
    "additional_purchase",
    "redemption",
    "switch_in",
    "switch_out",
    "dividend_payout",
    "charges",
    "tax",
]
_UNIT_TYPES = {
    "purchase",
    "sip",
    "additional_purchase",
    "redemption",
    "switch_in",
    "switch_out",
}


class InvestorTransactionCreate(BaseModel):
    transaction_date: date
    transaction_type: TransactionType
    amount: Decimal = Field(gt=0, max_digits=24, decimal_places=6)
    units: Decimal | None = Field(default=None, gt=0, max_digits=24, decimal_places=8)
    nav: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=8)
    currency: Literal["INR"] = "INR"
    folio_reference: str | None = Field(default=None, max_length=100)
    external_reference: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("amount", "units", "nav")
    @classmethod
    def validate_finite_decimal(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("Numeric values must be finite.")
        return value

    @model_validator(mode="after")
    def validate_units_and_nav(self) -> "InvestorTransactionCreate":
        if self.transaction_type in _UNIT_TYPES and self.units is None:
            raise ValueError("Unit-changing transactions require units.")
        if self.transaction_type not in _UNIT_TYPES and self.units is not None:
            raise ValueError("This transaction type must not contain units.")
        if self.nav is not None and self.units is None:
            raise ValueError("NAV can only be supplied when units are supplied.")
        for name in ("folio_reference", "external_reference", "notes"):
            value = getattr(self, name)
            if value is not None and not value.strip():
                raise ValueError(f"{name} must not be blank.")
        return self


class InvestorTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: int
    scheme_code: int
    transaction_date: date
    transaction_type: TransactionType
    amount: Decimal
    units: Decimal | None
    nav: Decimal | None
    currency: str
    folio_reference: str | None
    external_reference: str | None
    notes: str | None
    created_at: datetime


class SipSimulationRequest(BaseModel):
    start_date: date
    end_date: date
    valuation_date: date
    monthly_amount: Decimal = Field(gt=0, max_digits=24, decimal_places=6)
    day_of_month: int = Field(default=1, ge=1, le=31)

    @field_validator("monthly_amount")
    @classmethod
    def validate_amount_finite(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("monthly_amount must be finite.")
        return value

    @model_validator(mode="after")
    def validate_dates(self) -> "SipSimulationRequest":
        if self.start_date > self.end_date or self.valuation_date < self.end_date:
            raise ValueError("Require start_date <= end_date <= valuation_date.")
        return self


class SipInstallmentResponse(BaseModel):
    due_date: date
    amount: Decimal
    nav: Decimal | None
    units: Decimal
    status: str


class SipSimulationResponse(BaseModel):
    scheme_code: int
    installments: list[SipInstallmentResponse]
    scheduled_count: int
    invested_count: int
    missed_count: int
    invested_amount: Decimal
    units_allotted: Decimal
    valuation_date: date
    valuation_nav: Decimal
    current_value: Decimal
    absolute_gain: Decimal
    xirr: Decimal | None
    coverage_ratio: Decimal
    return_basis: Literal["simulated_sip"] = "simulated_sip"


class InvestorReturnsResponse(BaseModel):
    scheme_code: int
    as_of_date: date
    transaction_count: int
    total_units: Decimal
    cash_invested: Decimal
    realized_proceeds: Decimal
    expenses: Decimal
    current_value: Decimal
    valuation_nav: Decimal | None
    absolute_gain: Decimal
    xirr: Decimal | None
    xirr_limitation: str | None
    return_basis: Literal["actual_ledger"] = "actual_ledger"


class ActiveRiskResponse(BaseModel):
    scheme_code: int
    benchmark_code: str
    start_date: date
    end_date: date
    periods_per_year: int
    aligned_observation_count: int
    tracking_error: Decimal | None
    information_ratio: Decimal | None
    mean_active_return: Decimal | None
    coverage_ratio: Decimal
