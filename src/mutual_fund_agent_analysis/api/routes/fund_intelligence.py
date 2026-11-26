"""Fund category, multi-fund holdings and underlying-equity intelligence APIs."""

import hashlib
import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.analytics.fund_intelligence import (
    analyze_category_peers,
    compare_disclosed_equity,
)
from mutual_fund_agent_analysis.database.session import get_db
from mutual_fund_agent_analysis.models.intelligence import DataSource
from mutual_fund_agent_analysis.models.research import PortfolioHolding, PortfolioSnapshot
from mutual_fund_agent_analysis.models.security import SecurityMarketObservation

router = APIRouter(prefix="/fund-intelligence", tags=["fund-intelligence"])


class FundCompareRequest(BaseModel):
    scheme_codes: list[Annotated[int, Field(strict=True, gt=0)]] = Field(min_length=2, max_length=5)

    @field_validator("scheme_codes")
    @classmethod
    def unique_positive_codes(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("scheme_codes must be unique.")
        return value


class MarketObservationRequest(BaseModel):
    security_key: str = Field(min_length=2, max_length=160)
    isin: str | None = Field(default=None, max_length=20)
    security_name: str = Field(min_length=1, max_length=300)
    symbol: str | None = Field(default=None, max_length=40)
    exchange: str | None = Field(default=None, max_length=12)
    source_key: str = Field(min_length=1, max_length=60)
    source_url: HttpUrl | None = None
    observed_at: datetime
    fundamentals_as_of: date | None = None
    last_price: Decimal = Field(gt=0)
    change_pct: Decimal | None = Field(default=None, ge=-100)
    day_high: Decimal | None = Field(default=None, gt=0)
    day_low: Decimal | None = Field(default=None, gt=0)
    volume: int | None = Field(default=None, ge=0)
    market_status: Literal["trading", "halted", "closed", "unknown"] = "unknown"
    fundamentals: dict[str, Decimal | None] = Field(default_factory=dict)
    corporate_events: list[dict[str, Any]] = Field(default_factory=list, max_length=100)

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone offset.")
        if value.astimezone(UTC) > datetime.now(UTC):
            raise ValueError("observed_at cannot be in the future.")
        return value

    @field_validator("fundamentals")
    @classmethod
    def validate_fundamentals(cls, value: dict[str, Decimal | None]):
        allowed = {
            "market_cap",
            "pe_ratio",
            "pb_ratio",
            "roe_pct",
            "debt_to_equity",
            "revenue_growth_pct",
            "profit_growth_pct",
            "promoter_pledge_pct",
            "dividend_yield_pct",
            "book_value",
        }
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"Unsupported fundamental fields: {sorted(unknown)}.")
        for key, metric in value.items():
            if metric is None:
                continue
            if not metric.is_finite():
                raise ValueError(f"{key} must be finite.")
            if key in {"market_cap", "debt_to_equity", "book_value"} and metric < 0:
                raise ValueError(f"{key} cannot be negative.")
            if key in {"promoter_pledge_pct", "dividend_yield_pct"} and not 0 <= metric <= 100:
                raise ValueError(f"{key} must be between 0 and 100.")
        return value

    @field_validator("security_key")
    @classmethod
    def normalize_security_key(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("security_key cannot be blank.")
        return normalized

    @field_validator("isin")
    @classmethod
    def normalize_isin(cls, value: str | None) -> str | None:
        return value.strip().upper() or None if value is not None else None


def _latest_market_observation(
    session: Session,
    security_key: str,
    isin: str | None = None,
    as_of: date | None = None,
):
    query = select(SecurityMarketObservation).order_by(
        SecurityMarketObservation.observed_at.desc(),
        SecurityMarketObservation.observation_id.desc(),
    )
    if as_of:
        cutoff = datetime.combine(as_of, time.max, tzinfo=UTC)
        query = query.where(SecurityMarketObservation.observed_at <= cutoff)
    if isin:
        exact_key_match = session.scalars(
            query.where(
                SecurityMarketObservation.security_key == security_key,
                or_(
                    SecurityMarketObservation.isin.is_(None),
                    SecurityMarketObservation.isin == isin,
                ),
            ).limit(1)
        ).first()
        if exact_key_match is not None:
            return exact_key_match
        return session.scalars(query.where(SecurityMarketObservation.isin == isin).limit(1)).first()
    return session.scalars(
        query.where(SecurityMarketObservation.security_key == security_key).limit(1)
    ).first()


def _market_payload(row: SecurityMarketObservation | None, *, as_of: date | None = None) -> dict:
    if row is None:
        return {
            "availability": "unavailable",
            "market_data": None,
            "message": "No provider observation is stored for this security at the requested date.",
        }
    observed = row.observed_at
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    reference_time = datetime.combine(as_of, time.max, tzinfo=UTC) if as_of else datetime.now(UTC)
    age = reference_time - observed.astimezone(UTC)
    age_seconds = max(0.0, age.total_seconds())
    freshness = "fresh" if age_seconds <= 72 * 3600 else "stale"
    fundamentals = row.fundamentals_json or {}
    signals = []
    for key, message in (
        ("pe_ratio", "Negative P/E may indicate negative earnings."),
        ("roe_pct", "Negative ROE indicates negative reported return on equity."),
        ("revenue_growth_pct", "Reported revenue growth is negative."),
        ("profit_growth_pct", "Reported profit growth is negative."),
    ):
        value = fundamentals.get(key)
        if value is not None and Decimal(str(value)) < 0:
            signals.append({"field": key, "message": message})
    pledged = fundamentals.get("promoter_pledge_pct")
    if pledged is not None and Decimal(str(pledged)) > 0:
        signals.append(
            {
                "field": "promoter_pledge_pct",
                "message": "Promoter shares are pledged; review the reported percentage.",
            }
        )
    if row.market_status == "halted":
        signals.append(
            {
                "field": "market_status",
                "message": "The provider reports the security as halted.",
            }
        )
    return {
        "availability": "available",
        "freshness": freshness,
        "age_hours": round(age_seconds / 3600, 2),
        "market_data": {
            "security_key": row.security_key,
            "isin": row.isin,
            "security_name": row.security_name,
            "symbol": row.symbol,
            "exchange": row.exchange,
            "source_key": row.source_key,
            "source_url": row.source_url,
            "observed_at": row.observed_at,
            "retrieved_at": row.retrieved_at,
            "fundamentals_as_of": row.fundamentals_as_of,
            "last_price": row.last_price,
            "change_pct": row.change_pct,
            "day_high": row.day_high,
            "day_low": row.day_low,
            "volume": row.volume,
            "market_status": row.market_status,
            "fundamentals": fundamentals,
            "fundamental_field_count": len(fundamentals),
            "health_signals": signals,
            "health_assessment": (
                "review_required"
                if signals
                else (
                    "no_flagged_condition_in_available_fields"
                    if fundamentals or row.market_status != "unknown"
                    else "insufficient_data"
                )
            ),
            "corporate_events": row.corporate_events_json,
        },
        "freshness_policy": (
            "Fresh means the observation is no more than 72 hours old relative to the "
            "requested as-of date (or current UTC time for current requests); verify "
            "exchange session and provider timestamp."
        ),
    }


@router.get("/schemes/{scheme_code}/category")
def category_analysis(
    scheme_code: int,
    session: Annotated[Session, Depends(get_db)],
    start_date: date | None = None,
    end_date: date | None = None,
    benchmark_code: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    benchmark_source: Annotated[str, Query(min_length=1, max_length=40)] = "niftyindices",
) -> dict:
    try:
        return analyze_category_peers(
            session,
            scheme_code,
            start_date,
            end_date,
            benchmark_code=benchmark_code,
            benchmark_source=benchmark_source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/compare")
def compare_fund_holdings(
    payload: FundCompareRequest,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    try:
        return compare_disclosed_equity(session, payload.scheme_codes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/schemes/{scheme_code}/equity-status")
def fund_equity_status(
    scheme_code: int,
    session: Annotated[Session, Depends(get_db)],
    as_of: date | None = None,
) -> dict:
    snapshot = session.scalars(
        select(PortfolioSnapshot)
        .where(
            PortfolioSnapshot.scheme_code == scheme_code,
            PortfolioSnapshot.status.in_(["complete", "partial"]),
            *([PortfolioSnapshot.effective_date <= as_of] if as_of else []),
        )
        .order_by(PortfolioSnapshot.effective_date.desc(), PortfolioSnapshot.retrieved_at.desc())
        .limit(1)
    ).first()
    if snapshot is None:
        raise HTTPException(
            status_code=404, detail="No portfolio disclosure found for this scheme."
        )
    holdings = session.scalars(
        select(PortfolioHolding)
        .where(
            PortfolioHolding.snapshot_id == snapshot.snapshot_id,
            PortfolioHolding.asset_class == "equity",
        )
        .order_by(PortfolioHolding.weight_pct.desc().nullslast())
    ).all()
    items = []
    for holding in holdings:
        market = _latest_market_observation(
            session, holding.security_key, holding.isin, as_of=as_of
        )
        items.append(
            {
                "security_key": holding.security_key,
                "isin": holding.isin,
                "security_name": holding.security_name,
                "sector": holding.sector,
                "disclosed_weight_pct": holding.weight_pct,
                "holding_asset_class": holding.asset_class,
                **_market_payload(market, as_of=as_of),
            }
        )
    return {
        "scheme_code": scheme_code,
        "snapshot_id": snapshot.snapshot_id,
        "holdings_as_of": snapshot.effective_date,
        "market_data_as_of": as_of,
        "snapshot_status": snapshot.status,
        "equity_security_count": len(items),
        "market_data_available_count": sum(item["availability"] == "available" for item in items),
        "items": items,
        "warning": (
            "Current security observations do not update or replace the fund's disclosed holdings."
        ),
    }


@router.get("/securities/{security_key}/market-status")
def security_market_status(
    security_key: str,
    session: Annotated[Session, Depends(get_db)],
    isin: str | None = Query(default=None, min_length=12, max_length=20),
    as_of: date | None = None,
) -> dict:
    return _market_payload(
        _latest_market_observation(session, security_key.strip().upper(), isin, as_of=as_of),
        as_of=as_of,
    )


@router.post("/market-observations", status_code=status.HTTP_201_CREATED)
def ingest_market_observation(
    payload: MarketObservationRequest,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    source = session.get(DataSource, payload.source_key)
    if source is None or not source.enabled or source.source_type not in {"provider", "official"}:
        raise HTTPException(
            status_code=422,
            detail="Register and enable an official or provider market-data source first.",
        )
    if (
        payload.day_high is not None
        and payload.day_low is not None
        and payload.day_high < payload.day_low
    ):
        raise HTTPException(
            status_code=422,
            detail="day_high must be greater than or equal to day_low.",
        )
    if payload.day_high is not None and payload.last_price > payload.day_high:
        raise HTTPException(status_code=422, detail="last_price cannot exceed day_high.")
    if payload.day_low is not None and payload.last_price < payload.day_low:
        raise HTTPException(status_code=422, detail="last_price cannot be below day_low.")
    canonical = payload.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    row = SecurityMarketObservation(
        **payload.model_dump(exclude={"fundamentals", "corporate_events", "source_url"}),
        source_url=str(payload.source_url) if payload.source_url else None,
        fundamentals_json=canonical["fundamentals"],
        corporate_events_json=canonical["corporate_events"],
        content_hash=digest,
    )
    session.add(row)
    try:
        session.commit()
        session.refresh(row)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Duplicate market observation or invalid source."
        ) from exc
    return _market_payload(row)
