"""Typed API contracts for the common intelligence foundation."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DataSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    source_key: str
    display_name: str
    source_type: str
    authority_tier: int
    is_official: bool
    base_url: str | None
    terms_url: str | None
    attribution_required: bool
    enabled: bool
    metadata_json: dict[str, Any]


class EntityCreateRequest(BaseModel):
    entity_type: Literal[
        "amc", "scheme", "company", "security", "sector", "benchmark",
        "index", "person", "event", "regulator", "other"
    ]
    canonical_name: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)

    @field_validator("canonical_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("canonical_name cannot be blank.")
        return " ".join(value.split())


class EntityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    entity_id: int
    entity_type: str
    canonical_name: str
    normalized_name: str
    description: str | None
    status: str
    merged_into_entity_id: int | None
    created_at: datetime
    updated_at: datetime


class AliasCreateRequest(BaseModel):
    alias: str = Field(min_length=1, max_length=300)
    alias_type: str = Field(default="common", min_length=1, max_length=30)
    source_key: str | None = Field(default=None, max_length=60)
    valid_from: date | None = None
    valid_to: date | None = None
    is_primary: bool = False

    @model_validator(mode="after")
    def validate_range(self):
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must be on or after valid_from.")
        if not self.alias.strip():
            raise ValueError("alias cannot be blank.")
        return self


class AliasResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    alias_id: int
    entity_id: int
    alias: str
    normalized_alias: str
    alias_type: str
    source_key: str | None
    valid_from: date | None
    valid_to: date | None
    is_primary: bool
    created_at: datetime


class IdentifierCreateRequest(BaseModel):
    namespace: str = Field(min_length=2, max_length=60)
    identifier_value: str = Field(min_length=1, max_length=160)
    source_key: str | None = Field(default=None, max_length=60)
    valid_from: date | None = None
    valid_to: date | None = None
    is_primary: bool = False

    @model_validator(mode="after")
    def validate_range(self):
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must be on or after valid_from.")
        return self


class IdentifierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    identifier_id: int
    entity_id: int
    namespace: str
    identifier_value: str
    normalized_value: str
    source_key: str | None
    valid_from: date | None
    valid_to: date | None
    is_primary: bool
    created_at: datetime


class EvidenceCreateRequest(BaseModel):
    source_key: str = Field(min_length=1, max_length=60)
    external_id: str | None = Field(default=None, max_length=200)
    canonical_url: str | None = Field(default=None, max_length=1000)
    title: str | None = Field(default=None, max_length=500)
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    content_hash: str | None = Field(default=None, max_length=128)
    verification_status: Literal[
        "unverified", "corroborated", "verified", "disputed", "retracted"
    ] = "unverified"
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_effective_range(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from.")
        return self


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    evidence_id: int
    source_key: str
    external_id: str | None
    canonical_url: str | None
    title: str | None
    published_at: datetime | None
    retrieved_at: datetime
    effective_from: date | None
    effective_to: date | None
    content_hash: str | None
    verification_status: str
    confidence: Decimal | None
    metadata_json: dict[str, Any]


class EntityEvidenceLinkRequest(BaseModel):
    relation_type: str = Field(default="mentions", min_length=1, max_length=40)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    resolution_method: Literal["identifier", "exact_alias", "manual", "model_reviewed"] = "manual"
    verified_at: datetime | None = None


class EntityEvidenceLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    entity_id: int
    evidence_id: int
    relation_type: str
    confidence: Decimal | None
    resolution_method: str
    verified_at: datetime | None
    created_at: datetime


class EntityResolveRequest(BaseModel):
    entity_type: str | None = Field(default=None, max_length=30)
    namespace: str | None = Field(default=None, max_length=60)
    identifier_value: str | None = Field(default=None, max_length=160)
    alias: str | None = Field(default=None, max_length=300)
    as_of: date | None = None

    @model_validator(mode="after")
    def require_lookup_key(self):
        if bool(self.namespace) != bool(self.identifier_value):
            raise ValueError("namespace and identifier_value must be supplied together.")
        if not self.namespace and not self.alias:
            raise ValueError("Provide an identifier or an alias to resolve.")
        return self


class EntityResolveResponse(BaseModel):
    status: Literal["resolved", "ambiguous", "not_found"]
    matched_by: str | None
    entity: EntityResponse | None
    candidates: list[EntityResponse]
