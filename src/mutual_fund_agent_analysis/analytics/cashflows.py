"""Investor cash-flow primitives and date-based XIRR calculation.

The XIRR solver searches a documented bounded rate domain and rejects ambiguous
multiple-root cash-flow series instead of silently choosing one result.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext

DAYS_PER_XIRR_YEAR = Decimal("365")
_MIN_LOG_GROSS_RATE = Decimal("-13.81551055796427410410794872810618524561")
_MAX_LOG_GROSS_RATE = Decimal("13.81551055796427410410794872810618524561")
_SCAN_STEPS = 4096
_ROOT_TOLERANCE = Decimal("1e-24")
_MAX_ITERATIONS = 256


@dataclass(frozen=True, slots=True)
class CashFlow:
    """A dated investor cash flow; contributions are negative, proceeds positive."""

    date: date
    amount: Decimal


def normalize_cash_flows(flows: Iterable[CashFlow]) -> list[CashFlow]:
    """Validate flows, aggregate same-day entries, and return chronological net flows."""
    items = list(flows)
    if not items:
        raise ValueError("At least two dated cash flows are required.")
    if any(not isinstance(item, CashFlow) for item in items):
        raise TypeError("Every item must be a CashFlow.")
    if any(type(item.date) is not date for item in items):
        raise ValueError("Cash-flow dates must be datetime.date values.")
    if any(not isinstance(item.amount, Decimal) for item in items):
        raise TypeError("Cash-flow amounts must use Decimal values.")
    if any(not item.amount.is_finite() for item in items):
        raise ValueError("Cash-flow amounts must be finite.")

    totals: dict[date, Decimal] = defaultdict(Decimal)
    with localcontext() as context:
        context.prec = max(
            50,
            max(len(item.amount.as_tuple().digits) for item in items)
            + len(str(len(items)))
            + 4,
        )
        for item in items:
            totals[item.date] += item.amount

    result = [CashFlow(day, amount) for day, amount in sorted(totals.items()) if amount != 0]
    if len(result) < 2:
        raise ValueError("At least two non-zero cash-flow dates are required.")
    if not any(item.amount < 0 for item in result) or not any(
        item.amount > 0 for item in result
    ):
        raise ValueError(
            "Cash flows must contain at least one contribution and one proceeds flow."
        )
    return result


def xnpv(rate: Decimal, flows: Iterable[CashFlow]) -> Decimal:
    """Calculate net present value using actual day counts and a 365-day year."""
    if not isinstance(rate, Decimal):
        raise TypeError("rate must be a Decimal.")
    if not rate.is_finite() or rate <= Decimal("-1"):
        raise ValueError("rate must be finite and greater than -100%.")
    normalized = normalize_cash_flows(flows)
    origin = normalized[0].date
    with localcontext() as context:
        context.prec = 40
        log_gross_rate = (Decimal("1") + rate).ln()
        return sum(
            (
                flow.amount
                * (
                    -(
                        Decimal((flow.date - origin).days)
                        / DAYS_PER_XIRR_YEAR
                    )
                    * log_gross_rate
                ).exp()
                for flow in normalized
            ),
            Decimal("0"),
        )


def xirr(flows: Iterable[CashFlow]) -> Decimal:
    """Calculate XIRR in the bounded gross-rate domain [1e-6, 1e6].

    The solver scans log(1 + rate) for sign-changing brackets and bisects each
    bracket. Multiple sign-changing roots found at the scan resolution are
    rejected. Tangential roots and roots outside the documented domain are not
    guaranteed to be detected.
    """
    normalized = normalize_cash_flows(flows)
    origin = normalized[0].date

    with localcontext() as context:
        context.prec = 40
        elapsed = [Decimal((flow.date - origin).days) / DAYS_PER_XIRR_YEAR for flow in normalized]

        def value_at(log_gross_rate: Decimal) -> Decimal:
            return sum(
                (
                    flow.amount * (-(period * log_gross_rate)).exp()
                    for flow, period in zip(normalized, elapsed, strict=True)
                ),
                Decimal("0"),
            )

        step = (_MAX_LOG_GROSS_RATE - _MIN_LOG_GROSS_RATE) / Decimal(_SCAN_STEPS)
        brackets: list[tuple[Decimal, Decimal]] = []
        left = _MIN_LOG_GROSS_RATE
        left_value = value_at(left)

        for index in range(1, _SCAN_STEPS + 1):
            right = _MIN_LOG_GROSS_RATE + step * Decimal(index)
            right_value = value_at(right)
            if right_value == 0:
                brackets.append((right, right))
            elif left_value != 0 and (left_value < 0) != (right_value < 0):
                brackets.append((left, right))
            left, left_value = right, right_value

        unique_brackets: list[tuple[Decimal, Decimal]] = []
        for bracket in brackets:
            if not unique_brackets or bracket != unique_brackets[-1]:
                unique_brackets.append(bracket)

        if not unique_brackets:
            raise ValueError("XIRR has no root in the supported rate domain.")
        if len(unique_brackets) > 1:
            raise ValueError(
                "XIRR is ambiguous: multiple roots exist in the supported rate domain."
            )

        low, high = unique_brackets[0]
        if low == high:
            root = low
        else:
            low_value = value_at(low)
            for _ in range(_MAX_ITERATIONS):
                middle = (low + high) / Decimal("2")
                middle_value = value_at(middle)
                if abs(middle_value) <= _ROOT_TOLERANCE or abs(high - low) <= _ROOT_TOLERANCE:
                    low = high = middle
                    break
                if (low_value < 0) != (middle_value < 0):
                    high = middle
                else:
                    low = middle
                    low_value = middle_value
            root = (low + high) / Decimal("2")

        return root.exp() - Decimal("1")
