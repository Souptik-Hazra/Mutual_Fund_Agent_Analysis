"""Typed HTTP adapter for the MFAPI.in public NAV API.

MFAPI is treated as an upstream convenience provider. Store source metadata and
validate every response; AMFI remains the primary reference for NAV verification.
"""

import time
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator


class MFAPIScheme(BaseModel):
    """Scheme identifier returned by MFAPI search/list endpoints."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    scheme_code: int = Field(alias="schemeCode", gt=0)
    scheme_name: str = Field(alias="schemeName", min_length=1)


class MFAPINavPoint(BaseModel):
    """One published NAV observation."""

    date: date
    nav: Decimal

    @field_validator("date", mode="before")
    @classmethod
    def parse_provider_date(cls, value: Any) -> date:
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            raise ValueError("NAV date must be a string in DD-MM-YYYY format.")
        return datetime.strptime(value, "%d-%m-%Y").date()

    @field_validator("nav", mode="before")
    @classmethod
    def parse_provider_nav(cls, value: Any) -> Decimal:
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("NAV must be a valid decimal value.") from exc
        if not parsed.is_finite() or parsed <= 0:
            raise ValueError("NAV must be finite and greater than zero.")
        return parsed


class MFAPISchemeMetadata(BaseModel):
    """Provider metadata for a mutual fund scheme."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    scheme_code: int = Field(alias="scheme_code", gt=0)
    scheme_name: str = Field(alias="scheme_name", min_length=1)
    fund_house: str | None = None
    scheme_type: str | None = None
    scheme_category: str | None = None
    isin_growth: str | None = None
    isin_div_reinvestment: str | None = None


class MFAPINavResponse(BaseModel):
    """Validated MFAPI scheme NAV-history response."""

    meta: MFAPISchemeMetadata
    data: list[MFAPINavPoint]
    status: str
    raw_payload: dict[str, Any] | None = Field(default=None, exclude=True)


class MFAPIClient:
    """Small synchronous HTTP client with explicit timeouts and bounded retries."""

    source = "mfapi"

    def __init__(
        self,
        base_url: str = "https://api.mfapi.in",
        timeout_seconds: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
            headers={"User-Agent": "MutualFundAgentAnalysis/0.1 (+personal research)"},
            transport=transport,
        )

    def close(self) -> None:
        """Close the underlying connection pool."""
        self._client.close()

    def __enter__(self) -> "MFAPIClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _get_json(self, path: str, params: dict[str, str] | None = None) -> Any:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self._client.get(path, params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                retryable = not isinstance(exc, httpx.HTTPStatusError) or (
                    exc.response.status_code == 429 or exc.response.status_code >= 500
                )
                if not retryable or attempt == 2:
                    raise
                retry_after = None
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                    header = exc.response.headers.get("Retry-After")
                    if header:
                        try:
                            retry_after = float(header)
                        except ValueError:
                            try:
                                retry_date = parsedate_to_datetime(header)
                                if retry_date.tzinfo is None:
                                    retry_date = retry_date.replace(tzinfo=UTC)
                                retry_after = (retry_date - datetime.now(UTC)).total_seconds()
                            except (TypeError, ValueError, OverflowError):
                                retry_after = None
                delay = retry_after if retry_after is not None else 0.5 * (2**attempt)
                time.sleep(min(max(delay, 0.0), 30.0))
        if last_error is not None:
            raise last_error
        raise RuntimeError("MFAPI request failed without an exception.")

    def search_schemes(self, query: str) -> list[MFAPIScheme]:
        """Search schemes by name and return validated scheme codes."""
        normalized = query.strip()
        if len(normalized) < 2:
            raise ValueError("Scheme search query must contain at least two characters.")
        payload = self._get_json("/mf/search", params={"q": normalized})
        if not isinstance(payload, list):
            raise ValueError("MFAPI returned an unexpected scheme-search response.")
        return [MFAPIScheme.model_validate(item) for item in payload]

    def get_nav_history(
        self,
        scheme_code: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> MFAPINavResponse:
        """Fetch and validate one scheme's NAV history, optionally date bounded."""
        if scheme_code <= 0:
            raise ValueError("Scheme code must be a positive integer.")
        if start_date and end_date and start_date > end_date:
            raise ValueError("start_date cannot be later than end_date.")

        params: dict[str, str] = {}
        if start_date:
            params["startDate"] = start_date.isoformat()
        if end_date:
            params["endDate"] = end_date.isoformat()

        payload = self._get_json(f"/mf/{scheme_code}", params=params or None)
        response = MFAPINavResponse.model_validate(payload)
        response.raw_payload = payload
        if response.status.upper() != "SUCCESS":
            raise ValueError(f"MFAPI did not return SUCCESS for scheme {scheme_code}.")
        if response.meta.scheme_code != scheme_code:
            raise ValueError("MFAPI response scheme code does not match the requested code.")

        unique_dates = [point.date for point in response.data]
        if len(unique_dates) != len(set(unique_dates)):
            raise ValueError("MFAPI response contains duplicate NAV dates.")
        if start_date and any(point.date < start_date for point in response.data):
            raise ValueError("MFAPI returned NAV observations before start_date.")
        if end_date and any(point.date > end_date for point in response.data):
            raise ValueError("MFAPI returned NAV observations after end_date.")
        return response
