from datetime import date
from decimal import Decimal

import pytest

from mutual_fund_agent_analysis.analytics.active_risk import calculate_active_risk_metrics
from mutual_fund_agent_analysis.analytics.series import ReturnPoint


def test_tracking_error_and_information_ratio() -> None:
    fund = [
        ReturnPoint(date(2024, 1, 2), Decimal("0.03"), date(2024, 1, 1)),
        ReturnPoint(date(2024, 1, 3), Decimal("0.01"), date(2024, 1, 2)),
        ReturnPoint(date(2024, 1, 4), Decimal("0.04"), date(2024, 1, 3)),
    ]
    benchmark = [
        ReturnPoint(date(2024, 1, 2), Decimal("0.01"), date(2024, 1, 1)),
        ReturnPoint(date(2024, 1, 3), Decimal("0.02"), date(2024, 1, 2)),
        ReturnPoint(date(2024, 1, 4), Decimal("0.02"), date(2024, 1, 3)),
    ]
    result = calculate_active_risk_metrics(fund, benchmark, 252)
    assert result.aligned_observation_count == 3
    assert result.mean_active_return == Decimal("0.01")
    assert result.tracking_error is not None and result.tracking_error > 0
    assert result.information_ratio is not None


def test_active_risk_undefined_with_one_aligned_observation() -> None:
    point = ReturnPoint(date(2024, 1, 2), Decimal("0.01"), date(2024, 1, 1))
    result = calculate_active_risk_metrics([point], [point], 252)
    assert result.tracking_error is None
    assert result.information_ratio is None


def test_active_risk_rejects_invalid_frequency() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        calculate_active_risk_metrics([], [], 0)


def test_active_risk_rejects_boolean_frequency() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        calculate_active_risk_metrics([], [], True)


def test_active_risk_uses_common_exact_intervals_only() -> None:
    fund = [
        ReturnPoint(date(2024, 1, 2), Decimal("0.02"), date(2024, 1, 1)),
        ReturnPoint(date(2024, 1, 4), Decimal("0.04"), date(2024, 1, 3)),
    ]
    benchmark = [
        ReturnPoint(date(2024, 1, 2), Decimal("0.01"), date(2024, 1, 1)),
        ReturnPoint(date(2024, 1, 3), Decimal("0.01"), date(2024, 1, 2)),
        ReturnPoint(date(2024, 1, 4), Decimal("0.02"), date(2024, 1, 3)),
    ]
    result = calculate_active_risk_metrics(fund, benchmark, 252)
    assert result.aligned_observation_count == 2
    assert result.coverage_ratio == Decimal("2") / Decimal("3")
