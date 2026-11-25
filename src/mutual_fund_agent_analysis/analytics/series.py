"""Validated price and return time-series primitives."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PricePoint:
    date: date
    value: Decimal


@dataclass(frozen=True, slots=True)
class ReturnPoint:
    date: date
    value: Decimal
    start_date: date | None = None


def normalize_prices(points: Iterable[PricePoint]) -> list[PricePoint]:
    """Validate prices and return them in chronological order."""
    result = list(points)
    if not result:
        raise ValueError("At least one price observation is required.")
    if any(not point.value.is_finite() or point.value <= 0 for point in result):
        raise ValueError("Price observations must be finite and greater than zero.")
    dates = [point.date for point in result]
    if len(dates) != len(set(dates)):
        raise ValueError("Duplicate observation dates are not allowed.")
    return sorted(result, key=lambda point: point.date)


def period_returns(points: Iterable[PricePoint]) -> list[ReturnPoint]:
    """Calculate close-to-close returns between consecutive observed dates."""
    prices = normalize_prices(points)
    return [
        ReturnPoint(
            current.date,
            current.value / previous.value - Decimal("1"),
            previous.date,
        )
        for previous, current in zip(prices, prices[1:], strict=False)
    ]
