"""Peak-to-trough drawdown and recovery analysis."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from mutual_fund_agent_analysis.analytics.series import PricePoint, normalize_prices


@dataclass(frozen=True, slots=True)
class DrawdownMetrics:
    maximum_drawdown: Decimal
    peak_date: date
    trough_date: date
    recovery_date: date | None
    drawdown_duration_days: int
    recovery_duration_days: int | None
    maximum_underwater_duration_days: int


def calculate_drawdown(points: Iterable[PricePoint]) -> DrawdownMetrics:
    """Find the deepest peak-to-trough decline and longest time below a prior peak."""
    prices = normalize_prices(points)
    peak = prices[0]
    worst = Decimal("0")
    worst_peak = peak
    worst_trough = peak
    worst_recovery: date | None = peak.date
    underwater_start: date | None = None
    longest_underwater = 0

    for point in prices:
        if point.value >= peak.value:
            if underwater_start is not None:
                longest_underwater = max(
                    longest_underwater, (point.date - underwater_start).days
                )
                underwater_start = None
            peak = point
        else:
            if underwater_start is None:
                underwater_start = peak.date
            drawdown = point.value / peak.value - Decimal("1")
            if drawdown < worst:
                worst = drawdown
                worst_peak = peak
                worst_trough = point
                worst_recovery = None

        if (
            worst_recovery is None
            and point.date > worst_trough.date
            and point.value >= worst_peak.value
        ):
            worst_recovery = point.date

    if underwater_start is not None:
        longest_underwater = max(longest_underwater, (prices[-1].date - underwater_start).days)

    return DrawdownMetrics(
        maximum_drawdown=worst,
        peak_date=worst_peak.date,
        trough_date=worst_trough.date,
        recovery_date=worst_recovery,
        drawdown_duration_days=(worst_trough.date - worst_peak.date).days,
        recovery_duration_days=(
            (worst_recovery - worst_peak.date).days if worst_recovery is not None else None
        ),
        maximum_underwater_duration_days=longest_underwater,
    )
