"""Research intelligence request and response contracts."""

# ruff: noqa: E501
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class HoldingInput(BaseModel):
    security_key: str = Field(min_length=2, max_length=160)
    isin: str | None = Field(default=None, max_length=20)
    security_name: str = Field(min_length=1, max_length=300)
    sector: str | None = Field(default=None, max_length=160)
    asset_class: Literal["equity", "debt", "cash", "derivative", "reit_invit", "gold", "other"] = (
        "equity"
    )
    quantity: Decimal | None = Field(default=None, ge=0)
    market_value: Decimal | None = Field(default=None, ge=0)
    weight_pct: Decimal | None = Field(default=None, ge=0, le=100)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortfolioImportRequest(BaseModel):
    scheme_code: int = Field(gt=0)
    source_key: str = Field(min_length=1, max_length=60)
    effective_date: date
    published_at: datetime | None = None
    document_url: HttpUrl | None = None
    content_hash: str = Field(min_length=32, max_length=128)
    total_market_value: Decimal | None = Field(default=None, ge=0)
    status: Literal["complete", "partial"] = "complete"
    holdings: list[HoldingInput] = Field(min_length=1, max_length=5000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("holdings")
    @classmethod
    def unique_securities(cls, rows: list[HoldingInput]) -> list[HoldingInput]:
        keys = [(row.security_key.upper(), row.asset_class) for row in rows]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate security_key and asset_class in one snapshot.")
        return rows


class EventInput(BaseModel):
    source_key: str = Field(min_length=1, max_length=60)
    external_id: str | None = Field(default=None, max_length=200)
    related_entity_id: int | None = Field(default=None, gt=0)
    evidence_id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=3, max_length=500)
    summary: str | None = None
    event_type: Literal[
        "results",
        "board_meeting",
        "dividend",
        "record_date",
        "split",
        "bonus",
        "merger",
        "acquisition",
        "fundraising",
        "management",
        "regulatory",
        "macro",
        "filing",
        "other",
    ] = "other"
    status: Literal[
        "confirmed", "scheduled", "reported", "unverified", "speculative", "disproved", "outdated"
    ] = "reported"
    event_date: date | None = None
    published_at: datetime | None = None
    canonical_url: HttpUrl | None = None
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SocialPostInput(BaseModel):
    source_key: Literal["reddit", "x"]
    external_id: str = Field(min_length=1, max_length=200)
    related_entity_id: int | None = Field(default=None, gt=0)
    canonical_url: HttpUrl | None = None
    text_excerpt: str | None = Field(default=None, max_length=2000)
    content_hash: str = Field(min_length=32, max_length=128)
    published_at: datetime | None = None
    engagement_count: int = Field(default=0, ge=0)
    sentiment_label: Literal["positive", "neutral", "negative"] | None = None
    sentiment_score: Decimal | None = Field(default=None, ge=-1, le=1)
    sentiment_model: str | None = Field(default=None, max_length=100)
    is_spam: bool = False
    expires_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentMetadata(BaseModel):
    source_key: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=1, max_length=500)
    scheme_code: int | None = Field(default=None, gt=0)
    related_entity_id: int | None = Field(default=None, gt=0)
    published_at: datetime | None = None
    effective_date: date | None = None
    canonical_url: HttpUrl | None = None


class PortfolioCompareRequest(BaseModel):
    scheme_codes: list[int] = Field(min_length=2, max_length=20)


class EntityExposureResponse(BaseModel):
    security_key: str
    effective_date: date
    funds: list[dict[str, Any]]
    total_fund_count: int


class PortfolioSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    snapshot_id: int
    scheme_code: int
    source_key: str
    effective_date: date
    published_at: datetime | None
    status: str
    content_hash: str
    total_market_value: Decimal | None
    holdings_count: int


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    event_id: int
    title: str
    event_type: str
    status: str
    event_date: date | None
    published_at: datetime | None
    source_key: str
    canonical_url: str | None
    related_entity_id: int | None


class SocialAnalyticsResponse(BaseModel):
    from_date: date | None
    to_date: date | None
    post_count: int
    coverage_entity_count: int
    average_sentiment: Decimal | None
    sentiment_distribution: dict[str, int]
    discussion_volume_by_day: list[dict[str, Any]]


class DocumentSearchResponse(BaseModel):
    query: str
    results: list[dict[str, Any]]
    retrieval_mode: str


class DocumentAskRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)
    scheme_code: int | None = Field(default=None, gt=0)
    top_k: int = Field(default=6, ge=1, le=15)
