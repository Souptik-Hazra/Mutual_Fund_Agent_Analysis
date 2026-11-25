"""Conservative reinvested-IDCW total-return calculation."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext


@dataclass(frozen=True, slots=True)
class TotalReturnPoint:
    date: date
    nav: Decimal
    distribution_per_unit: Decimal
    nav_index: Decimal
    total_return_index: Decimal


def reinvested_distribution_index(
    navs: Sequence[tuple[date, Decimal]],
    distributions: Mapping[date, Decimal],
    *,
    base_value: Decimal = Decimal("100"),
) -> list[TotalReturnPoint]:
    """Build a reinvested distribution index using ex-date NAV reinvestment.

    Each distribution is reinvested at the ex-date NAV, so the ex-date gross
    return factor is (ex-date NAV + distribution per unit) / prior NAV.
    This function intentionally does not decide whether provider coverage is
    complete; callers must establish and disclose that independently.
    """
    if len(navs) < 2:
        raise ValueError("At least two NAV observations are required.")
    if not base_value.is_finite() or base_value <= 0:
        raise ValueError("base_value must be finite and greater than zero.")

    ordered = list(navs)
    dates = [item[0] for item in ordered]
    if any(type(day) is not date for day in dates):
        raise ValueError("NAV dates must be datetime.date values.")
    if dates != sorted(set(dates)):
        raise ValueError("NAV observations must have unique, ascending dates.")
    if any(not value.is_finite() or value <= 0 for _, value in ordered):
        raise ValueError("NAV values must be finite and greater than zero.")
    if any(day not in set(dates[1:]) for day in distributions):
        raise ValueError(
            "Each distribution ex-date must have an NAV observation after the base date."
        )
    if any(not amount.is_finite() or amount < 0 for amount in distributions.values()):
        raise ValueError("Distribution amounts must be finite and non-negative.")

    output: list[TotalReturnPoint] = []
    nav_index = base_value
    total_index = base_value
    with localcontext() as context:
        context.prec = 36
        first_date, first_nav = ordered[0]
        output.append(TotalReturnPoint(first_date, first_nav, Decimal("0"), nav_index, total_index))
        for previous, current in zip(ordered, ordered[1:], strict=False):
            day, nav = current
            distribution = distributions.get(day, Decimal("0"))
            nav_index *= nav / previous[1]
            total_index *= (nav + distribution) / previous[1]
            output.append(TotalReturnPoint(day, nav, distribution, nav_index, total_index))
    return output
