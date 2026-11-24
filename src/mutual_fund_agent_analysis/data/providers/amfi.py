"""AMFI official NAV history adapter.

AMFI's public historical report is a semicolon-delimited text export, not a
stable JSON API. Parsing is deliberately strict and covered by format fixtures.
"""

import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AMFINavMetadata(BaseModel):
    """Scheme metadata available in AMFI historical NAV rows."""

    model_config = ConfigDict(extra="forbid")
    scheme_code: int = Field(gt=0)
    scheme_name: str = Field(min_length=1)
    fund_house: str | None = None
    scheme_type: str | None = None
    scheme_category: str | None = None
    isin_growth: str | None = None
    isin_div_reinvestment: str | None = None


class AMFINavPoint(BaseModel):
    """One validated AMFI NAV observation."""

    date: date
    nav: Decimal

    @field_validator("nav", mode="before")
    @classmethod
    def parse_nav(cls, value: Any) -> Decimal:
        try:
            parsed = Decimal(str(value).strip())
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("AMFI NAV must be a valid decimal.") from exc
        if not parsed.is_finite() or parsed <= 0:
            raise ValueError("AMFI NAV must be finite and greater than zero.")
        return parsed


class AMFINavResponse(BaseModel):
    """Normalized response shape shared with the repository layer."""

    meta: AMFINavMetadata
    data: list[AMFINavPoint]
    raw_payload: dict[str, Any] | None = None


class AMFIClient:
    """Fetch scheme NAV history from AMFI's public historical report."""

    source = "amfi"
    base_url = "https://portal.amfiindia.com"

    def __init__(
        self,
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        chunk_days: int = 31,
    ) -> None:
        if not 1 <= chunk_days <= 31:
            raise ValueError("chunk_days must be between 1 and 31.")
        self.chunk_days = chunk_days
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            headers={"User-Agent": "MutualFundAgentAnalysis/0.1 (NAV research)"},
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "AMFIClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _get_text(self, start_date: date, end_date: date) -> str:
        params = {
            "tp": "1",
            "frmdt": start_date.strftime("%d-%b-%Y"),
            "todt": end_date.strftime("%d-%b-%Y"),
        }
        for attempt in range(3):
            try:
                response = self._client.get("/DownloadNAVHistoryReport_Po.aspx", params=params)
                response.raise_for_status()
                report = response.text.lstrip("\ufeff")
                if not report.strip():
                    raise ValueError("AMFI returned an empty NAV history report.")
                return report
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                retryable = not isinstance(exc, httpx.HTTPStatusError) or (
                    exc.response.status_code == 429 or exc.response.status_code >= 500
                )
                if not retryable or attempt == 2:
                    raise
                delay = 0.5 * (2**attempt)
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                    retry_after = exc.response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except ValueError:
                            try:
                                retry_at = parsedate_to_datetime(retry_after)
                                delay = max(
                                    0.0,
                                    (retry_at - datetime.now(retry_at.tzinfo)).total_seconds(),
                                )
                            except (TypeError, ValueError, OverflowError):
                                pass
                time.sleep(min(max(delay, 0.0), 30.0))
        raise RuntimeError("AMFI request failed without an exception.")

    @staticmethod
    def _parse_date(value: str) -> date:
        return datetime.strptime(value.strip().title(), "%d-%b-%Y").date()

    @classmethod
    def _parse_report(
        cls, report: str, scheme_code: int
    ) -> tuple[str | None, list[AMFINavPoint]]:
        scheme_name: str | None = None
        observations: list[AMFINavPoint] = []
        seen_dates: set[date] = set()

        for line_number, line in enumerate(report.splitlines(), start=1):
            fields = [field.strip() for field in line.strip().split(";")]
            if not fields or not fields[0].isdigit():
                continue
            if len(fields) < 6 or int(fields[0]) != scheme_code:
                continue
            try:
                if len(fields) >= 8:
                    # Historical report: code;name;ISIN1;ISIN2;NAV;repurchase;sale;date
                    name, nav_value, date_value = fields[1], fields[4], fields[7]
                else:
                    # Legacy six-column row: code;ISIN1;ISIN2;name;NAV;date
                    name, nav_value, date_value = fields[3], fields[4], fields[5]
                if not date_value:
                    continue
                nav_date = cls._parse_date(date_value)
                nav_value_decimal = Decimal(nav_value)
            except (IndexError, InvalidOperation, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Malformed AMFI NAV row at line {line_number} for scheme {scheme_code}."
                ) from exc

            if not nav_value_decimal.is_finite() or nav_value_decimal <= 0:
                # Zero-valued liquidation rows are not usable prices for return calculations.
                continue
            if nav_date in seen_dates:
                raise ValueError(
                    f"AMFI returned duplicate NAV date {nav_date} for scheme {scheme_code}."
                )
            seen_dates.add(nav_date)
            scheme_name = name or scheme_name
            observations.append(AMFINavPoint(date=nav_date, nav=nav_value_decimal))

        observations.sort(key=lambda point: point.date)
        return scheme_name, observations

    def get_nav_history(
        self,
        scheme_code: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> AMFINavResponse:
        """Fetch history in bounded windows and return only the requested scheme."""
        if scheme_code <= 0:
            raise ValueError("Scheme code must be a positive integer.")
        end = end_date or date.today()
        start = start_date or (end - timedelta(days=6))
        if start > end:
            raise ValueError("start_date cannot be later than end_date.")

        chunks: list[str] = []
        points_by_date: dict[date, AMFINavPoint] = {}
        scheme_name: str | None = None
        cursor = start
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=self.chunk_days - 1), end)
            report = self._get_text(cursor, chunk_end)
            chunks.append(report)
            parsed_name, points = self._parse_report(report, scheme_code)
            if parsed_name:
                scheme_name = parsed_name
            for point in points:
                if not cursor <= point.date <= chunk_end:
                    raise ValueError("AMFI returned a NAV outside the requested date window.")
                if point.date in points_by_date:
                    raise ValueError(
                        f"AMFI returned duplicate NAV date {point.date} across report windows."
                    )
                points_by_date[point.date] = point
            cursor = chunk_end + timedelta(days=1)

        if not points_by_date or not scheme_name:
            raise ValueError(
                f"AMFI returned no positive NAV observations for scheme {scheme_code} "
                f"between {start} and {end}."
            )
        return AMFINavResponse(
            meta=AMFINavMetadata(scheme_code=scheme_code, scheme_name=scheme_name),
            data=sorted(points_by_date.values(), key=lambda point: point.date),
            raw_payload={
                "provider": self.source,
                "endpoint": f"{self.base_url}/DownloadNAVHistoryReport_Po.aspx",
                "scheme_code": scheme_code,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "format": "semicolon-delimited AMFI historical report",
                "chunks": len(chunks),
                "raw_text": "\n".join(chunks),
            },
        )
