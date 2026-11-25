"""NSE Indices historical TRI/NTR adapter.

The public historical-data page exposes an ASP.NET endpoint that is not a
versioned public API. Keep this adapter isolated and fail loudly on schema drift.
"""

import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
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
    ) -> None:
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
                raw_date = row.get("Date") or row.get("date")
                observation_date = datetime.strptime(raw_date.strip(), "%d %b %Y").date()
                tri_value = row.get("TotalReturnsIndex", row.get("totalReturnsIndex"))
                ntr_value = row.get("NTR_Value", row.get("NTRValue"))
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

    def get_history(
        self,
        benchmark_code: str,
        start_date: date,
        end_date: date,
    ) -> BenchmarkResponse:
        """Fetch TRI/NTR history for a canonical Nifty index name."""
        name = benchmark_code.strip()
        if not name or len(name) > 160 or "'" in name:
            raise ValueError("benchmark_code must be a valid canonical Nifty index name.")
        if start_date > end_date:
            raise ValueError("start_date cannot be later than end_date.")

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
        response = self._client.post(self.endpoint, content=json.dumps({"cinfo": cinfo}))
        response.raise_for_status()
        raw_payload = response.json()
        points = self._parse_rows(raw_payload, name)
        for point in points:
            if not start_date <= point.date <= end_date:
                raise ValueError("Nifty Indices returned an observation outside the requested range.")
        if not points:
            raise ValueError(
                f"No TRI observations returned for {name} between {start_date} and {end_date}. "
                "Check the canonical index name and published history coverage."
            )
        response_name = name
        rows = raw_payload.get("d")
        if isinstance(rows, str):
            rows = json.loads(rows)
        if rows and isinstance(rows[0], dict):
            response_name = str(rows[0].get("Index Name") or name)
        return BenchmarkResponse(
            benchmark_code=name,
            benchmark_name=response_name,
            data=points,
            raw_payload={
                "provider": self.source,
                "endpoint": f"{self.base_url}{self.endpoint}",
                "request": {
                    "benchmark_code": name,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
                "response": raw_payload,
            },
        )
