"""Database-backed orchestration for deterministic single- and multi-fund analytics."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.analytics.benchmark import (
    BenchmarkMetrics,
    calculate_benchmark_metrics,
)
from mutual_fund_agent_analysis.analytics.distributions import (
    payout_distribution_index,
    reinvested_distribution_index,
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
from mutual_fund_agent_analysis.models.financial import (
    DistributionCoverageAttestation,
    DistributionObservation,
)
from mutual_fund_agent_analysis.models.intelligence import DataSource
from mutual_fund_agent_analysis.models.nav_reconciliation import NavReconciliation
from mutual_fund_agent_analysis.models.scheme import MutualFundScheme


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
    frequency: str = "daily"
    return_basis: str = "nav_only_excludes_idcw"
    benchmark_return_basis: str | None = None
    base100_series: tuple[tuple[date, Decimal], ...] = ()
    methodology: dict[str, str] = field(default_factory=dict)
    distribution_coverage_status: str = "not_required"
    benchmark_unavailable_reason: str | None = None


@dataclass(frozen=True, slots=True)
class FundComparisonReport:
    """Comparison over an identical set of NAV dates for every selected fund."""

    scheme_codes: tuple[int, ...]
    observation_count: int
    start_date: date
    end_date: date
    funds: tuple[FundAnalyticsReport, ...]
    benchmark_code: str | None
    frequency: str = "daily"
    comparability_warnings: tuple[str, ...] = ()


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
        coverage_statement = select(NavReconciliation).where(
            NavReconciliation.scheme_code == scheme_code
        )
        coverage = session.scalars(coverage_statement.order_by(NavReconciliation.nav_date)).all()
        if not coverage:
            raise ValueError(
                f"No reconciled NAV observations exist for scheme {scheme_code}. "
                "Synchronize NAV history before running analytics."
            )
        available_start = coverage[0].nav_date
        available_end = coverage[-1].nav_date
        requested_window = (
            f"{start_date.isoformat() if start_date else 'earliest'} to "
            f"{end_date.isoformat() if end_date else 'latest'}"
        )
        raise ValueError(
            f"No reconciled NAV observations for scheme {scheme_code} in requested "
            f"window {requested_window}. Available NAV history: "
            f"{available_start.isoformat()} to {available_end.isoformat()}."
        )

    conflicts = tuple(row.nav_date for row in rows if row.status == "conflict")
    if conflicts and not allow_nav_conflicts:
        raise ValueError(
            f"{len(conflicts)} NAV reconciliation conflict(s) found; "
            "resolve them or explicitly set allow_nav_conflicts=True."
        )
    prices = [PricePoint(row.nav_date, Decimal(row.canonical_nav)) for row in rows]
    return prices, conflicts


def load_fund_return_prices(
    session: Session,
    scheme_code: int,
    start_date: date | None = None,
    end_date: date | None = None,
    allow_nav_conflicts: bool = False,
) -> tuple[list[PricePoint], tuple[date, ...], str, str, str | None]:
    """Use IDCW total returns only when an official verified attestation covers the window."""
    prices, conflicts = load_fund_prices(
        session, scheme_code, start_date, end_date, allow_nav_conflicts
    )
    scheme = session.get(MutualFundScheme, scheme_code)
    if scheme is None:
        raise ValueError(f"Scheme {scheme_code} is not present in the local scheme catalogue.")
    if scheme.option_type == "growth":
        return prices, conflicts, "growth_nav_total_return", "not_required", None
    if scheme.option_type not in {"idcw_payout", "idcw_reinvestment"}:
        return (
            prices,
            conflicts,
            "nav_only_excludes_idcw",
            "unavailable",
            (
                "Scheme option is not explicitly classified as Growth, IDCW payout "
                "or IDCW reinvestment."
            ),
        )

    attestations = session.scalars(
        select(DistributionCoverageAttestation)
        .where(
            DistributionCoverageAttestation.scheme_code == scheme_code,
            DistributionCoverageAttestation.coverage_complete.is_(True),
            DistributionCoverageAttestation.verification_status == "verified",
            DistributionCoverageAttestation.start_date <= prices[0].date,
            DistributionCoverageAttestation.end_date >= prices[-1].date,
        )
        .order_by(DistributionCoverageAttestation.attested_at.desc())
    ).all()
    attestation = None
    for item in attestations:
        source = session.get(DataSource, item.source_key)
        if (
            source is not None
            and source.enabled
            and source.is_official
            and source.source_type == "official"
        ):
            attestation = item
            break
    if attestation is None:
        return (
            prices,
            conflicts,
            "nav_only_excludes_idcw",
            "incomplete",
            (
                "No verified, complete, enabled official-source attestation covers "
                "the full observed NAV window."
            ),
        )

    rows = session.scalars(
        select(DistributionObservation)
        .where(
            DistributionObservation.scheme_code == scheme_code,
            DistributionObservation.source_key == attestation.source_key,
            DistributionObservation.option_type == scheme.option_type,
            DistributionObservation.status == "active",
            DistributionObservation.ex_date > prices[0].date,
            DistributionObservation.ex_date <= prices[-1].date,
        )
        .order_by(DistributionObservation.ex_date, DistributionObservation.revision)
    ).all()
    distributions: dict[date, Decimal] = {}
    for item in rows:
        source = session.get(DataSource, item.source_key)
        if (
            item.verification_status != "verified"
            or source is None
            or not source.enabled
            or not source.is_official
            or source.source_type != "official"
        ):
            return (
                prices,
                conflicts,
                "nav_only_excludes_idcw",
                "incomplete",
                "An in-range distribution is not verified against an enabled official source.",
            )
        distributions[item.ex_date] = distributions.get(item.ex_date, Decimal("0")) + Decimal(
            item.amount_per_unit
        )

    builder = (
        payout_distribution_index
        if scheme.option_type == "idcw_payout"
        else reinvested_distribution_index
    )
    try:
        index = builder([(point.date, point.value) for point in prices], distributions)
    except ValueError as exc:
        return (
            prices,
            conflicts,
            "nav_only_excludes_idcw",
            "incomplete",
            f"IDCW total-return series could not be constructed: {exc}",
        )
    basis = (
        "idcw_payout_total_return"
        if scheme.option_type == "idcw_payout"
        else "idcw_reinvested_total_return"
    )
    return (
        [PricePoint(point.date, point.total_return_index) for point in index],
        conflicts,
        basis,
        "verified_complete",
        None,
    )


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
    return_basis: str = "growth_nav_total_return",
    distribution_coverage_status: str = "not_required",
    distribution_unavailable_reason: str | None = None,
) -> FundAnalyticsReport:
    benchmark_unavailable_reason = None
    if return_basis == "nav_only_excludes_idcw" and benchmark_code is not None:
        benchmark_unavailable_reason = distribution_unavailable_reason or (
            "Benchmark-relative metrics are suppressed because verified IDCW "
            "total-return coverage is unavailable."
        )
        benchmark_code = None
        benchmark_prices = None
    if frequency not in FREQUENCY_PERIODS_PER_YEAR:
        raise ValueError("Unsupported analysis frequency.")
    if frequency != "daily":
        periods_per_year = FREQUENCY_PERIODS_PER_YEAR[frequency]
    prices = resample_prices(prices, frequency)
    benchmark_prices = (
        resample_prices(benchmark_prices, frequency) if benchmark_prices is not None else None
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
        return_basis=return_basis,
        benchmark_return_basis="tri" if benchmark_code is not None else None,
        distribution_coverage_status=distribution_coverage_status,
        benchmark_unavailable_reason=benchmark_unavailable_reason,
        base100_series=tuple(
            (point.date, Decimal("100") * point.value / prices[0].value) for point in prices
        ),
        methodology={
            "fund_return_basis": return_basis,
            "distribution_coverage_status": distribution_coverage_status,
            "distribution_coverage_limitation": (
                distribution_unavailable_reason or "Not applicable."
            ),
            "absolute_return": "(ending fund return index / starting fund return index) - 1.",
            "cagr": "Geometric annualization using 365.25 calendar days.",
            "annualized_volatility": (
                "Sample standard deviation of periodic simple fund returns multiplied by "
                "sqrt(periods_per_year)."
            ),
            "annualized_downside_deviation": (
                "Root mean square periodic shortfall below the periodic risk-free rate, "
                "multiplied by sqrt(periods_per_year)."
            ),
            "sharpe_sortino": (
                "Periodic excess returns use annual_risk_free_rate / periods_per_year."
            ),
            "beta": (
                "Sample covariance of exact interval-aligned fund and TRI returns divided "
                "by sample benchmark variance."
            ),
            "alpha": ("Arithmetic annualized Jensen alpha using the periodic risk-free rate."),
            "benchmark_return": (
                "Arithmetic mean of exact interval-aligned TRI simple returns multiplied "
                "by periods_per_year; not CAGR."
            ),
        },
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
    prices, conflicts, return_basis, coverage_status, coverage_reason = load_fund_return_prices(
        session, scheme_code, start_date, end_date, allow_nav_conflicts
    )
    benchmark_prices = (
        load_benchmark_prices(
            session, benchmark_code, prices[0].date, prices[-1].date, benchmark_source
        )
        if benchmark_code is not None
        and not (
            return_basis == "nav_only_excludes_idcw" and coverage_status != "verified_complete"
        )
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
        return_basis,
        coverage_status,
        coverage_reason,
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
    """Compare schemes on exact common dates and compatible total-return bases."""
    codes = tuple(scheme_codes)
    if not 2 <= len(codes) <= 5 or len(codes) != len(set(codes)):
        raise ValueError("Comparison requires between two and five distinct schemes.")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")

    scheme_rows = session.scalars(
        select(MutualFundScheme).where(MutualFundScheme.scheme_code.in_(codes))
    ).all()
    option_by_code = {row.scheme_code: row.option_type for row in scheme_rows}
    if set(option_by_code) != set(codes):
        raise ValueError("One or more selected schemes are missing from the local catalogue.")
    options = set(option_by_code.values())
    if len(options) > 1:
        raise ValueError(
            "Mixed Growth and IDCW options are not ranked together; select "
            "like-for-like scheme options with the same option type."
        )

    loaded = {
        code: load_fund_return_prices(session, code, start_date, end_date, allow_nav_conflicts)
        for code in codes
    }
    bases = {item[2] for item in loaded.values()}
    if len(bases) > 1:
        raise ValueError(
            "Selected IDCW schemes do not share one verified return basis; "
            "comparison is unavailable."
        )
    warnings = []
    effective_benchmark = benchmark_code
    if "nav_only_excludes_idcw" in bases and benchmark_code is not None:
        effective_benchmark = None
        warnings.append(
            "Benchmark-relative metrics (including alpha, beta, tracking error "
            "and information ratio) "
            "are unavailable because verified complete IDCW distribution coverage is missing."
        )
    if any(option in {None, "unknown"} for option in options):
        effective_benchmark = None
        warnings.append(
            "Scheme option metadata is unclassified; benchmark-relative comparison is suppressed."
        )
    if "nav_only_excludes_idcw" in bases:
        warnings.append(
            "Fund returns are NAV-only and exclude IDCW distributions; "
            "do not interpret them as total returns."
        )

    common_dates = set(point.date for point in loaded[codes[0]][0])
    for code in codes[1:]:
        common_dates.intersection_update(point.date for point in loaded[code][0])

    benchmark_prices = None
    if effective_benchmark is not None:
        earliest = max(item[0][0].date for item in loaded.values())
        latest = min(item[0][-1].date for item in loaded.values())
        if earliest > latest:
            raise ValueError("Selected funds have no overlapping date range.")
        benchmark_prices = load_benchmark_prices(
            session, effective_benchmark, earliest, latest, benchmark_source
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
        source_prices, conflicts, basis, coverage_status, coverage_reason = loaded[code]
        aligned_prices = [point for point in source_prices if point.date in date_set]
        aligned_conflicts = tuple(day for day in conflicts if day in date_set)
        reports.append(
            _build_report(
                code,
                aligned_prices,
                aligned_conflicts,
                effective_benchmark,
                benchmark_source,
                aligned_benchmark,
                annual_risk_free_rate,
                periods_per_year,
                calendar_year_as_of_date,
                frequency,
                basis,
                coverage_status,
                coverage_reason,
            )
        )

    return FundComparisonReport(
        scheme_codes=codes,
        observation_count=reports[0].observation_count,
        start_date=reports[0].start_date,
        end_date=reports[0].end_date,
        funds=tuple(reports),
        benchmark_code=effective_benchmark,
        frequency=frequency,
        comparability_warnings=tuple(warnings),
    )
