"""Database-backed orchestration for deterministic single-fund analytics."""

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
    PricePoint,
    period_returns,
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
) -> FundAnalyticsReport:
    """Run the complete deterministic analytics suite over reconciled database data."""
    prices, conflicts = load_fund_prices(
        session,
        scheme_code,
        start_date,
        end_date,
        allow_nav_conflicts,
    )
    if len(prices) < 2:
        raise ValueError("At least two NAV observations are required for fund analytics.")

    fund_returns = period_returns(prices)
    benchmark_metrics = None
    if benchmark_code is not None:
        benchmark_prices = load_benchmark_prices(
            session,
            benchmark_code,
            prices[0].date,
            prices[-1].date,
            benchmark_source,
        )
        benchmark_metrics = calculate_benchmark_metrics(
            fund_returns,
            period_returns(benchmark_prices) if len(benchmark_prices) >= 2 else [],
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
        calendar_year_returns=tuple(sorted(calendar_year_returns(prices).items())),
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
    )
