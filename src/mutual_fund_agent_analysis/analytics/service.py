"""Database-backed orchestration for deterministic single- and multi-fund analytics."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.analytics.benchmark import (
    BenchmarkMetrics,
    calculate_benchmark_metrics,
)
from mutual_fund_agent_analysis.analytics.drawdown import DrawdownMetrics, calculate_drawdown
from mutual_fund_agent_analysis.analytics.returns import (
    RollingReturn,
    absolute_return,
    cagr,
    calendar_year_returns,
    rolling_returns,
)
from mutual_fund_agent_analysis.analytics.risk import (
    DEFAULT_PERIODS_PER_YEAR,
    RiskMetrics,
    calculate_risk_metrics,
)
from mutual_fund_agent_analysis.analytics.series import (
    FREQUENCY_PERIODS_PER_YEAR,
    PricePoint,
    period_returns,
    resample_prices,
)
from mutual_fund_agent_analysis.models.benchmark import BenchmarkObservation
from mutual_fund_agent_analysis.models.nav_reconciliation import NavReconciliation


@dataclass(frozen=True, slots=True)
class FundAnalyticsReport:
    """Reproducible analytics and provenance for one scheme and date range."""

    scheme_code: int
    observation_count: int
    start_date: date
    end_date: date
    absolute_return: Decimal
    cagr: Decimal
    rolling_returns: tuple[RollingReturn, ...]
    calendar_year_returns: tuple[tuple[int, Decimal], ...]
    risk: RiskMetrics
    drawdown: DrawdownMetrics
    benchmark: BenchmarkMetrics | None
    annual_risk_free_rate: Decimal
    periods_per_year: int
    benchmark_code: str | None
    benchmark_source: str | None
    nav_conflict_dates: tuple[date, ...]
    calendar_year_as_of_date: date | None
    frequency: str


@dataclass(frozen=True, slots=True)
class FundComparisonReport:
    """Comparison over an identical set of NAV dates for every selected fund."""

    scheme_codes: tuple[int, ...]
    observation_count: int
    start_date: date
    end_date: date
    funds: tuple[FundAnalyticsReport, ...]
    benchmark_code: str | None
    frequency: str


def load_fund_prices(
    session: Session,
    scheme_code: int,
    start_date: date | None = None,
    end_date: date | None = None,
    allow_nav_conflicts: bool = False,
) -> tuple[list[PricePoint], tuple[date, ...]]:
    """Load canonical reconciled NAVs; conflicts are rejected unless explicitly allowed."""
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")
    statement = select(NavReconciliation).where(NavReconciliation.scheme_code == scheme_code)
    if start_date is not None:
        statement = statement.where(NavReconciliation.nav_date >= start_date)
    if end_date is not None:
        statement = statement.where(NavReconciliation.nav_date <= end_date)
    rows = session.scalars(statement.order_by(NavReconciliation.nav_date)).all()
    if not rows:
        raise ValueError(f"No reconciled NAV observations found for scheme {scheme_code}.")

    conflicts = tuple(row.nav_date for row in rows if row.status == "conflict")
    if conflicts and not allow_nav_conflicts:
        raise ValueError(
            f"{len(conflicts)} NAV reconciliation conflict(s) found; "
            "resolve them or explicitly set allow_nav_conflicts=True."
        )
    prices = [PricePoint(row.nav_date, Decimal(row.canonical_nav)) for row in rows]
    return prices, conflicts


def load_benchmark_prices(
    session: Session,
    benchmark_code: str,
    start_date: date,
    end_date: date,
    source: str = "niftyindices",
) -> list[PricePoint]:
    """Load one source-specific benchmark TRI series without filling missing dates."""
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")
    statement = (
        select(BenchmarkObservation)
        .where(
            BenchmarkObservation.benchmark_code == benchmark_code,
            BenchmarkObservation.source == source,
            BenchmarkObservation.observation_date >= start_date,
            BenchmarkObservation.observation_date <= end_date,
        )
        .order_by(BenchmarkObservation.observation_date)
    )
    rows = session.scalars(statement).all()
    return [PricePoint(row.observation_date, Decimal(row.tri_value)) for row in rows]


def _build_report(
    scheme_code: int,
    prices: list[PricePoint],
    conflicts: tuple[date, ...],
    benchmark_code: str | None,
    benchmark_source: str,
    benchmark_prices: list[PricePoint] | None,
    annual_risk_free_rate: Decimal,
    periods_per_year: int,
    calendar_year_as_of_date: date | None,
    frequency: str,
) -> FundAnalyticsReport:
    if frequency not in FREQUENCY_PERIODS_PER_YEAR:
        raise ValueError("Unsupported analysis frequency.")
    if frequency != "daily":
        periods_per_year = FREQUENCY_PERIODS_PER_YEAR[frequency]
    prices = resample_prices(prices, frequency)
    benchmark_prices = (
        resample_prices(benchmark_prices, frequency)
        if benchmark_prices is not None
        else None
    )
    if len(prices) < 2:
        raise ValueError("At least two NAV observations are required for fund analytics.")
    if calendar_year_as_of_date is not None and (
        type(calendar_year_as_of_date) is not date or calendar_year_as_of_date < prices[-1].date
    ):
        raise ValueError("calendar_year_as_of_date must be a date on or after the latest NAV.")

    fund_returns = period_returns(prices)
    benchmark_metrics = None
    if benchmark_code is not None:
        benchmark_returns = (
            period_returns(benchmark_prices)
            if benchmark_prices is not None and len(benchmark_prices) >= 2
            else []
        )
        benchmark_metrics = calculate_benchmark_metrics(
            fund_returns,
            benchmark_returns,
            annual_risk_free_rate,
            periods_per_year,
        )

    return FundAnalyticsReport(
        scheme_code=scheme_code,
        observation_count=len(prices),
        start_date=prices[0].date,
        end_date=prices[-1].date,
        absolute_return=absolute_return(prices),
        cagr=cagr(prices),
        rolling_returns=tuple(rolling_returns(prices)),
        calendar_year_returns=tuple(
            sorted(calendar_year_returns(prices, calendar_year_as_of_date).items())
        ),
        risk=calculate_risk_metrics(
            fund_returns,
            annual_risk_free_rate,
            periods_per_year,
        ),
        drawdown=calculate_drawdown(prices),
        benchmark=benchmark_metrics,
        annual_risk_free_rate=annual_risk_free_rate,
        periods_per_year=periods_per_year,
        benchmark_code=benchmark_code,
        benchmark_source=benchmark_source if benchmark_code is not None else None,
        nav_conflict_dates=conflicts,
        calendar_year_as_of_date=calendar_year_as_of_date,
        frequency=frequency,
    )


def analyze_fund(
    session: Session,
    scheme_code: int,
    benchmark_code: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    annual_risk_free_rate: Decimal = Decimal("0"),
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
    benchmark_source: str = "niftyindices",
    allow_nav_conflicts: bool = False,
    calendar_year_as_of_date: date | None = None,
    frequency: str = "daily",
) -> FundAnalyticsReport:
    """Run deterministic analytics and retain explicit calendar-year completion context."""
    prices, conflicts = load_fund_prices(
        session, scheme_code, start_date, end_date, allow_nav_conflicts
    )
    benchmark_prices = (
        load_benchmark_prices(
            session, benchmark_code, prices[0].date, prices[-1].date, benchmark_source
        )
        if benchmark_code is not None
        else None
    )
    return _build_report(
        scheme_code,
        prices,
        conflicts,
        benchmark_code,
        benchmark_source,
        benchmark_prices,
        annual_risk_free_rate,
        periods_per_year,
        calendar_year_as_of_date,
        frequency,
    )


def compare_funds(
    session: Session,
    scheme_codes: list[int] | tuple[int, ...],
    benchmark_code: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    annual_risk_free_rate: Decimal = Decimal("0"),
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
    benchmark_source: str = "niftyindices",
    allow_nav_conflicts: bool = False,
    calendar_year_as_of_date: date | None = None,
    frequency: str = "daily",
) -> FundComparisonReport:
    """Compare 2–5 schemes using the exact intersection of their available NAV dates.

    When a benchmark is selected, its available TRI dates are also intersected.
    No price or benchmark series is forward-filled or interpolated.
    """
    codes = tuple(scheme_codes)
    if not 2 <= len(codes) <= 5:
        raise ValueError("Comparison requires between two and five distinct schemes.")
    if len(codes) != len(set(codes)):
        raise ValueError("Comparison scheme codes must be unique.")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")

    loaded: dict[int, tuple[list[PricePoint], tuple[date, ...]]] = {
        code: load_fund_prices(session, code, start_date, end_date, allow_nav_conflicts)
        for code in codes
    }
    common_dates = set(point.date for point in loaded[codes[0]][0])
    for code in codes[1:]:
        common_dates.intersection_update(point.date for point in loaded[code][0])

    benchmark_prices: list[PricePoint] | None = None
    if benchmark_code is not None:
        earliest = max(points[0].date for points, _ in loaded.values())
        latest = min(points[-1].date for points, _ in loaded.values())
        if earliest > latest:
            raise ValueError("Selected funds have no overlapping date range.")
        benchmark_prices = load_benchmark_prices(
            session, benchmark_code, earliest, latest, benchmark_source
        )
        common_dates.intersection_update(point.date for point in benchmark_prices)

    ordered_dates = sorted(common_dates)
    if len(ordered_dates) < 2:
        raise ValueError("Selected funds do not have at least two common observation dates.")
    date_set = set(ordered_dates)
    aligned_benchmark = (
        [point for point in benchmark_prices if point.date in date_set]
        if benchmark_prices is not None
        else None
    )
    reports = []
    for code in codes:
        source_prices, conflicts = loaded[code]
        aligned_prices = [point for point in source_prices if point.date in date_set]
        aligned_conflicts = tuple(day for day in conflicts if day in date_set)
        reports.append(
            _build_report(
                code,
                aligned_prices,
                aligned_conflicts,
                benchmark_code,
                benchmark_source,
                aligned_benchmark,
                annual_risk_free_rate,
                periods_per_year,
                calendar_year_as_of_date,
                frequency,
            )
        )

    return FundComparisonReport(
        scheme_codes=codes,
        observation_count=reports[0].observation_count,
        start_date=reports[0].start_date,
        end_date=reports[0].end_date,
        funds=tuple(reports),
        benchmark_code=benchmark_code,
        frequency=frequency,
    )
