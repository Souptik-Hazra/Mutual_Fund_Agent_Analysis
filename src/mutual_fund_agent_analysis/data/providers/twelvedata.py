"""Twelve Data adapter for explicitly licensed personal NSE/BSE market access."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx


@dataclass(frozen=True)
class EquityQuote:
    symbol: str
    exchange: str
    observed_at: datetime
    price: Decimal
    change_pct: Decimal | None
    day_high: Decimal | None
    day_low: Decimal | None
    volume: int | None
    market_status: str
    source_url: str


class TwelveDataClient:
    source = "twelvedata"
    base_url = "https://api.twelvedata.com"

    def __init__(
        self, api_key: str, timeout: float = 12.0, client: httpx.Client | None = None
    ):
        if not api_key.strip():
            raise ValueError("Twelve Data API key cannot be blank.")
        self._api_key = api_key.strip()
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout, connect=5.0))

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def _decimal(payload: dict[str, Any], *keys: str) -> Decimal | None:
        for key in keys:
            value = payload.get(key)
            if value in (None, "", "null"):
                continue
            try:
                parsed = Decimal(str(value))
            except InvalidOperation as exc:
                raise ValueError(f"Provider returned invalid numeric field: {key}.") from exc
            if not parsed.is_finite():
                raise ValueError(f"Provider returned non-finite numeric field: {key}.")
            return parsed
        return None

    @staticmethod
    def _timestamp(payload: dict[str, Any]) -> datetime:
        raw = payload.get("timestamp") or payload.get("datetime")
        if raw is None:
            raise ValueError("Provider quote omitted its observation timestamp.")
        if isinstance(raw, (int, float)) or str(raw).isdigit():
            value = datetime.fromtimestamp(float(raw), tz=UTC)
        else:
            value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if value.tzinfo is None:
                raise ValueError("Provider timestamp is missing timezone information.")
            value = value.astimezone(UTC)
        if value > datetime.now(UTC):
            raise ValueError("Provider returned a future observation timestamp.")
        return value

    def _get(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = self._client.get(
                f"{self.base_url}/{endpoint}",
                params={**params, "apikey": self._api_key},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            # HTTPX exceptions can include the full request URL, including the API key.
            raise ValueError("Twelve Data request failed; provider details were withheld.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Twelve Data returned a non-object response.")
        if payload.get("status") == "error" or payload.get("code"):
            raise ValueError("Twelve Data rejected the quote request.")
        return payload

    def get_quote(self, symbol: str, exchange: str) -> EquityQuote:
        ticker, venue = symbol.strip().upper(), exchange.strip().upper()
        if not ticker or not venue or len(ticker) > 40 or len(venue) > 12:
            raise ValueError("A valid symbol and explicit exchange are required.")
        payload = self._get("quote", {"symbol": ticker, "exchange": venue})
        returned_symbol = payload.get("symbol")
        returned_exchange = payload.get("exchange")
        if not isinstance(returned_symbol, str) or not returned_symbol.strip():
            raise ValueError(
                "Provider quote omitted the returned symbol; identity cannot be verified."
            )
        if not isinstance(returned_exchange, str) or not returned_exchange.strip():
            raise ValueError(
                "Provider quote omitted the returned exchange; identity cannot be verified."
            )
        if returned_symbol.strip().upper() != ticker:
            raise ValueError("Provider returned a different symbol; quote rejected.")
        if returned_exchange.strip().upper() != venue:
            raise ValueError("Provider returned a different exchange; quote rejected.")
        price = self._decimal(payload, "close", "price")
        if price is None or price <= 0:
            raise ValueError("Provider quote has no positive last price.")
        state = payload.get("is_market_open")
        return EquityQuote(
            symbol=returned_symbol.strip().upper(),
            exchange=returned_exchange.strip().upper(),
            observed_at=self._timestamp(payload),
            price=price,
            change_pct=self._decimal(payload, "percent_change"),
            day_high=self._decimal(payload, "high"),
            day_low=self._decimal(payload, "low"),
            volume=int(payload["volume"]) if payload.get("volume") not in (None, "") else None,
            market_status="trading" if state is True else "closed" if state is False else "unknown",
            source_url=f"{self.base_url}/quote",
        )
