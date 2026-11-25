"""Tests for dated investor cash-flow analytics."""

from datetime import date
from decimal import Decimal

import pytest

from mutual_fund_agent_analysis.analytics.cashflows import (
    CashFlow,
    normalize_cash_flows,
    xirr,
    xnpv,
)


def flows(*items: tuple[str, str]) -> list[CashFlow]:
    return [CashFlow(date.fromisoformat(day), Decimal(amount)) for day, amount in items]


def test_xirr_matches_simple_annual_cash_flow() -> None:
    result = xirr(flows(("2023-01-01", "-1000"), ("2024-01-01", "1100")))
    assert result == pytest.approx(Decimal("0.1"), abs=Decimal("0.00001"))


def test_xirr_handles_irregular_dates_using_actual_day_count() -> None:
    cash_flows = flows(("2024-01-01", "-1000"), ("2024-07-02", "1100"))
    result = xirr(cash_flows)
    assert xnpv(result, cash_flows).copy_abs() < Decimal("1e-18")


def test_xirr_aggregates_same_day_flows() -> None:
    cash_flows = flows(
        ("2023-01-01", "-600"),
        ("2023-01-01", "-400"),
        ("2024-01-01", "1100"),
    )
    assert xirr(cash_flows) == xirr(flows(("2023-01-01", "-1000"), ("2024-01-01", "1100")))


def test_xirr_rejects_missing_positive_or_negative_cash_flows() -> None:
    with pytest.raises(ValueError, match="contribution and one proceeds"):
        xirr(flows(("2023-01-01", "-100"), ("2024-01-01", "-110")))
    with pytest.raises(ValueError, match="contribution and one proceeds"):
        xirr(flows(("2023-01-01", "100"), ("2024-01-01", "110")))


def test_xirr_rejects_single_date_after_netting() -> None:
    with pytest.raises(ValueError, match="two non-zero"):
        normalize_cash_flows(flows(("2023-01-01", "-100"), ("2023-01-01", "100")))


def test_xnpv_rejects_rate_at_or_below_minus_one() -> None:
    with pytest.raises(ValueError, match="greater than -100%"):
        xnpv(Decimal("-1"), flows(("2023-01-01", "-100"), ("2024-01-01", "110")))


def test_xirr_rejects_multiple_roots() -> None:
    # Two sign changes can produce more than one valid rate root.
    cash_flows = flows(
        ("2020-01-01", "-100"),
        ("2021-01-01", "230"),
        ("2022-01-01", "-132"),
    )
    with pytest.raises(ValueError, match="multiple roots"):
        xirr(cash_flows)
