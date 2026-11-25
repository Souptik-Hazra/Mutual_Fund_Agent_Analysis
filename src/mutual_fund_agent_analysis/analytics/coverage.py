"""Observation-frequency checks and coverage diagnostics."""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from mutual_fund_agent_analysis.analytics.series import ReturnPoint, normalize_returns


@dataclass(frozen=True, slots=True)
class ReturnCoverage:
    observation_count: int
    median_interval_days: Decimal | None
    maximum_interval_days: int | None
    long_gap_count: int
    estimated_coverage_ratio: Decimal | None
    inferred_frequency: str


_FREQUENCY_BY_PERIODS = {
    252: ("daily", 1, 7),
    52: ("weekly", 5, 14),
    12: ("monthly", 15, 50),
    4: ("quarterly", 46, 150),
    1: ("yearly", 151, 550),
}


def assess_return_coverage(
    returns: Iterable[ReturnPoint],
    periods_per_year: int,
) -> ReturnCoverage:
    """Summarize calendar spacing and flag long gaps without filling observations."""
    points = normalize_returns(returns)
    if isinstance(periods_per_year, bool) or not isinstance(periods_per_year, int) or periods_per_year <= 0:
        raise ValueError("periods_per_year must be a positive integer.")
    if len(points) < 2:
        return ReturnCoverage(len(points), None, None, 0, None, "insufficient")
    gaps = [(right.date - left.date).days for left, right in zip(points, points[1:], strict=False)]
    ordered = sorted(gaps)
    middle = len(ordered) // 2
    median = (
        Decimal(ordered[middle])
        if len(ordered) % 2
        else Decimal(ordered[middle - 1] + ordered[middle]) / Decimal("2")
    )
    expected = Decimal("365.25") / Decimal(periods_per_year)
    threshold = max(4, int(expected * Decimal("1.75")))
    long_gaps = sum(gap > threshold for gap in gaps)
    span_days = (points[-1].date - points[0].start_date).days
    expected_count = Decimal(span_days) * Decimal(periods_per_year) / Decimal("365.25")
    coverage = min(Decimal("1"), Decimal(len(points)) / expected_count) if expected_count else None
    inferred = "irregular"
    for name, minimum, maximum in (
        ("daily", 1, 7),
        ("weekly", 5, 14),
        ("monthly", 15, 50),
        ("quarterly", 46, 150),
        ("yearly", 151, 550),
    ):
        if minimum <= median <= maximum:
            inferred = name
            break
    return ReturnCoverage(
        observation_count=len(points),
        median_interval_days=median,
        maximum_interval_days=max(gaps),
        long_gap_count=long_gaps,
        estimated_coverage_ratio=coverage,
        inferred_frequency=inferred,
    )


def validate_observation_frequency(
    returns: Iterable[ReturnPoint],
    periods_per_year: int,
) -> ReturnCoverage:
    """Reject clear daily/monthly/etc. annualization mismatches; return diagnostics."""
    points = normalize_returns(returns)
    coverage = assess_return_coverage(points, periods_per_year)
    expected = _FREQUENCY_BY_PERIODS.get(periods_per_year)
    if expected is not None and coverage.median_interval_days is not None:
        expected_name, minimum, maximum = expected
        if not minimum <= coverage.median_interval_days <= maximum:
            raise ValueError(
                f"periods_per_year={periods_per_year} implies {expected_name} observations, "
                f"but median spacing is {coverage.median_interval_days} days "
                f"({coverage.inferred_frequency})."
            )
    return coverage
