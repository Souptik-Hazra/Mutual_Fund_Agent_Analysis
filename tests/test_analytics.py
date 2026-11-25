"""Tests for deterministic financial analytics."""

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from mutual_fund_agent_analysis.analytics import (
    PricePoint,
    ReturnPoint,
    absolute_return,
    align_returns,
    analyze_fund,
    cagr,
    calculate_benchmark_metrics,
    calculate_drawdown,
    calculate_risk_metrics,
    calendar_year_returns,
    load_fund_prices,
    period_returns,
    rolling_returns,
    trailing_return,
)

def prices(*items: tuple[str, str]) -> list[PricePoint]:
    return [PricePoint(date.fromisoformat(day), Decimal(value)) for day, value in items]

def returns(*items: tuple[str, str]) -> list[ReturnPoint]:
    return [
        ReturnPoint(
            date.fromisoformat(day),
            Decimal(value),
            date.fromisoformat(day) - timedelta(days=1),
        )
        for day, value in items
    ]

def test_absolute_return_and_cagr() -> None:
    observations = prices(("2020-01-01", "100"), ("2021-01-01", "110"))
    assert absolute_return(observations) == Decimal("0.1")
    assert cagr(observations) == pytest.approx(Decimal("0.0997"), abs=Decimal("0.001"))

def test_period_returns_sort_observations_and_preserve_actual_dates() -> None:
    result = period_returns(prices(("2024-01-03", "121"), ("2024-01-01", "100")))
    assert [(point.date.isoformat(), point.value, point.start_date) for point in result] == [
        ("2024-01-03", Decimal("0.21"), date(2024, 1, 1))
    ]

def test_rolling_returns_and_calendar_year_returns() -> None:
    observations = prices(
        ("2022-01-03", "100"),
        ("2022-12-30", "110"),
        ("2023-12-29", "121"),
        ("2024-12-31", "133.1"),
    )
    rolling = rolling_returns(observations, windows_years=(1,))
    assert rolling
    assert rolling[-1].value == Decimal("0.1")
    calendar = calendar_year_returns(observations)
    assert calendar[2023] == Decimal("0.1")
    assert calendar[2024] == Decimal("0.1")

def test_trailing_return_requires_sufficient_history() -> None:
    observations = prices(("2023-01-01", "100"), ("2024-01-02", "120"))
    assert trailing_return(observations, 1) == Decimal("0.2")
    with pytest.raises(ValueError, match="Insufficient history"):
        trailing_return(observations, 3)

def test_duplicate_and_non_positive_prices_are_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        absolute_return(prices(("2024-01-01", "10"), ("2024-01-01", "11")))
    with pytest.raises(ValueError, match="greater than zero"):
        absolute_return(prices(("2024-01-01", "0")))

def test_risk_metrics_use_sample_volatility_and_explicit_frequency() -> None:
    result = calculate_risk_metrics(
        returns(("2024-01-02", "0.01"), ("2024-01-03", "-0.01")),
        annual_risk_free_rate=Decimal("0"),
        periods_per_year=2,
    )
    assert result.observation_count == 2
    assert result.annualized_volatility is not None
    assert result.sharpe_ratio == pytest.approx(Decimal("0"))
    assert result.sortino_ratio is not None

def test_zero_volatility_has_undefined_sharpe() -> None:
    result = calculate_risk_metrics(returns(("2024-01-02", "0.01"), ("2024-01-03", "0.01")))
    assert result.annualized_volatility == 0
    assert result.sharpe_ratio is None

def test_benchmark_metrics_align_exact_dates_and_calculate_beta_alpha() -> None:
    fund = returns(
        ("2024-01-02", "0.02"),
        ("2024-01-03", "0.04"),
        ("2024-01-04", "0.06"),
    )
    benchmark = returns(
        ("2024-01-02", "0.01"),
        ("2024-01-04", "0.03"),
        ("2024-01-05", "0.99"),
    )
    aligned_fund, aligned_benchmark = align_returns(fund, benchmark)
    assert [point.date for point in aligned_fund] == [
        date(2024, 1, 2),
        date(2024, 1, 4),
    ]
    metrics = calculate_benchmark_metrics(fund, benchmark, periods_per_year=1)
    assert metrics.observation_count == 2
    assert metrics.beta == Decimal("2")
    assert metrics.annualized_alpha == Decimal("0")

def test_insufficient_benchmark_history_returns_undefined_metrics() -> None:
    metrics = calculate_benchmark_metrics(
        returns(("2024-01-02", "0.02")),
        returns(("2024-01-02", "0.01")),
    )
    assert metrics.beta is None
    assert metrics.annualized_alpha is None

def test_drawdown_reports_peak_trough_and_recovery() -> None:
    result = calculate_drawdown(
        prices(
            ("2024-01-01", "100"),
            ("2024-01-10", "120"),
            ("2024-01-20", "90"),
            ("2024-02-01", "125"),
        )
    )
    assert result.maximum_drawdown == Decimal("-0.25")
    assert result.peak_date == date(2024, 1, 10)
    assert result.trough_date == date(2024, 1, 20)
    assert result.recovery_date == date(2024, 2, 1)
    assert result.drawdown_duration_days == 10
    assert result.recovery_duration_days == 12

def test_benchmark_alignment_requires_identical_observation_intervals() -> None:
    fund = [
        ReturnPoint(date(2024, 1, 3), Decimal("0.02"), date(2024, 1, 1)),
    ]
    benchmark = [
        ReturnPoint(date(2024, 1, 3), Decimal("0.01"), date(2024, 1, 2)),
    ]
    aligned_fund, aligned_benchmark = align_returns(fund, benchmark)
    assert aligned_fund == []
    assert aligned_benchmark == []

def test_database_loader_rejects_nav_reconciliation_conflicts_by_default() -> None:
    session = Mock()
    session.scalars.return_value.all.return_value = [
        SimpleNamespace(
            nav_date=date(2024, 1, 1),
            canonical_nav=Decimal("100"),
            status="matched",
        ),
        SimpleNamespace(
            nav_date=date(2024, 1, 2),
            canonical_nav=Decimal("101"),
            status="conflict",
        ),
    ]
    with pytest.raises(ValueError, match="reconciliation conflict"):
        load_fund_prices(session, 12345)

def test_database_loader_can_explicitly_include_and_report_nav_conflicts() -> None:
    session = Mock()
    conflict_date = date(2024, 1, 2)
    session.scalars.return_value.all.return_value = [
        SimpleNamespace(
            nav_date=date(2024, 1, 1),
            canonical_nav=Decimal("100"),
            status="matched",
        ),
        SimpleNamespace(
            nav_date=conflict_date,
            canonical_nav=Decimal("101"),
            status="conflict",
        ),
    ]
    prices, conflicts = load_fund_prices(session, 12345, allow_nav_conflicts=True)
    assert [point.value for point in prices] == [Decimal("100"), Decimal("101")]
    assert conflicts == (conflict_date,)

def test_one_year_rolling_window_uses_calendar_anniversary() -> None:
    observations = prices(
        ("2023-02-28", "100"),
        ("2023-03-01", "200"),
        ("2024-02-29", "110"),
    )
    result = rolling_returns(observations, windows_years=(1,))
    latest = next(item for item in result if item.end_date == date(2024, 2, 29))
    assert latest.start_date == date(2023, 2, 28)
    assert latest.value == Decimal("0.1")

def test_return_alignment_rejects_missing_or_invalid_intervals() -> None:
    invalid = ReturnPoint(date(2024, 1, 2), Decimal("0.01"), date(2024, 1, 2))
    with pytest.raises(ValueError, match="start_date earlier than date"):
        align_returns([invalid], [])

def test_return_alignment_rejects_duplicate_intervals() -> None:
    duplicate = ReturnPoint(date(2024, 1, 2), Decimal("0.01"), date(2024, 1, 1))
    with pytest.raises(ValueError, match="Duplicate return observation intervals"):
        align_returns([duplicate, duplicate], [duplicate])

def test_drawdown_recovery_duration_is_measured_from_trough() -> None:
    result = calculate_drawdown(
        prices(
            ("2024-01-01", "100"),
            ("2024-01-10", "120"),
            ("2024-01-20", "90"),
            ("2024-02-01", "125"),
        )
    )
    assert result.recovery_duration_days == 12

def test_price_inputs_require_decimal_values() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        absolute_return([PricePoint(date(2024, 1, 1), 100)])  # type: ignore[arg-type]

def test_risk_frequency_must_be_a_positive_integer() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        calculate_risk_metrics(
            returns(("2024-01-02", "0.01"), ("2024-01-03", "0.02")),
            periods_per_year=12.5,  # type: ignore[arg-type]
        )

def test_risk_metrics_require_two_observations_for_ratios() -> None:
    result = calculate_risk_metrics(returns(("2024-01-02", "0.01")))
    assert result.observation_count == 1
    assert result.annualized_volatility is None
    assert result.annualized_downside_deviation is None
    assert result.sharpe_ratio is None
    assert result.sortino_ratio is None

def test_drawdown_recovery_is_none_when_series_never_declines() -> None:
    result = calculate_drawdown(
        prices(("2024-01-01", "100"), ("2024-01-02", "110"), ("2024-01-03", "120"))
    )
    assert result.maximum_drawdown == Decimal("0")
    assert result.recovery_date is None
    assert result.recovery_duration_days is None

def test_absolute_return_requires_two_observations() -> None:
    with pytest.raises(ValueError, match="at least two"):
        absolute_return(prices(("2024-01-01", "100")))

def test_calendar_year_returns_exclude_incomplete_latest_year() -> None:
    result = calendar_year_returns(
        prices(
            ("2023-01-02", "100"),
            ("2023-12-29", "110"),
            ("2024-12-30", "121"),
            ("2025-06-30", "130"),
        )
    )
    assert result == {2024: Decimal("0.1")}

def test_rolling_windows_reject_duplicates() -> None:
    with pytest.raises(ValueError, match="must not contain duplicates"):
        rolling_returns(prices(("2023-01-01", "100"), ("2024-01-01", "110")), (1, 1))

def test_return_alignment_rejects_overlapping_intervals() -> None:
    overlapping = [
        ReturnPoint(date(2024, 1, 3), Decimal("0.02"), date(2024, 1, 1)),
        ReturnPoint(date(2024, 1, 4), Decimal("0.03"), date(2024, 1, 2)),
    ]
    with pytest.raises(ValueError, match="must not overlap"):
        align_returns(overlapping, overlapping)

def test_constant_benchmark_keeps_return_metrics_but_not_beta_or_alpha() -> None:
    fund = returns(("2024-01-02", "0.02"), ("2024-01-03", "0.04"))
    benchmark = returns(("2024-01-02", "0.01"), ("2024-01-03", "0.01"))
    result = calculate_benchmark_metrics(fund, benchmark, periods_per_year=12)
    assert result.beta is None
    assert result.annualized_alpha is None
    assert result.annualized_fund_return == Decimal("0.36")
    assert result.annualized_benchmark_return == Decimal("0.12")
    assert result.mean_period_excess_return == Decimal("0.02")

def test_database_service_builds_report_from_reconciled_navs() -> None:
    session = Mock()
    nav_rows = [
        SimpleNamespace(
            nav_date=date(2024, 1, 1),
            canonical_nav=Decimal("100"),
            status="matched",
        ),
        SimpleNamespace(
            nav_date=date(2024, 1, 2),
            canonical_nav=Decimal("110"),
            status="matched",
        ),
        SimpleNamespace(
            nav_date=date(2024, 1, 3),
            canonical_nav=Decimal("121"),
            status="matched",
        ),
    ]
    session.scalars.return_value.all.return_value = nav_rows

    report = analyze_fund(session, 12345)

    assert report.scheme_code == 12345
    assert report.observation_count == 3
    assert report.absolute_return == Decimal("0.21")
    assert report.nav_conflict_dates == ()
    assert report.benchmark is None
    assert report.risk.observation_count == 2
