"""Opt-in market quote ingestion from Twelve Data."""
import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
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
def sync_twelvedata_quote(payload: QuoteSyncRequest, session: Annotated[Session, Depends(get_db)]) -> dict:
    """Fetch and persist one quote; never poll or imply a live stream."""
    settings = get_settings()
    if not settings.twelve_data_api_key:
        raise HTTPException(status_code=503, detail="TWELVE_DATA_API_KEY is not configured.")
    if not settings.twelve_data_exchange_access_confirmed:
        raise HTTPException(status_code=403, detail="Confirm NSE/BSE exchange entitlement and personal-use rights before enabling this provider.")
    source = session.get(DataSource, "twelvedata")
    if source is None:
        source = DataSource(source_key="twelvedata", display_name="Twelve Data", source_type="provider", authority_tier=2, is_official=False, base_url="https://api.twelvedata.com", terms_url="https://twelvedata.com/terms", attribution_required=True, enabled=True, metadata_json={"exchange_access_confirmed_by_local_operator": True, "use": "personal_internal"})
        session.add(source)
        session.flush()
    elif not source.enabled:
        raise HTTPException(status_code=409, detail="The Twelve Data source is disabled.")
    client = TwelveDataClient(settings.twelve_data_api_key.get_secret_value())
    try:
        quote = client.get_quote(payload.symbol, payload.exchange)
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Twelve Data quote request failed: {exc}") from exc
    finally:
        client.close()
    canonical = {"security_key": payload.security_key.strip().upper(), "symbol": quote.symbol, "exchange": quote.exchange, "observed_at": quote.observed_at.isoformat(), "price": str(quote.price), "change_pct": str(quote.change_pct) if quote.change_pct is not None else None, "day_high": str(quote.day_high) if quote.day_high is not None else None, "day_low": str(quote.day_low) if quote.day_low is not None else None, "volume": quote.volume, "market_status": quote.market_status}
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    row = SecurityMarketObservation(security_key=payload.security_key.strip().upper(), isin=payload.isin.strip().upper() if payload.isin else None, security_name=payload.security_name.strip(), symbol=quote.symbol, exchange=quote.exchange, source_key="twelvedata", source_url=quote.source_url, observed_at=quote.observed_at, last_price=quote.price, change_pct=quote.change_pct, day_high=quote.day_high, day_low=quote.day_low, volume=quote.volume, market_status=quote.market_status, fundamentals_json={}, corporate_events_json=[], content_hash=digest)
    session.add(row)
    try:
        session.commit()
        session.refresh(row)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Duplicate quote observation or persistence constraint failure.") from exc
    age = datetime.now(UTC) - row.observed_at.astimezone(UTC)
    return {"provider": "twelvedata", "availability": "stored", "freshness": "fresh" if age.total_seconds() <= 3600 else "stale", "observation": {"security_key": row.security_key, "symbol": row.symbol, "exchange": row.exchange, "observed_at": row.observed_at, "retrieved_at": row.retrieved_at, "last_price": row.last_price, "change_pct": row.change_pct, "day_high": row.day_high, "day_low": row.day_low, "volume": row.volume, "market_status": row.market_status, "source_key": row.source_key, "source_url": row.source_url}, "limitations": ["This is a provider quote observation, not a guaranteed real-time exchange tick.", "Fundamentals and corporate actions are not populated by this quote endpoint.", "Exchange coverage and use rights depend on the operator's active subscription and approvals."]}
