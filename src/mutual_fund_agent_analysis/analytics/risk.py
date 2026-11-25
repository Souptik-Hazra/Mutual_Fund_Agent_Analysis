"""Annualized volatility and risk-adjusted return metrics."""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from mutual_fund_agent_analysis.analytics.coverage import (
    ReturnCoverage,
    validate_observation_frequency,
)
from mutual_fund_agent_analysis.analytics.series import ReturnPoint, normalize_returns

DEFAULT_PERIODS_PER_YEAR = 252


@dataclass(frozen=True, slots=True)
class RiskMetrics:
    observation_count: int
    annualized_volatility: Decimal | None
    annualized_downside_deviation: Decimal | None
    sharpe_ratio: Decimal | None
    sortino_ratio: Decimal | None
    coverage: ReturnCoverage


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))


def _sample_std(values: list[Decimal]) -> Decimal | None:
    if len(values) < 2:
        return None
    mean = _mean(values)
    variance = sum(((value - mean) ** 2 for value in values), Decimal("0")) / Decimal(
        len(values) - 1
    )
    return variance.sqrt()


def calculate_risk_metrics(
    returns: Iterable[ReturnPoint],
    annual_risk_free_rate: Decimal = Decimal("0"),
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> RiskMetrics:
    """Calculate sample risk metrics and validate the supplied observation frequency.

    The nominal annual risk-free rate is divided by periods_per_year. Common
    frequencies (252 daily, 52 weekly, 12 monthly, 4 quarterly, 1 yearly) are
    checked against median calendar spacing. Coverage diagnostics expose long
    gaps; they do not synthesize missing observations.
    """
    observations = normalize_returns(returns)
    values = [point.value for point in observations]
    if (
        isinstance(periods_per_year, bool)
        or not isinstance(periods_per_year, int)
        or periods_per_year <= 0
    ):
        raise ValueError("periods_per_year must be a positive integer.")
    if not isinstance(annual_risk_free_rate, Decimal):
        raise TypeError("annual_risk_free_rate must be a Decimal.")
    if not annual_risk_free_rate.is_finite() or annual_risk_free_rate <= Decimal("-1"):
        raise ValueError("annual_risk_free_rate must be finite and greater than -1.")
    if any(not value.is_finite() or value <= Decimal("-1") for value in values):
        raise ValueError("Returns must be finite and greater than -100%.")

    coverage = validate_observation_frequency(observations, periods_per_year)
    if len(values) < 2:
        return RiskMetrics(len(values), None, None, None, None, coverage)

    periodic_rf = annual_risk_free_rate / Decimal(periods_per_year)
    excess = [value - periodic_rf for value in values]
    std = _sample_std(values)
    volatility = std * Decimal(periods_per_year).sqrt() if std is not None else None

    downside_squares = [min(value - periodic_rf, Decimal("0")) ** 2 for value in values]
    downside = (sum(downside_squares, Decimal("0")) / Decimal(len(values))).sqrt() * Decimal(
        periods_per_year
    ).sqrt()
    mean_excess = _mean(excess)
    sharpe = (
        mean_excess * Decimal(periods_per_year) / volatility
        if volatility is not None and volatility != 0
        else None
    )
    sortino = mean_excess * Decimal(periods_per_year) / downside if downside != 0 else None
    return RiskMetrics(len(values), volatility, downside, sharpe, sortino, coverage)
