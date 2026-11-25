"""Provider-neutral contracts shared by NAV data adapters."""

from datetime import date
from decimal import Decimal
from typing import Any, Protocol


class NavMetadata(Protocol):
    scheme_code: int
    scheme_name: str
    fund_house: str | None
    scheme_type: str | None
    scheme_category: str | None
    isin_growth: str | None
    isin_div_reinvestment: str | None


class NavPoint(Protocol):
    date: date
    nav: Decimal


class NavResponse(Protocol):
    meta: NavMetadata
    data: list[NavPoint]
    raw_payload: dict[str, Any] | None


class NavProvider(Protocol):
    """Common interface implemented by every NAV provider."""

    source: str

    def get_nav_history(
        self,
        scheme_code: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> NavResponse: ...

    def close(self) -> None: ...
