from datetime import date
from decimal import Decimal

import pytest

from mutual_fund_agent_analysis.analytics.cashflows import (
    CashFlow,
    normalize_cash_flows,
    xirr,
)


def test_same_day_cash_flows_are_aggregated():
    result = normalize_cash_flows(
        [
            CashFlow(date(2024, 1, 1), Decimal("-100")),
            CashFlow(date(2024, 1, 1), Decimal("20")),
            CashFlow(date(2025, 1, 1), Decimal("90")),
        ]
    )
    assert result[0].amount == Decimal("-80")
    assert len(result) == 2


def test_leap_year_xirr_uses_actual_day_count():
    actual = xirr(
        [
            CashFlow(date(2024, 1, 1), Decimal("-100")),
            CashFlow(date(2025, 1, 1), Decimal("110")),
        ]
    )
    expected = (Decimal("1.1").ln() * Decimal(365) / Decimal(366)).exp() - Decimal("1")
    assert abs(actual - expected) < Decimal("1e-20")


def test_xirr_rejects_cash_flows_without_both_signs():
    with pytest.raises(ValueError, match="at least one contribution"):
        normalize_cash_flows(
            [
                CashFlow(date(2024, 1, 1), Decimal("-100")),
                CashFlow(date(2025, 1, 1), Decimal("-50")),
            ]
        )


def test_xirr_rejects_no_root_cash_flows():
    with pytest.raises(ValueError, match="no root"):
        xirr(
            [
                CashFlow(date(2024, 1, 1), Decimal("-100")),
                CashFlow(date(2025, 1, 1), Decimal("1e-30")),
            ]
        )
