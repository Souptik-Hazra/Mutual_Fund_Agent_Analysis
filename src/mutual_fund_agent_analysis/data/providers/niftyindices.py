"""NSE Indices historical TRI/NTR adapter.

The public historical-data page exposes an ASP.NET endpoint that is not a
versioned public API. Requests are split into at-most-365-day windows.
"""
import json
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator


class BenchmarkPoint(BaseModel):
    """One official benchmark total-return observation."""
    date: date
    tri: Decimal
    ntr: Decimal | None = None

    @field_validator("tri", "ntr", mode="before")
    @classmethod
    def parse_positive_decimal(cls, value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            parsed = Decimal(str(value).replace(",", "").strip())
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Index values must be valid decimals.") from exc
        if not parsed.is_finite() or parsed <= 0:
            raise ValueError("Index values must be finite and greater than zero.")
        return parsed


class BenchmarkResponse(BaseModel):
    """Normalized response returned by the Nifty Indices adapter."""
    model_config = ConfigDict(extra="forbid")
    benchmark_code: str = Field(min_length=1, max_length=80)
    benchmark_name: str = Field(min_length=1, max_length=160)
    data: list[BenchmarkPoint]
    raw_payload: dict[str, Any] | None = None


class NiftyIndicesClient:
    """Fetch daily TRI and NTR values for a Nifty benchmark."""
    source = "niftyindices"
    base_url = "https://www.niftyindices.com"
    endpoint = "/Backpage.aspx/getTotalReturnIndexString"
    referer = "https://www.niftyindices.com/reports/historical-data"

    def __init__(
        self,
        timeout_seconds: float = 45.0,
        transport: httpx.BaseTransport | None = None,
        max_attempts: int = 3,
        chunk_days: int = 365,
    ) -> None:
        if not 1 <= chunk_days <= 365:
            raise ValueError("chunk_days must be between 1 and 365.")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")
        self.chunk_days = chunk_days
        self.max_attempts = max_attempts
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            follow_redirects=True,
            transport=transport,
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.referer,
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 "
                    "MutualFundAgentAnalysis/0.1"
                ),
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "NiftyIndicesClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _parse_rows(payload: Any, benchmark_code: str) -> list[BenchmarkPoint]:
        if not isinstance(payload, dict) or "d" not in payload:
            raise ValueError("Unexpected Nifty Indices response: missing 'd' field.")
        rows = payload["d"]
        if isinstance(rows, str):
            try:
                rows = json.loads(rows)
            except json.JSONDecodeError as exc:
                raise ValueError("Nifty Indices returned invalid JSON in 'd'.") from exc
        if not isinstance(rows, list):
            raise ValueError("Nifty Indices 'd' field must contain a list.")

        points: list[BenchmarkPoint] = []
        seen: set[date] = set()
        for row_number, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise ValueError(f"Invalid Nifty Indices row {row_number}.")
            try:
                raw_date = (
                    row.get("Date") or row.get("date") or row.get("HistoricalDate")
                    or row.get("historicalDate")
                )
                raw_date = raw_date.strip()
                for date_format in ("%d %b %Y", "%d-%b-%Y"):
                    try:
                        observation_date = datetime.strptime(raw_date, date_format).date()
                        break
                    except ValueError:
                        continue
                else:
                    raise ValueError(f"Unsupported Nifty date format: {raw_date!r}")
                tri_value = (
                    row.get("TotalReturnsIndex") or row.get("totalReturnsIndex")
                    or row.get("Total Returns Index") or row.get("TRI")
                )
                ntr_value = (
                    row.get("NTR_Value") or row.get("NTRValue")
                    or row.get("Net Total Return Index") or row.get("NTR")
                )
                point = BenchmarkPoint(date=observation_date, tri=tri_value, ntr=ntr_value)
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Could not parse Nifty Indices row {row_number} for {benchmark_code}."
                ) from exc
            if point.date in seen:
                raise ValueError(
                    f"Duplicate benchmark observation date {point.date} for {benchmark_code}."
                )
            seen.add(point.date)
            points.append(point)

        points.sort(key=lambda item: item.date)
        return points

    @staticmethod
    def _retry_delay(attempt: int, retry_after: str | None = None) -> float:
        if retry_after:
            try:
                return min(max(float(retry_after), 0.0), 30.0)
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    return min(max((retry_at - datetime.now(retry_at.tzinfo)).total_seconds(), 0.0), 30.0)
                except (TypeError, ValueError, OverflowError):
                    pass
        return min(0.5 * (2**attempt), 10.0)

    def _fetch_chunk(self, name: str, start_date: date, end_date: date) -> Any:
        cinfo = (
            "{'name':'"
            + name
            + "','startDate':'"
            + start_date.strftime("%d-%b-%Y")
            + "','endDate':'"
            + end_date.strftime("%d-%b-%Y")
            + "','indexName':'"
            + name
            + "'}"
        )
        body = json.dumps({"cinfo": cinfo})
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                response = self._client.post(self.endpoint, content=body)
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, json.JSONDecodeError) as exc:
                last_error = exc
                retryable = not isinstance(exc, httpx.HTTPStatusError) or (
                    exc.response.status_code == 429 or exc.response.status_code >= 500
                )
                if not retryable or attempt + 1 == self.max_attempts:
                    raise
                retry_after = (
                    exc.response.headers.get("Retry-After")
                    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429
                    else None
                )
                time.sleep(self._retry_delay(attempt, retry_after))
        if last_error:
            raise last_error
        raise RuntimeError("Nifty Indices request failed without an exception.")

    def get_history(
        self,
        benchmark_code: str,
        start_date: date,
        end_date: date,
    ) -> BenchmarkResponse:
        """Fetch TRI/NTR history in bounded windows and combine observations."""
        name = benchmark_code.strip()
        if not name or len(name) > 160 or "'" in name:
            raise ValueError("benchmark_code must be a valid canonical Nifty index name.")
        if start_date > end_date:
            raise ValueError("start_date cannot be later than end_date.")

        points_by_date: dict[date, BenchmarkPoint] = {}
        raw_chunks: list[dict[str, Any]] = []
        cursor = start_date
        response_name = name
        while cursor <= end_date:
            chunk_end = min(cursor + timedelta(days=self.chunk_days - 1), end_date)
            raw_payload = self._fetch_chunk(name, cursor, chunk_end)
            points = self._parse_rows(raw_payload, name)
            for point in points:
                if not cursor <= point.date <= chunk_end:
                    raise ValueError("Nifty Indices returned an observation outside the requested range.")
                if point.date in points_by_date:
                    raise ValueError(
                        f"Duplicate benchmark observation date {point.date} across request windows."
                    )
                points_by_date[point.date] = point

            rows = raw_payload.get("d")
            if isinstance(rows, str):
                rows = json.loads(rows)
            if rows and isinstance(rows[0], dict):
                response_name = str(
                    rows[0].get("Index Name") or rows[0].get("indexName")
                    or rows[0].get("INDEX_NAME") or response_name
                )
            raw_chunks.append({
                "start_date": cursor.isoformat(),
                "end_date": chunk_end.isoformat(),
                "response": raw_payload,
            })
            cursor = chunk_end + timedelta(days=1)

        if not points_by_date:
            raise ValueError(
                f"No TRI observations returned for {name} between {start_date} and {end_date}. "
                "Check the canonical index name and published history coverage."
            )
        return BenchmarkResponse(
            benchmark_code=name,
            benchmark_name=response_name,
            data=sorted(points_by_date.values(), key=lambda item: item.date),
            raw_payload={
                "provider": self.source,
                "endpoint": f"{self.base_url}{self.endpoint}",
                "request": {
                    "benchmark_code": name,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "chunk_days": self.chunk_days,
                    "chunk_count": len(raw_chunks),
                },
                "chunks": raw_chunks,
            },
        )
