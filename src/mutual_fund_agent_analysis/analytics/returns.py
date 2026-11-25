"""Point-to-point, annualized, rolling, and calendar-year returns."""

from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from mutual_fund_agent_analysis.analytics.series import PricePoint, normalize_prices

DAYS_PER_YEAR = Decimal("365.25")


def _subtract_years(value: date, years: int) -> date:
    """Subtract calendar years, mapping leap day to February 28 when needed."""
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, month=2, day=28)


@dataclass(frozen=True, slots=True)
class RollingReturn:
    end_date: date
    start_date: date
    years: int
    value: Decimal


def absolute_return(points: Iterable[PricePoint]) -> Decimal:
    """Return total point-to-point price appreciation, excluding distributions."""
    prices = normalize_prices(points)
    return prices[-1].value / prices[0].value - Decimal("1")


def cagr(points: Iterable[PricePoint]) -> Decimal:
    """Calculate date-aware CAGR using 365.25 days per year."""
    prices = normalize_prices(points)
    days = (prices[-1].date - prices[0].date).days
    if days <= 0:
        raise ValueError("CAGR requires observations on at least two distinct dates.")
    exponent = DAYS_PER_YEAR / Decimal(days)
    return (prices[-1].value / prices[0].value) ** exponent - Decimal("1")


def trailing_return(points: Iterable[PricePoint], years: int) -> Decimal:
    """Calculate return to the latest date from the closest available prior observation."""
    if isinstance(years, bool) or not isinstance(years, int) or years <= 0:
        raise ValueError("years must be a positive integer.")
    prices = normalize_prices(points)
    target = _subtract_years(prices[-1].date, years)
    eligible = [point for point in prices if point.date <= target]
    if not eligible:
        raise ValueError(f"Insufficient history for a {years}-year trailing return.")
    start = eligible[-1]
    return prices[-1].value / start.value - Decimal("1")


def rolling_returns(
    points: Iterable[PricePoint], windows_years: tuple[int, ...] = (1, 3, 5)
) -> list[RollingReturn]:
    """Calculate rolling point-to-point returns using the last observation on/before each anchor."""
    prices = normalize_prices(points)
    if any(
        isinstance(year, bool) or not isinstance(year, int) or year <= 0
        for year in windows_years
    ):
        raise ValueError("Rolling windows must be positive integers.")
    dates = [point.date for point in prices]
    results: list[RollingReturn] = []
    for years in windows_years:
        for end_index, end in enumerate(prices):
            anchor = _subtract_years(end.date, years)
            start_index = bisect_right(dates, anchor, 0, end_index + 1) - 1
            if start_index < 0:
                continue
            start = prices[start_index]
            results.append(
                RollingReturn(
                    end_date=end.date,
                    start_date=start.date,
                    years=years,
                    value=end.value / start.value - Decimal("1"),
                )
            )
    return sorted(results, key=lambda item: (item.end_date, item.years))


def calendar_year_returns(points: Iterable[PricePoint]) -> dict[int, Decimal]:
    """Calculate calendar-year returns from the last available NAV in adjacent years."""
    prices = normalize_prices(points)
    year_ends: dict[int, PricePoint] = {}
    for point in prices:
        year_ends[point.date.year] = point
    results: dict[int, Decimal] = {}
    for year in sorted(year_ends):
        previous = year_ends.get(year - 1)
        current = year_ends[year]
        if previous is not None:
            results[year] = current.value / previous.value - Decimal("1")
    return results
