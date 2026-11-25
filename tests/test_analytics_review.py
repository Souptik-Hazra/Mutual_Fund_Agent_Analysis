"""Regression tests for review hardening in deterministic analytics."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from mutual_fund_agent_analysis.analytics import (
    PricePoint,
    ReturnPoint,
    assess_return_coverage,
    calculate_benchmark_metrics,
    calendar_year_returns,
    trailing_return_details,
)
from mutual_fund_agent_analysis.analytics.risk import calculate_risk_metrics


def _prices(*values: tuple[str, str]) -> list[PricePoint]:
    return [PricePoint(date.fromisoformat(day), Decimal(value)) for day, value in values]


def _returns(*ends: str) -> list[ReturnPoint]:
    return [
        ReturnPoint(
            date.fromisoformat(day),
            Decimal("0.01"),
            date.fromisoformat(day) - timedelta(days=1),
        )
        for day in ends
    ]


def test_calendar_year_uses_final_trading_day_when_as_of_is_after_year_end() -> None:
    navs = _prices(
        ("2023-12-29", "100"),
        ("2024-12-30", "110"),
    )
    assert calendar_year_returns(navs) == {}
    assert calendar_year_returns(navs, date(2025, 1, 2)) == {
        2024: Decimal("0.1")
    }


def test_calendar_year_does_not_treat_december_30_as_complete_without_as_of() -> None:
    navs = _prices(
        ("2023-12-29", "100"),
        ("2024-12-30", "110"),
    )
    assert 2024 not in calendar_year_returns(navs)


def test_trailing_return_exposes_actual_anchor_and_staleness() -> None:
    navs = _prices(
        ("2023-01-02", "100"),
        ("2023-01-10", "105"),
        ("2024-01-10", "110"),
    )
    result = trailing_return_details(navs, 1)
    assert result.target_start_date == date(2023, 1, 10)
    assert result.actual_start_date == date(2023, 1, 10)
    assert result.staleness_days == 0
    assert result.value == Decimal("0.04761904761904761904761905")


def test_trailing_return_can_reject_stale_anchor() -> None:
    navs = _prices(
        ("2022-12-20", "100"),
        ("2024-01-10", "110"),
    )
    with pytest.raises(ValueError, match="anchor is stale"):
        trailing_return_details(navs, 1, max_staleness_days=5)


def test_daily_annualization_rejects_monthly_observations() -> None:
    monthly = [
        ReturnPoint(date(2024, 2, 1), Decimal("0.01"), date(2024, 1, 1)),
        ReturnPoint(date(2024, 3, 1), Decimal("0.02"), date(2024, 2, 1)),
        ReturnPoint(date(2024, 4, 1), Decimal("0.03"), date(2024, 3, 1)),
    ]
    with pytest.raises(ValueError, match="implies daily"):
        calculate_risk_metrics(monthly, periods_per_year=252)


def test_coverage_diagnostics_report_missing_observation_gaps() -> None:
    series = [
        ReturnPoint(date(2024, 1, 2), Decimal("0.01"), date(2024, 1, 1)),
        ReturnPoint(date(2024, 1, 3), Decimal("0.01"), date(2024, 1, 2)),
        ReturnPoint(date(2024, 1, 10), Decimal("0.01"), date(2024, 1, 9)),
    ]
    result = assess_return_coverage(series, 252)
    assert result.observation_count == 3
    assert result.maximum_interval_days == 7
    assert result.long_gap_count == 1
    assert result.inferred_frequency == "daily"


def test_benchmark_metrics_report_partial_alignment_coverage() -> None:
    fund = [
        ReturnPoint(date(2024, 1, 2), Decimal("0.02"), date(2024, 1, 1)),
        ReturnPoint(date(2024, 1, 3), Decimal("0.03"), date(2024, 1, 2)),
        ReturnPoint(date(2024, 1, 4), Decimal("0.04"), date(2024, 1, 3)),
    ]
    benchmark = [
        ReturnPoint(date(2024, 1, 2), Decimal("0.01"), date(2024, 1, 1)),
        ReturnPoint(date(2024, 1, 4), Decimal("0.02"), date(2024, 1, 3)),
    ]
    result = calculate_benchmark_metrics(fund, benchmark)
    assert result.observation_count == 2
    assert result.fund_observation_count == 3
    assert result.benchmark_observation_count == 2
    assert result.coverage_ratio == Decimal("0.6666666666666666666666666667")


def test_zero_and_negative_benchmark_returns_are_valid_observations() -> None:
    fund = [
        ReturnPoint(date(2024, 1, 2), Decimal("-0.1"), date(2024, 1, 1)),
        ReturnPoint(date(2024, 1, 3), Decimal("0"), date(2024, 1, 2)),
        ReturnPoint(date(2024, 1, 4), Decimal("0.1"), date(2024, 1, 3)),
    ]
    benchmark = [
        ReturnPoint(date(2024, 1, 2), Decimal("-0.05"), date(2024, 1, 1)),
        ReturnPoint(date(2024, 1, 3), Decimal("0"), date(2024, 1, 2)),
        ReturnPoint(date(2024, 1, 4), Decimal("0.05"), date(2024, 1, 3)),
    ]
    result = calculate_benchmark_metrics(fund, benchmark)
    assert result.beta == Decimal("2")
    assert result.annualized_alpha == Decimal("0")
    assert result.annualized_fund_return == Decimal("0")
    assert result.annualized_benchmark_return == Decimal("0")


def test_calendar_year_does_not_mark_stale_november_data_complete() -> None:
    navs = _prices(
        ("2023-12-29", "100"),
        ("2024-11-15", "110"),
    )
    assert 2024 not in calendar_year_returns(navs, date(2025, 1, 2))
