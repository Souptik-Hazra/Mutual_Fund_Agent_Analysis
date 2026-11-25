"""Validated price and return time-series primitives."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

FREQUENCY_PERIODS_PER_YEAR = {
    "daily": 252,
    "weekly": 52,
    "monthly": 12,
    "quarterly": 4,
    "yearly": 1,
}


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
    if any(type(point.date) is not date for point in result):
        raise ValueError("Price observation dates must be datetime.date values.")
    if any(not isinstance(point.value, Decimal) for point in result):
        raise TypeError("Price observations must use Decimal values.")
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
        if type(point.date) is not date or type(point.start_date) is not date:
            raise ValueError("Return observation dates must be datetime.date values.")
        if point.start_date >= point.date:
            raise ValueError("Return observations require start_date earlier than date.")
        if not isinstance(point.value, Decimal):
            raise TypeError("Return observations must use Decimal values.")
        if not point.value.is_finite() or point.value <= Decimal("-1"):
            raise ValueError("Returns must be finite and greater than -100%.")
    intervals = [(point.start_date, point.date) for point in result]
    if len(intervals) != len(set(intervals)):
        raise ValueError("Duplicate return observation intervals are not allowed.")
    ordered = sorted(result, key=lambda point: (point.start_date, point.date))
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current.start_date < previous.date:
            raise ValueError("Return observation intervals must not overlap.")
    return ordered


def resample_prices(
    points: Iterable[PricePoint],
    frequency: str = "daily",
) -> list[PricePoint]:
    """Select the last actual observation in each calendar period, preserving the start.

    No missing NAV is filled or interpolated. The first source observation is
    retained as the base point; subsequent observations are the last available
    NAV in each daily, ISO-weekly, monthly, quarterly or yearly bucket.
    """
    if frequency not in FREQUENCY_PERIODS_PER_YEAR:
        raise ValueError("frequency must be daily, weekly, monthly, quarterly or yearly.")
    prices = normalize_prices(points)
    if frequency == "daily":
        return prices

    def bucket(point: PricePoint) -> tuple[int, ...]:
        day = point.date
        if frequency == "weekly":
            iso = day.isocalendar()
            return (iso.year, iso.week)
        if frequency == "monthly":
            return (day.year, day.month)
        if frequency == "quarterly":
            return (day.year, (day.month - 1) // 3 + 1)
        return (day.year,)

    period_ends: dict[tuple[int, ...], PricePoint] = {}
    for point in prices:
        period_ends[bucket(point)] = point

    sampled = [prices[0]]
    for point in period_ends.values():
        if point.date > sampled[-1].date:
            sampled.append(point)
    return sampled
