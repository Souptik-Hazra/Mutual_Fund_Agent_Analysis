from datetime import date
from decimal import Decimal

import pytest

from mutual_fund_agent_analysis.analytics.series import PricePoint
from mutual_fund_agent_analysis.analytics.sip import simulate_monthly_sip


def test_monthly_sip_allots_units_and_reports_value() -> None:
    navs = [
        PricePoint(date(2024, 1, 1), Decimal("10")),
        PricePoint(date(2024, 2, 1), Decimal("20")),
        PricePoint(date(2024, 3, 1), Decimal("25")),
    ]
    result = simulate_monthly_sip(
        navs, date(2024, 1, 1), date(2024, 2, 1),
        Decimal("1000"), date(2024, 3, 1),
    )
    assert result.invested_amount == Decimal("2000")
    assert result.units_allotted == Decimal("150")
    assert result.current_value == Decimal("3750")
    assert result.absolute_gain == Decimal("1750")
    assert result.xirr is not None


def test_missing_sip_nav_is_reported_not_filled() -> None:
    navs = [
        PricePoint(date(2024, 1, 1), Decimal("10")),
        PricePoint(date(2024, 3, 1), Decimal("25")),
    ]
    result = simulate_monthly_sip(
        navs, date(2024, 1, 1), date(2024, 2, 1),
        Decimal("1000"), date(2024, 3, 1),
    )
    assert result.missed_count == 1
    assert result.installments[1].status == "missed_nav"
    assert result.coverage_ratio == Decimal("0.5")


def test_sip_requires_exact_valuation_nav() -> None:
    with pytest.raises(ValueError, match="exact NAV"):
        simulate_monthly_sip(
            [PricePoint(date(2024, 1, 1), Decimal("10"))],
            date(2024, 1, 1), date(2024, 1, 1),
            Decimal("1000"), date(2024, 1, 2),
        )


def test_sip_clamps_day_to_month_end() -> None:
    navs = [
        PricePoint(date(2024, 1, 31), Decimal("10")),
        PricePoint(date(2024, 2, 29), Decimal("10")),
        PricePoint(date(2024, 3, 31), Decimal("10")),
    ]
    result = simulate_monthly_sip(
        navs, date(2024, 1, 1), date(2024, 3, 31),
        Decimal("100"), date(2024, 3, 31), 31,
    )
    assert [item.due_date for item in result.installments] == [
        date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31)
    ]


def test_sip_rejects_duplicate_and_invalid_nav_observations() -> None:
    duplicate = [
        PricePoint(date(2024, 1, 1), Decimal("10")),
        PricePoint(date(2024, 1, 1), Decimal("11")),
    ]
    with pytest.raises(ValueError, match="Duplicate"):
        simulate_monthly_sip(
            duplicate, date(2024, 1, 1), date(2024, 1, 1),
            Decimal("100"), date(2024, 1, 1),
        )
    invalid = [PricePoint(date(2024, 1, 1), Decimal("0"))]
    with pytest.raises(ValueError, match="greater than zero"):
        simulate_monthly_sip(
            invalid, date(2024, 1, 1), date(2024, 1, 1),
            Decimal("100"), date(2024, 1, 1),
        )


def test_sip_requires_at_least_one_scheduled_due_date() -> None:
    with pytest.raises(ValueError, match="No SIP installments"):
        simulate_monthly_sip(
            [PricePoint(date(2024, 1, 1), Decimal("10"))],
            date(2024, 2, 1), date(2024, 2, 1),
            Decimal("100"), date(2024, 2, 1),
        )
