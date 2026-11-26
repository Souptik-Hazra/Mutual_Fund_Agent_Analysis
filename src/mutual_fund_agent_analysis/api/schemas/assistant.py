"""Research assistant API contracts."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


class ResearchAssistantRequest(BaseModel):
    question: str = Field(min_length=5, max_length=1500)
    scheme_codes: list[int] = Field(default_factory=list, max_length=5)
    benchmark_code: str | None = Field(default=None, min_length=1, max_length=80)
    benchmark_source: str | None = Field(default=None, min_length=1, max_length=40)
    start_date: date | None = None
    end_date: date | None = None
    as_of_date: date | None = None
    annual_risk_free_rate: Decimal = Decimal("0")
    periods_per_year: int = Field(default=252, ge=1, le=366)
    top_k: int = Field(default=6, ge=1, le=15)
    synthesize: bool = Field(
        default=False,
        description="Opt in to LLM narrative synthesis; disabled by default.",
    )

    @field_validator("scheme_codes")
    @classmethod
    def validate_scheme_codes(cls, values: list[int]) -> list[int]:
        if any(isinstance(code, bool) or code <= 0 for code in values):
            raise ValueError("scheme_codes must contain positive integer codes.")
        if len(values) != len(set(values)):
            raise ValueError("scheme_codes must be unique.")
        return values

    @model_validator(mode="after")
    def validate_dates(self) -> "ResearchAssistantRequest":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date.")
        if self.end_date and self.as_of_date and self.as_of_date > self.end_date:
            raise ValueError("as_of_date cannot be later than end_date.")
        if not self.annual_risk_free_rate.is_finite() or self.annual_risk_free_rate <= -1:
            raise ValueError("annual_risk_free_rate must be finite and greater than -1.")
        return self
