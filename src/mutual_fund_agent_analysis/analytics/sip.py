"""Exact-date monthly SIP simulation; missing NAVs are never filled."""
from calendar import monthrange
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from mutual_fund_agent_analysis.analytics.cashflows import CashFlow, xirr
from mutual_fund_agent_analysis.analytics.series import PricePoint


@dataclass(frozen=True, slots=True)
class SipInstallment:
    due_date: date
    amount: Decimal
    nav: Decimal | None
    units: Decimal
    status: str


@dataclass(frozen=True, slots=True)
class SipSimulation:
    installments: tuple[SipInstallment, ...]
    scheduled_count: int
    invested_count: int
    missed_count: int
    invested_amount: Decimal
    units_allotted: Decimal
    valuation_date: date
    valuation_nav: Decimal
    current_value: Decimal
    absolute_gain: Decimal
    xirr: Decimal | None
    coverage_ratio: Decimal


def _monthly_dates(start: date, end: date, day_of_month: int) -> list[date]:
    if type(day_of_month) is not int or not 1 <= day_of_month <= 31:
        raise ValueError("day_of_month must be an integer between 1 and 31.")
    dates = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        due = date(year, month, min(day_of_month, monthrange(year, month)[1]))
        if start <= due <= end:
            dates.append(due)
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return dates


def simulate_monthly_sip(
    navs: Iterable[PricePoint],
    start_date: date,
    end_date: date,
    monthly_amount: Decimal,
    valuation_date: date,
    day_of_month: int = 1,
) -> SipSimulation:
    """Simulate SIP purchases only where an exact-date NAV exists."""
    if any(type(value) is not date for value in (start_date, end_date, valuation_date)):
        raise TypeError("SIP dates must be datetime.date values.")
    if start_date > end_date or valuation_date < end_date:
        raise ValueError("Require start_date <= end_date <= valuation_date.")
    if not isinstance(monthly_amount, Decimal) or not monthly_amount.is_finite() or monthly_amount <= 0:
        raise ValueError("monthly_amount must be a finite positive Decimal.")
    points = list(navs)
    if any(not isinstance(point, PricePoint) for point in points):
        raise TypeError("navs must contain PricePoint values.")
    if any(not point.value.is_finite() or point.value <= 0 for point in points):
        raise ValueError("NAV values must be finite and greater than zero.")
    by_date = {point.date: point.value for point in points}
    if len(by_date) != len(points):
        raise ValueError("Duplicate NAV dates are not allowed.")
    if valuation_date not in by_date:
        raise ValueError("An exact NAV observation is required on valuation_date.")

    schedule, flows = [], []
    total_units = invested = Decimal("0")
    invested_count = 0
    for due in _monthly_dates(start_date, end_date, day_of_month):
        nav = by_date.get(due)
        if nav is None:
            schedule.append(SipInstallment(due, monthly_amount, None, Decimal("0"), "missed_nav"))
            continue
        units = monthly_amount / nav
        total_units += units
        invested += monthly_amount
        invested_count += 1
        flows.append(CashFlow(due, -monthly_amount))
        schedule.append(SipInstallment(due, monthly_amount, nav, units, "invested"))
    if not invested_count:
        raise ValueError("No SIP installments had an exact-date NAV observation.")
    current_value = total_units * by_date[valuation_date]
    flows.append(CashFlow(valuation_date, current_value))
    try:
        realized_xirr = xirr(flows)
    except ValueError:
        realized_xirr = None
    return SipSimulation(
        tuple(schedule), len(schedule), invested_count, len(schedule) - invested_count,
        invested, total_units, valuation_date, by_date[valuation_date], current_value,
        current_value - invested, realized_xirr, Decimal(invested_count) / Decimal(len(schedule)),
    )
