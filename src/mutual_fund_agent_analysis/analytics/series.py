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
    start_date: date


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


def normalize_returns(points: Iterable[ReturnPoint]) -> list[ReturnPoint]:
    """Validate and sort returns with explicit, unique observation intervals."""
    result = list(points)
    for point in result:
        if point.start_date is None or point.start_date >= point.date:
            raise ValueError("Return observations require start_date earlier than date.")
        if not point.value.is_finite() or point.value <= Decimal("-1"):
            raise ValueError("Returns must be finite and greater than -100%.")
    intervals = [(point.start_date, point.date) for point in result]
    if len(intervals) != len(set(intervals)):
        raise ValueError("Duplicate return observation intervals are not allowed.")
    return sorted(result, key=lambda point: (point.start_date, point.date))
