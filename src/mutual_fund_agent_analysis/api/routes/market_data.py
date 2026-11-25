"""Opt-in market quote ingestion from Twelve Data."""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.analytics.security_intelligence import security_profile
from mutual_fund_agent_analysis.core.config import get_settings
from mutual_fund_agent_analysis.data.providers.twelvedata import TwelveDataClient
from mutual_fund_agent_analysis.database.session import get_db
from mutual_fund_agent_analysis.models.intelligence import DataSource
from mutual_fund_agent_analysis.models.security import SecurityMarketObservation

router = APIRouter(prefix="/market-data", tags=["market-data"])


class QuoteSyncRequest(BaseModel):
    security_key: str = Field(min_length=2, max_length=160)
    security_name: str = Field(min_length=1, max_length=300)
    symbol: str = Field(min_length=1, max_length=40)
    exchange: str = Field(min_length=2, max_length=12)
    isin: str | None = Field(default=None, max_length=20)


@router.post("/twelvedata/quote", status_code=201)
def sync_twelvedata_quote(
    payload: QuoteSyncRequest, session: Annotated[Session, Depends(get_db)]
) -> dict:
    """Fetch and persist one quote; never poll or imply a live stream."""
    settings = get_settings()
    if not settings.twelve_data_api_key:
        raise HTTPException(status_code=503, detail="TWELVE_DATA_API_KEY is not configured.")
    if not settings.twelve_data_exchange_access_confirmed:
        raise HTTPException(
            status_code=403,
            detail=(
                "Confirm NSE/BSE exchange entitlement and personal-use rights "
                "before enabling this provider."
            ),
        )
    source = session.get(DataSource, "twelvedata")
    if source is None:
        source = DataSource(
            source_key="twelvedata",
            display_name="Twelve Data",
            source_type="provider",
            authority_tier=2,
            is_official=False,
            base_url="https://api.twelvedata.com",
            terms_url="https://twelvedata.com/terms",
            attribution_required=True,
            enabled=True,
            metadata_json={
                "exchange_access_confirmed_by_local_operator": True,
                "use": "personal_internal",
            },
        )
        session.add(source)
        session.flush()
    elif not source.enabled:
        raise HTTPException(status_code=409, detail="The Twelve Data source is disabled.")
    client = TwelveDataClient(settings.twelve_data_api_key.get_secret_value())
    try:
        quote = client.get_quote(payload.symbol, payload.exchange)
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502, detail=f"Twelve Data quote request failed: {exc}"
        ) from exc
    finally:
        client.close()
    canonical = {
        "security_key": payload.security_key.strip().upper(),
        "symbol": quote.symbol,
        "exchange": quote.exchange,
        "observed_at": quote.observed_at.isoformat(),
        "price": str(quote.price),
        "change_pct": str(quote.change_pct) if quote.change_pct is not None else None,
        "day_high": str(quote.day_high) if quote.day_high is not None else None,
        "day_low": str(quote.day_low) if quote.day_low is not None else None,
        "volume": quote.volume,
        "market_status": quote.market_status,
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    row = SecurityMarketObservation(
        security_key=payload.security_key.strip().upper(),
        isin=payload.isin.strip().upper() if payload.isin else None,
        security_name=payload.security_name.strip(),
        symbol=quote.symbol,
        exchange=quote.exchange,
        source_key="twelvedata",
        source_url=quote.source_url,
        observed_at=quote.observed_at,
        last_price=quote.price,
        change_pct=quote.change_pct,
        day_high=quote.day_high,
        day_low=quote.day_low,
        volume=quote.volume,
        market_status=quote.market_status,
        fundamentals_json={},
        corporate_events_json=[],
        content_hash=digest,
    )
    session.add(row)
    try:
        session.commit()
        session.refresh(row)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Duplicate quote observation or persistence constraint failure."
        ) from exc
    age = datetime.now(UTC) - row.observed_at.astimezone(UTC)
    return {
        "provider": "twelvedata",
        "availability": "stored",
        "freshness": "fresh" if age.total_seconds() <= 3600 else "stale",
        "observation": {
            "security_key": row.security_key,
            "symbol": row.symbol,
            "exchange": row.exchange,
            "observed_at": row.observed_at,
            "retrieved_at": row.retrieved_at,
            "last_price": row.last_price,
            "change_pct": row.change_pct,
            "day_high": row.day_high,
            "day_low": row.day_low,
            "volume": row.volume,
            "market_status": row.market_status,
            "source_key": row.source_key,
            "source_url": row.source_url,
        },
        "limitations": [
            "This is a provider quote observation, not a guaranteed real-time exchange tick.",
            "Fundamentals and corporate actions are not populated by this quote endpoint.",
            "Exchange coverage and use rights depend on the operator's active "
            "subscription and approvals.",
        ],
    }



class SecurityCorporateEvent(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    event_type: Literal[
        "results", "board_meeting", "dividend", "record_date", "split", "bonus",
        "merger", "acquisition", "fundraising", "management", "regulatory", "filing", "other",
    ] = "other"
    event_date: date | None = None
    status: Literal[
        "confirmed", "scheduled", "reported", "unverified", "speculative", "disproved", "outdated"
    ] = "reported"
    source_url: AnyHttpUrl | None = None


class SecurityObservationInput(BaseModel):
    security_key: str = Field(min_length=2, max_length=160)
    security_name: str = Field(min_length=2, max_length=300)
    symbol: str | None = Field(default=None, max_length=40)
    exchange: str | None = Field(default=None, max_length=12)
    isin: str | None = Field(default=None, max_length=20)
    source_key: str = Field(min_length=2, max_length=60)
    source_url: AnyHttpUrl | None = None
    observed_at: datetime
    fundamentals_as_of: date | None = None
    last_price: Decimal = Field(gt=0)
    change_pct: Decimal | None = Field(default=None, ge=-100)
    day_high: Decimal | None = Field(default=None, gt=0)
    day_low: Decimal | None = Field(default=None, gt=0)
    volume: int | None = Field(default=None, ge=0)
    market_status: Literal["trading", "halted", "closed", "unknown"] = "unknown"
    fundamentals: dict[str, Decimal | None] = Field(default_factory=dict)
    corporate_events: list[SecurityCorporateEvent] = Field(default_factory=list, max_length=100)

    @field_validator("fundamentals")
    @classmethod
    def validate_fundamentals(cls, values: dict[str, Decimal | None]) -> dict[str, Decimal | None]:
        allowed = {
            "market_cap", "pe_ratio", "pb_ratio", "roe_pct", "debt_to_equity",
            "dividend_yield_pct", "eps", "book_value", "revenue", "net_profit",
            "total_debt", "total_equity", "operating_margin_pct", "profit_margin_pct",
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"Unsupported fundamental metric(s): {', '.join(sorted(unknown))}")
        if any(value is not None and not value.is_finite() for value in values.values()):
            raise ValueError("Fundamental values must be finite decimals.")
        return values

    @model_validator(mode="after")
    def validate_observation(self) -> "SecurityObservationInput":
        if (
            not self.security_key.strip()
            or not self.security_name.strip()
            or not self.source_key.strip()
        ):
            raise ValueError("security_key, security_name and source_key cannot be blank.")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must include a timezone.")
        if self.day_high is not None and self.day_low is not None and self.day_high < self.day_low:
            raise ValueError("day_high cannot be lower than day_low.")
        if self.day_high is not None and self.last_price > self.day_high:
            raise ValueError("last_price cannot exceed day_high.")
        if self.day_low is not None and self.last_price < self.day_low:
            raise ValueError("last_price cannot be below day_low.")
        if self.observed_at > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("observed_at cannot be more than five minutes in the future.")
        if self.fundamentals and self.fundamentals_as_of is None:
            raise ValueError("fundamentals_as_of is required when fundamental metrics are supplied.")
        if self.fundamentals_as_of and self.fundamentals_as_of > self.observed_at.date():
            raise ValueError("fundamentals_as_of cannot be after observed_at.")
        return self


@router.post("/security-observations", status_code=201)
def ingest_security_observation(
    payload: SecurityObservationInput,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    """Persist a dated, source-attributed security observation without treating it as verified."""
    source = session.get(DataSource, payload.source_key)
    if source is None or not source.enabled:
        raise HTTPException(
            status_code=422, detail="source_key must reference an enabled data source."
        )
    canonical = payload.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    row = SecurityMarketObservation(
        security_key=payload.security_key.strip().upper(),
        isin=payload.isin.strip().upper() if payload.isin else None,
        security_name=payload.security_name.strip(),
        symbol=payload.symbol.strip().upper() if payload.symbol else None,
        exchange=payload.exchange.strip().upper() if payload.exchange else None,
        source_key=payload.source_key,
        source_url=str(payload.source_url) if payload.source_url else None,
        observed_at=payload.observed_at,
        fundamentals_as_of=payload.fundamentals_as_of,
        last_price=payload.last_price,
        change_pct=payload.change_pct,
        day_high=payload.day_high,
        day_low=payload.day_low,
        volume=payload.volume,
        market_status=payload.market_status,
        fundamentals_json={
            key: str(value) if value is not None else None
            for key, value in payload.fundamentals.items()
        },
        corporate_events_json=[
            {
                **event.model_dump(mode="json"),
                "source_key": payload.source_key,
                "verification_status": "unverified",
            }
            for event in payload.corporate_events
        ],
        content_hash=digest,
    )
    session.add(row)
    try:
        session.commit()
        session.refresh(row)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Duplicate or conflicting security observation."
        ) from exc
    return {
        "observation_id": row.observation_id,
        "security_key": row.security_key,
        "source_key": row.source_key,
        "observed_at": row.observed_at,
        "fundamentals_as_of": row.fundamentals_as_of,
        "content_hash": row.content_hash,
        "verification_status": "unverified",
        "message": (
            "Stored as an immutable source-attributed observation; "
            "verify the source before relying on it."
        ),
    }


@router.get("/securities/{security_key}")
def get_security_intelligence(
    security_key: str,
    session: Annotated[Session, Depends(get_db)],
    as_of: date | None = None,
    scheme_codes: list[int] | None = None,
) -> dict:
    """Return dated stock intelligence and matching positions from the latest AMC disclosures."""
    try:
        return security_profile(session, security_key, as_of=as_of, scheme_codes=scheme_codes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
