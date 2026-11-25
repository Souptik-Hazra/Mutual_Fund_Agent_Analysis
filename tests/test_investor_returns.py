from datetime import date
from decimal import Decimal

import pytest

from mutual_fund_agent_analysis.analytics.investor import (
    InvestorTransactionInput,
    calculate_investor_returns,
)


def test_actual_investor_xirr_includes_redemptions_dividends_and_open_units() -> None:
    transactions = [
        InvestorTransactionInput(
            date(2024, 1, 1), "purchase", Decimal("1000"), Decimal("100")
        ),
        InvestorTransactionInput(
            date(2024, 6, 1), "dividend_payout", Decimal("50")
        ),
        InvestorTransactionInput(
            date(2024, 9, 1), "redemption", Decimal("200"), Decimal("20")
        ),
    ]
    result = calculate_investor_returns(
        transactions, date(2025, 1, 1), Decimal("12")
    )
    assert result.total_units == Decimal("80")
    assert result.cash_invested == Decimal("1000")
    assert result.realized_proceeds == Decimal("250")
    assert result.current_value == Decimal("960")
    assert result.absolute_gain == Decimal("210")
    assert result.xirr is not None
    assert result.xirr_limitation is None


def test_fully_redeemed_investment_does_not_require_terminal_nav() -> None:
    transactions = [
        InvestorTransactionInput(
            date(2024, 1, 1), "purchase", Decimal("1000"), Decimal("100")
        ),
        InvestorTransactionInput(
            date(2025, 1, 1), "redemption", Decimal("1200"), Decimal("100")
        ),
    ]
    result = calculate_investor_returns(transactions, date(2025, 1, 1))
    assert result.total_units == 0
    assert result.current_value == 0
    assert result.valuation_nav is None
    assert result.xirr is not None


def test_charges_and_taxes_reduce_investor_gain() -> None:
    transactions = [
        InvestorTransactionInput(
            date(2024, 1, 1), "purchase", Decimal("1000"), Decimal("100")
        ),
        InvestorTransactionInput(date(2024, 1, 2), "charges", Decimal("10")),
        InvestorTransactionInput(date(2024, 1, 3), "tax", Decimal("5")),
    ]
    result = calculate_investor_returns(
        transactions, date(2024, 2, 1), Decimal("11")
    )
    assert result.expenses == Decimal("15")
    assert result.absolute_gain == Decimal("85")


def test_open_position_requires_exact_positive_nav() -> None:
    transaction = InvestorTransactionInput(
        date(2024, 1, 1), "sip", Decimal("1000"), Decimal("100")
    )
    with pytest.raises(ValueError, match="exact, finite positive"):
        calculate_investor_returns([transaction], date(2024, 2, 1))


def test_over_redemption_is_rejected() -> None:
    transactions = [
        InvestorTransactionInput(
            date(2024, 1, 1), "purchase", Decimal("1000"), Decimal("10")
        ),
        InvestorTransactionInput(
            date(2024, 2, 1), "redemption", Decimal("500"), Decimal("11")
        ),
    ]
    with pytest.raises(ValueError, match="exceed the recorded unit balance"):
        calculate_investor_returns(transactions, date(2024, 2, 1))


def test_future_transaction_is_rejected() -> None:
    transaction = InvestorTransactionInput(
        date(2024, 2, 1), "purchase", Decimal("1000"), Decimal("10")
    )
    with pytest.raises(ValueError, match="after as_of_date"):
        calculate_investor_returns([transaction], date(2024, 1, 31), Decimal("10"))


def test_zero_or_non_finite_transaction_amount_is_rejected() -> None:
    transaction = InvestorTransactionInput(
        date(2024, 1, 1), "purchase", Decimal("NaN"), Decimal("10")
    )
    with pytest.raises(ValueError, match="finite positive"):
        calculate_investor_returns([transaction], date(2024, 1, 1), Decimal("10"))
