"""Exact-date benchmark alignment, beta, alpha, and excess returns."""

from dataclasses import dataclass
from decimal import Decimal
from collections.abc import Iterable

from mutual_fund_agent_analysis.analytics.risk import DEFAULT_PERIODS_PER_YEAR, _mean
from mutual_fund_agent_analysis.analytics.series import ReturnPoint


@dataclass(frozen=True, slots=True)
class BenchmarkMetrics:
    observation_count: int
    beta: Decimal | None
    annualized_alpha: Decimal | None
    annualized_fund_return: Decimal | None
    annualized_benchmark_return: Decimal | None
    mean_period_excess_return: Decimal | None


def align_returns(
    fund_returns: Iterable[ReturnPoint], benchmark_returns: Iterable[ReturnPoint]
) -> tuple[list[ReturnPoint], list[ReturnPoint]]:
    """Inner-join identical return intervals; never forward-fill or mix horizons."""
    fund = {(point.start_date, point.date): point for point in fund_returns}
    benchmark = {(point.start_date, point.date): point for point in benchmark_returns}
    intervals = sorted(fund.keys() & benchmark.keys())
    return [fund[key] for key in intervals], [benchmark[key] for key in intervals]


def calculate_benchmark_metrics(
    fund_returns: Iterable[ReturnPoint],
    benchmark_returns: Iterable[ReturnPoint],
    annual_risk_free_rate: Decimal = Decimal("0"),
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> BenchmarkMetrics:
    """Calculate beta and arithmetic annualized Jensen alpha on aligned returns."""
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive.")
    if not annual_risk_free_rate.is_finite() or annual_risk_free_rate <= Decimal("-1"):
        raise ValueError("annual_risk_free_rate must be finite and greater than -1.")
    fund, benchmark = align_returns(fund_returns, benchmark_returns)
    count = len(fund)
    if count < 2:
        return BenchmarkMetrics(count, None, None, None, None, None)

    f_values = [point.value for point in fund]
    b_values = [point.value for point in benchmark]
    if any(not value.is_finite() or value <= Decimal("-1") for value in f_values + b_values):
        raise ValueError("Returns must be finite and greater than -100%.")
    f_mean, b_mean = _mean(f_values), _mean(b_values)
    b_variance = sum(((value - b_mean) ** 2 for value in b_values), Decimal("0"))
    if b_variance == 0:
        return BenchmarkMetrics(count, None, None, None, None, None)

    covariance = sum(
        (
            (f_value - f_mean) * (b_value - b_mean)
            for f_value, b_value in zip(f_values, b_values, strict=True)
        ),
        Decimal("0"),
    )
    beta = covariance / b_variance
    periodic_rf = annual_risk_free_rate / Decimal(periods_per_year)
    alpha = (
        (f_mean - periodic_rf) - beta * (b_mean - periodic_rf)
    ) * Decimal(periods_per_year)
    return BenchmarkMetrics(
        count,
        beta,
        alpha,
        f_mean * Decimal(periods_per_year),
        b_mean * Decimal(periods_per_year),
        f_mean - b_mean,
    )
