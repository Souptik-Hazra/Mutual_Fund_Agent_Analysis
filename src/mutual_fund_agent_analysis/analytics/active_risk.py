"""Benchmark-relative tracking error and information ratio."""
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from mutual_fund_agent_analysis.analytics.benchmark import align_returns
from mutual_fund_agent_analysis.analytics.risk import _mean
from mutual_fund_agent_analysis.analytics.series import ReturnPoint, normalize_returns


@dataclass(frozen=True, slots=True)
class ActiveRiskMetrics:
    aligned_observation_count: int
    tracking_error: Decimal | None
    information_ratio: Decimal | None
    mean_active_return: Decimal | None
    coverage_ratio: Decimal


def calculate_active_risk_metrics(
    fund_returns: Iterable[ReturnPoint],
    benchmark_returns: Iterable[ReturnPoint],
    periods_per_year: int,
) -> ActiveRiskMetrics:
    """Use exact return intervals; tracking error is sample deviation annualized by sqrt(n)."""
    if isinstance(periods_per_year, bool) or not isinstance(periods_per_year, int) or periods_per_year < 1:
        raise ValueError("periods_per_year must be a positive integer.")
    fund, benchmark = normalize_returns(fund_returns), normalize_returns(benchmark_returns)
    aligned_fund, aligned_benchmark = align_returns(fund, benchmark)
    count = len(aligned_fund)
    denominator = max(len(fund), len(benchmark))
    coverage = Decimal(count) / Decimal(denominator) if denominator else Decimal("0")
    if count < 2:
        return ActiveRiskMetrics(count, None, None, None, coverage)
    active = [f.value - b.value for f, b in zip(aligned_fund, aligned_benchmark, strict=True)]
    if any(not value.is_finite() for value in active):
        raise ValueError("Active returns must be finite.")
    mean_active = _mean(active)
    variance = sum(((value - mean_active) ** 2 for value in active), Decimal("0")) / Decimal(count - 1)
    periodic_te = variance.sqrt()
    annualization = Decimal(periods_per_year).sqrt()
    tracking_error = periodic_te * annualization
    information_ratio = mean_active / periodic_te * annualization if periodic_te else None
    return ActiveRiskMetrics(count, tracking_error, information_ratio, mean_active, coverage)
