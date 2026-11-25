"""Deterministic investor-level returns from dated transaction ledger entries."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from mutual_fund_agent_analysis.analytics.cashflows import CashFlow, xirr

UNIT_ADDITIONS = {"purchase", "sip", "additional_purchase", "switch_in"}
UNIT_REDUCTIONS = {"redemption", "switch_out"}
PROCEEDS_TYPES = {"redemption", "switch_out", "dividend_payout"}
EXPENSE_TYPES = {"charges", "tax"}
VALID_TYPES = UNIT_ADDITIONS | UNIT_REDUCTIONS | PROCEEDS_TYPES | EXPENSE_TYPES


@dataclass(frozen=True, slots=True)
class InvestorTransactionInput:
    transaction_date: date
    transaction_type: str
    amount: Decimal
    units: Decimal | None = None


@dataclass(frozen=True, slots=True)
class InvestorReturnReport:
    as_of_date: date
    transaction_count: int
    total_units: Decimal
    cash_invested: Decimal
    realized_proceeds: Decimal
    expenses: Decimal
    current_value: Decimal
    valuation_nav: Decimal | None
    absolute_gain: Decimal
    xirr: Decimal | None
    xirr_limitation: str | None


def calculate_investor_returns(
    transactions: Iterable[InvestorTransactionInput],
    as_of_date: date,
    valuation_nav: Decimal | None = None,
) -> InvestorReturnReport:
    """Calculate realized plus unrealized investor returns without imputing missing NAVs."""
    if type(as_of_date) is not date:
        raise TypeError("as_of_date must be a datetime.date value.")
    items = list(transactions)
    if not items:
        raise ValueError("No investor transactions are available for this scheme and date.")

    total_units = Decimal("0")
    cash_invested = Decimal("0")
    realized_proceeds = Decimal("0")
    expenses = Decimal("0")
    flows: list[CashFlow] = []

    for item in items:
        if type(item.transaction_date) is not date:
            raise ValueError("Transaction dates must be datetime.date values.")
        if item.transaction_date > as_of_date:
            raise ValueError("Transactions after as_of_date are not allowed.")
        if item.transaction_type not in VALID_TYPES:
            raise ValueError("Unsupported investor transaction type.")
        if (
            not isinstance(item.amount, Decimal)
            or not item.amount.is_finite()
            or item.amount <= 0
        ):
            raise ValueError("Transaction amounts must be finite positive Decimal values.")

        if item.transaction_type in UNIT_ADDITIONS | UNIT_REDUCTIONS:
            if (
                not isinstance(item.units, Decimal)
                or not item.units.is_finite()
                or item.units <= 0
            ):
                raise ValueError("Unit-changing transactions require finite positive units.")
            if item.transaction_type in UNIT_ADDITIONS:
                total_units += item.units
                cash_invested += item.amount
            else:
                total_units -= item.units
                realized_proceeds += item.amount
        elif item.units is not None:
            raise ValueError("Dividend, charge, and tax transactions must not contain units.")

        if item.transaction_type in PROCEEDS_TYPES:
            realized_proceeds += (
                item.amount if item.transaction_type == "dividend_payout" else Decimal("0")
            )
        if item.transaction_type in EXPENSE_TYPES:
            expenses += item.amount

        amount = (
            -item.amount
            if item.transaction_type in UNIT_ADDITIONS | EXPENSE_TYPES
            else item.amount
        )
        flows.append(CashFlow(item.transaction_date, amount))

    if total_units < 0:
        raise ValueError("Redemptions and switches exceed the recorded unit balance.")
    if total_units > 0:
        if (
            not isinstance(valuation_nav, Decimal)
            or not valuation_nav.is_finite()
            or valuation_nav <= 0
        ):
            raise ValueError("An exact, finite positive valuation NAV is required for open units.")
        current_value = total_units * valuation_nav
        flows.append(CashFlow(as_of_date, current_value))
    else:
        current_value = Decimal("0")
        valuation_nav = None

    try:
        investor_xirr = xirr(flows)
        limitation = None
    except ValueError as exc:
        investor_xirr = None
        limitation = str(exc)

    return InvestorReturnReport(
        as_of_date=as_of_date,
        transaction_count=len(items),
        total_units=total_units,
        cash_invested=cash_invested,
        realized_proceeds=realized_proceeds,
        expenses=expenses,
        current_value=current_value,
        valuation_nav=valuation_nav,
        absolute_gain=realized_proceeds + current_value - cash_invested - expenses,
        xirr=investor_xirr,
        xirr_limitation=limitation,
    )
