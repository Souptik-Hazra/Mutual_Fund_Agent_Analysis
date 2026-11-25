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
    target_year = value.year - years
    if target_year < 1:
        return date.min
    try:
        return value.replace(year=target_year)
    except ValueError:
        return value.replace(year=target_year, month=2, day=28)


@dataclass(frozen=True, slots=True)
class RollingReturn:
    end_date: date
    start_date: date
    years: int
    value: Decimal


@dataclass(frozen=True, slots=True)
class TrailingReturn:
    target_start_date: date
    actual_start_date: date
    end_date: date
    staleness_days: int
    value: Decimal


def absolute_return(points: Iterable[PricePoint]) -> Decimal:
    """Return total point-to-point price appreciation, excluding distributions."""
    prices = normalize_prices(points)
    if len(prices) < 2:
        raise ValueError("Absolute return requires at least two distinct observations.")
    return prices[-1].value / prices[0].value - Decimal("1")


def cagr(points: Iterable[PricePoint]) -> Decimal:
    """Calculate date-aware CAGR using 365.25 days per year."""
    prices = normalize_prices(points)
    days = (prices[-1].date - prices[0].date).days
    if days <= 0:
        raise ValueError("CAGR requires observations on at least two distinct dates.")
    exponent = DAYS_PER_YEAR / Decimal(days)
    return (prices[-1].value / prices[0].value) ** exponent - Decimal("1")


def trailing_return_details(
    points: Iterable[PricePoint],
    years: int,
    max_staleness_days: int | None = None,
) -> TrailingReturn:
    """Return a trailing result together with its actual anchor and staleness."""
    if isinstance(years, bool) or not isinstance(years, int) or years <= 0:
        raise ValueError("years must be a positive integer.")
    if max_staleness_days is not None and (
        isinstance(max_staleness_days, bool)
        or not isinstance(max_staleness_days, int)
        or max_staleness_days < 0
    ):
        raise ValueError("max_staleness_days must be a non-negative integer.")
    prices = normalize_prices(points)
    target = _subtract_years(prices[-1].date, years)
    eligible = [point for point in prices if point.date <= target]
    if not eligible:
        raise ValueError(f"Insufficient history for a {years}-year trailing return.")
    start = eligible[-1]
    staleness = (target - start.date).days
    if max_staleness_days is not None and staleness > max_staleness_days:
        raise ValueError(
            f"Trailing-return anchor is stale by {staleness} days "
            f"(maximum {max_staleness_days})."
        )
    return TrailingReturn(
        target_start_date=target,
        actual_start_date=start.date,
        end_date=prices[-1].date,
        staleness_days=staleness,
        value=prices[-1].value / start.value - Decimal("1"),
    )


def trailing_return(
    points: Iterable[PricePoint],
    years: int,
    max_staleness_days: int | None = None,
) -> Decimal:
    """Calculate trailing return; optionally reject an excessively stale anchor."""
    return trailing_return_details(points, years, max_staleness_days).value


def rolling_returns(
    points: Iterable[PricePoint], windows_years: tuple[int, ...] = (1, 3, 5)
) -> list[RollingReturn]:
    """Calculate rolling point-to-point returns using the last observation on/before each anchor."""
    prices = normalize_prices(points)
    if any(
        isinstance(year, bool) or not isinstance(year, int) or year <= 0 for year in windows_years
    ):
        raise ValueError("Rolling windows must be positive integers.")
    if len(windows_years) != len(set(windows_years)):
        raise ValueError("Rolling windows must not contain duplicates.")
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


def calendar_year_returns(
    points: Iterable[PricePoint],
    as_of_date: date | None = None,
) -> dict[int, Decimal]:
    """Calculate completed calendar-year returns from adjacent year-end observations.

    A latest-year observation is considered complete only when it is dated
    December 31 or an explicit as_of_date is after that calendar year. This
    handles exchanges whose final trading session is before December 31.
    """
    prices = normalize_prices(points)
    if as_of_date is not None and type(as_of_date) is not date:
        raise ValueError("as_of_date must be a datetime.date value.")
    if as_of_date is not None and as_of_date < prices[-1].date:
        raise ValueError("as_of_date cannot precede the latest price observation.")
    year_ends: dict[int, PricePoint] = {}
    for point in prices:
        year_ends[point.date.year] = point
    results: dict[int, Decimal] = {}
    latest_year = prices[-1].date.year
    final_date_is_year_end = prices[-1].date == date(latest_year, 12, 31)
    latest_year_is_complete = final_date_is_year_end or (
        as_of_date is not None and as_of_date > date(latest_year, 12, 31)
    )
    for year in sorted(year_ends):
        previous = year_ends.get(year - 1)
        current = year_ends[year]
        year_is_complete = year < latest_year or (
            year == latest_year and latest_year_is_complete
        )
        if previous is not None and year_is_complete:
            results[year] = current.value / previous.value - Decimal("1")
    return results
