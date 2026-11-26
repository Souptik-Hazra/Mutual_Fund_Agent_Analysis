"""Typed API contracts for scheme discovery and fund analysis."""

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SchemeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scheme_code: int
    scheme_name: str
    fund_house: str | None = None
    scheme_type: str | None = None
    scheme_category: str | None = None
    isin_growth: str | None = None
    isin_div_reinvestment: str | None = None
    lifecycle_type: str | None = None
    plan_type: str | None = None
    option_type: str | None = None
    launch_date: date | None = None
    closure_date: date | None = None
    effective_expense_ratio: Decimal | None = None
    expense_ratio_effective_date: date | None = None


class SchemePage(BaseModel):
    items: list[SchemeSummary]
    total: int
    limit: int
    offset: int


class DiscoveredScheme(BaseModel):
    scheme_code: int
    scheme_name: str


class SchemeDiscoveryResponse(BaseModel):
    provider: Literal["mfapi"] = "mfapi"
    query: str
    count: int
    items: list[DiscoveredScheme]


class SchemeDetail(SchemeSummary):
    latest_nav: Decimal | None = None
    latest_nav_date: date | None = None
    reconciliation_status: Literal["single_source", "matched", "conflict"] | None = None
    latest_canonical_source: str | None = None


class FundAnalyticsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheme_code: int
    observation_count: int
    start_date: date
    end_date: date
    absolute_return: Decimal
    cagr: Decimal
    rolling_returns: list[dict[str, Any]]
    calendar_year_returns: list[tuple[int, Decimal]]
    risk: dict[str, Any]
    drawdown: dict[str, Any]
    benchmark: dict[str, Any] | None
    annual_risk_free_rate: Decimal
    periods_per_year: int
    benchmark_code: str | None
    benchmark_source: str | None
    nav_conflict_dates: list[date]
    calendar_year_as_of_date: date | None
    frequency: Literal["daily", "weekly", "monthly", "quarterly", "yearly"]
    return_basis: Literal[
        "nav_only_excludes_idcw",
        "growth_nav_total_return",
        "idcw_payout_total_return",
        "idcw_reinvested_total_return",
    ] = "nav_only_excludes_idcw"
    benchmark_return_basis: Literal["tri"] | None = None
    distribution_coverage_status: str = "not_required"
    benchmark_unavailable_reason: str | None = None
    base100_series: list[tuple[date, Decimal]] = Field(default_factory=list)
    methodology: dict[str, str] = Field(default_factory=dict)


class FundComparisonRequest(BaseModel):
    scheme_codes: list[int] = Field(min_length=2, max_length=5)
    benchmark_code: str | None = Field(default=None, min_length=1, max_length=80)
    start_date: date | None = None
    end_date: date | None = None
    annual_risk_free_rate: Decimal = Decimal("0")
    periods_per_year: int = Field(default=252, ge=1, le=366)
    benchmark_source: str = Field(default="niftyindices", min_length=1, max_length=40)
    allow_nav_conflicts: bool = False
    calendar_year_as_of_date: date | None = None
    frequency: Literal["daily", "weekly", "monthly", "quarterly", "yearly"] = "daily"

    @field_validator("scheme_codes")
    @classmethod
    def validate_scheme_codes(cls, value: list[int]) -> list[int]:
        if any(isinstance(code, bool) or code <= 0 for code in value):
            raise ValueError("scheme_codes must contain positive integer codes.")
        if len(value) != len(set(value)):
            raise ValueError("scheme_codes must be unique.")
        return value

    @field_validator("annual_risk_free_rate")
    @classmethod
    def validate_risk_free_rate(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= Decimal("-1"):
            raise ValueError("annual_risk_free_rate must be finite and greater than -1.")
        return value

    @model_validator(mode="after")
    def validate_date_range(self) -> "FundComparisonRequest":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date.")
        return self


class FundComparisonResponse(BaseModel):
    scheme_codes: list[int]
    observation_count: int
    start_date: date
    end_date: date
    funds: list[FundAnalyticsResponse]
    benchmark_code: str | None
    frequency: Literal["daily", "weekly", "monthly", "quarterly", "yearly"] = "daily"
    comparability_warnings: list[str] = Field(default_factory=list)
