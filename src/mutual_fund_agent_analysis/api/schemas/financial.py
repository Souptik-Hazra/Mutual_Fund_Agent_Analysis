"""API contracts for auditable scheme metadata and IDCW observations."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class SchemeMetadataObservationCreate(BaseModel):
    source_key: str = Field(min_length=1, max_length=60)
    source_url: HttpUrl
    valid_from: date | None = None
    valid_to: date | None = None
    plan_type: Literal["direct", "regular", "unknown"] | None = None
    option_type: (
        Literal["growth", "idcw_payout", "idcw_reinvestment", "idcw_transfer", "unknown"] | None
    ) = None
    lifecycle_type: Literal["open_ended", "close_ended", "interval", "unknown"] | None = None
    expense_ratio: Decimal | None = Field(default=None, ge=0, le=100)
    expense_ratio_effective_date: date | None = None
    benchmark_code: str | None = Field(default=None, max_length=80)
    launch_date: date | None = None
    closure_date: date | None = None
    verification_status: Literal["unverified", "verified", "disputed", "retracted"] = "unverified"
    verification_note: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to cannot precede valid_from.")
        if self.launch_date and self.closure_date and self.closure_date < self.launch_date:
            raise ValueError("closure_date cannot precede launch_date.")
        if self.expense_ratio is not None and self.expense_ratio_effective_date is None:
            raise ValueError("expense_ratio requires expense_ratio_effective_date.")
        return self


class SchemeMetadataObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    metadata_id: int
    scheme_code: int
    source_key: str
    source_url: str
    content_hash: str
    observed_at: datetime
    valid_from: date | None
    valid_to: date | None
    plan_type: str | None
    option_type: str | None
    lifecycle_type: str | None
    expense_ratio: Decimal | None
    expense_ratio_effective_date: date | None
    benchmark_code: str | None
    launch_date: date | None
    closure_date: date | None
    verification_status: str
    verification_note: str | None


class DistributionObservationCreate(BaseModel):
    source_key: str = Field(min_length=1, max_length=60)
    external_id: str = Field(min_length=1, max_length=200)
    revision: int = Field(default=1, ge=1)
    supersedes_distribution_id: int | None = Field(default=None, gt=0)
    source_url: HttpUrl
    ex_date: date
    record_date: date | None = None
    payment_date: date | None = None
    amount_per_unit: Decimal = Field(gt=0, max_digits=20, decimal_places=8)
    option_type: Literal["idcw_payout", "idcw_reinvestment", "idcw_transfer"]
    status: Literal["active", "revised", "cancelled"] = "active"
    verification_status: Literal["unverified", "verified", "disputed", "retracted"] = "unverified"
    published_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.record_date and self.record_date < self.ex_date:
            raise ValueError("record_date cannot precede ex_date.")
        if self.payment_date and self.record_date and self.payment_date < self.record_date:
            raise ValueError("payment_date cannot precede record_date.")
        return self


class DistributionObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    distribution_id: int
    scheme_code: int
    source_key: str
    external_id: str
    revision: int
    supersedes_distribution_id: int | None
    source_url: str
    content_hash: str
    ex_date: date
    record_date: date | None
    payment_date: date | None
    amount_per_unit: Decimal
    option_type: str
    status: str
    verification_status: str
    published_at: datetime | None
    observed_at: datetime


class DistributionCoverageAttestationCreate(BaseModel):
    source_key: str = Field(min_length=1, max_length=60)
    external_id: str = Field(min_length=1, max_length=200)
    source_url: HttpUrl
    start_date: date
    end_date: date
    coverage_complete: bool
    verification_status: Literal["unverified", "verified", "disputed", "retracted"] = "unverified"
    verification_note: str | None = Field(default=None, max_length=1000)
    published_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date.")
        if self.verification_status == "verified" and not self.coverage_complete:
            raise ValueError("A verified coverage attestation must claim complete coverage.")
        return self


class DistributionCoverageAttestationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attestation_id: int
    scheme_code: int
    source_key: str
    external_id: str
    source_url: str
    content_hash: str
    start_date: date
    end_date: date
    coverage_complete: bool
    verification_status: str
    verification_note: str | None
    published_at: datetime | None
    attested_at: datetime


class TotalReturnPointResponse(BaseModel):
    date: date
    nav: Decimal
    distribution_per_unit: Decimal
    nav_index: Decimal
    total_return_index: Decimal


class IDCWTotalReturnResponse(BaseModel):
    scheme_code: int
    start_date: date
    end_date: date
    status: Literal["ready", "blocked_incomplete_coverage"]
    return_basis: Literal["idcw_payout_total_return", "idcw_reinvested_total_return"]
    methodology: str
    coverage_complete: bool
    coverage_attestation_id: int | None
    observation_count: int
    series: list[TotalReturnPointResponse]
    limitations: list[str]


class CoverageAuditResponse(BaseModel):
    generated_at: datetime
    counts: dict[str, int]
    ranges: dict[str, dict[str, Any]]
    provider_sync: dict[str, Any]
