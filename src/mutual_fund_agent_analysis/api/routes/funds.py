"""Fund explorer, scheme discovery, single-fund analysis, and comparison endpoints."""

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.analytics.active_risk import calculate_active_risk_metrics
from mutual_fund_agent_analysis.analytics.investor import (
    InvestorTransactionInput,
    calculate_investor_returns,
)
from mutual_fund_agent_analysis.analytics.series import period_returns
from mutual_fund_agent_analysis.analytics.service import (
    analyze_fund,
    compare_funds,
    load_benchmark_prices,
    load_fund_prices,
    load_fund_return_prices,
)
from mutual_fund_agent_analysis.analytics.sip import simulate_monthly_sip
from mutual_fund_agent_analysis.api.schemas.funds import (
    FundAnalyticsResponse,
    FundComparisonRequest,
    FundComparisonResponse,
    SchemeDetail,
    SchemeDiscoveryResponse,
    SchemePage,
    SchemeSummary,
)
from mutual_fund_agent_analysis.api.schemas.investor import (
    ActiveRiskResponse,
    InvestorReturnsResponse,
    InvestorTransactionCreate,
    InvestorTransactionResponse,
    SipSimulationRequest,
    SipSimulationResponse,
)
from mutual_fund_agent_analysis.data.providers.mfapi import MFAPIClient
from mutual_fund_agent_analysis.data.services.nav_sync import sync_scheme_nav
from mutual_fund_agent_analysis.database.session import get_db
from mutual_fund_agent_analysis.models import (
    InvestorTransaction,
    MutualFundScheme,
    NavReconciliation,
)

router = APIRouter(tags=["funds"])


def _validate_scheme_code(scheme_code: int) -> None:
    if scheme_code <= 0:
        raise HTTPException(status_code=422, detail="scheme_code must be a positive integer.")


def _report_payload(report: object) -> dict:
    return asdict(report)


@router.get("/schemes/discover", response_model=SchemeDiscoveryResponse)
def discover_schemes(
    q: Annotated[str, Query(min_length=2, max_length=120)],
) -> SchemeDiscoveryResponse:
    """Search the upstream MFAPI scheme directory without writing to the database."""
    normalized = q.strip()
    if len(normalized) < 2:
        raise HTTPException(
            status_code=422,
            detail="Search query must contain at least two characters.",
        )
    try:
        with MFAPIClient() as client:
            items = client.search_schemes(normalized)
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Scheme discovery provider is unavailable or returned invalid data.",
        ) from exc
    return SchemeDiscoveryResponse(
        query=normalized,
        count=len(items),
        items=[
            {"scheme_code": item.scheme_code, "scheme_name": item.scheme_name} for item in items
        ],
    )


@router.get("/schemes", response_model=SchemePage)
def list_schemes(
    session: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(min_length=2, max_length=120)] = None,
    fund_house: Annotated[str | None, Query(min_length=1, max_length=250)] = None,
    category: Annotated[str | None, Query(min_length=1, max_length=250)] = None,
    scheme_type: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    plan: Annotated[str | None, Query(pattern="^(direct|regular)$")] = None,
    option: Annotated[str | None, Query(pattern="^(growth|idcw)$")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SchemePage:
    """List locally ingested schemes with stable pagination and metadata filters."""
    statement = select(MutualFundScheme)
    count_statement = select(func.count()).select_from(MutualFundScheme)
    filters = []
    if q:
        normalized_query = q.strip()
        if len(normalized_query) < 2:
            raise HTTPException(
                status_code=422,
                detail="Search query must contain at least two characters.",
            )
        pattern = f"%{normalized_query}%"
        filters.append(
            or_(
                MutualFundScheme.scheme_name.ilike(pattern),
                cast(MutualFundScheme.scheme_code, String).ilike(pattern),
                MutualFundScheme.isin_growth.ilike(pattern),
                MutualFundScheme.isin_div_reinvestment.ilike(pattern),
            )
        )
    if fund_house:
        filters.append(MutualFundScheme.fund_house.ilike(f"%{fund_house.strip()}%"))
    if category:
        filters.append(MutualFundScheme.scheme_category.ilike(f"%{category.strip()}%"))
    if scheme_type:
        filters.append(MutualFundScheme.scheme_type.ilike(f"%{scheme_type.strip()}%"))
    if plan:
        filters.append(MutualFundScheme.plan_type == plan)
    if option == "growth":
        filters.append(MutualFundScheme.option_type == "growth")
    elif option == "idcw":
        filters.append(
            MutualFundScheme.option_type.in_(["idcw_payout", "idcw_reinvestment", "idcw_transfer"])
        )
    for condition in filters:
        statement = statement.where(condition)
        count_statement = count_statement.where(condition)

    total = session.scalar(count_statement) or 0
    rows = session.scalars(
        statement.order_by(MutualFundScheme.scheme_name, MutualFundScheme.scheme_code)
        .limit(limit)
        .offset(offset)
    ).all()
    return SchemePage(
        items=[SchemeSummary.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/schemes/{scheme_code}", response_model=SchemeDetail)
def get_scheme(
    scheme_code: int,
    session: Annotated[Session, Depends(get_db)],
) -> SchemeDetail:
    """Return cached scheme metadata and its latest reconciled NAV."""
    _validate_scheme_code(scheme_code)
    scheme = session.get(MutualFundScheme, scheme_code)
    if scheme is None:
        raise HTTPException(status_code=404, detail="Scheme not found in the local catalogue.")
    latest = session.scalars(
        select(NavReconciliation)
        .where(NavReconciliation.scheme_code == scheme_code)
        .order_by(NavReconciliation.nav_date.desc())
        .limit(1)
    ).first()
    payload = SchemeSummary.model_validate(scheme).model_dump()
    if latest is not None:
        payload.update(
            latest_nav=Decimal(latest.canonical_nav),
            latest_nav_date=latest.nav_date,
            reconciliation_status=latest.status,
            latest_canonical_source=latest.canonical_source,
        )
    return SchemeDetail.model_validate(payload)


@router.post("/schemes/{scheme_code}/sync-nav")
def sync_scheme_nav_on_demand(
    scheme_code: int,
    session: Annotated[Session, Depends(get_db)],
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """Fetch NAV history when no observations cover the requested analysis window."""
    _validate_scheme_code(scheme_code)
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date.")
    if session.get(MutualFundScheme, scheme_code) is None:
        raise HTTPException(status_code=404, detail="Scheme not found in the local catalogue.")

    coverage_statement = (
        select(func.count())
        .select_from(NavReconciliation)
        .where(NavReconciliation.scheme_code == scheme_code)
    )
    if start_date is not None:
        coverage_statement = coverage_statement.where(NavReconciliation.nav_date >= start_date)
    if end_date is not None:
        coverage_statement = coverage_statement.where(NavReconciliation.nav_date <= end_date)
    existing_count = session.scalar(coverage_statement) or 0
    if existing_count:
        return {
            "scheme_code": scheme_code,
            "synced": False,
            "observation_count": existing_count,
            "requested_start_date": start_date,
            "requested_end_date": end_date,
            "message": "NAV observations already exist within the requested date window.",
        }

    try:
        processed = sync_scheme_nav(session, scheme_code, start_date, end_date)
        session.commit()
    except (httpx.HTTPError, ValueError) as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to retrieve valid NAV history from MFAPI: {exc}",
        ) from exc
    except Exception:
        session.rollback()
        raise

    if processed < 2:
        raise HTTPException(
            status_code=422,
            detail=(
                "The provider returned fewer than two NAV observations; "
                "analytics cannot be calculated."
            ),
        )
    return {
        "scheme_code": scheme_code,
        "synced": True,
        "observation_count": processed,
        "requested_start_date": start_date,
        "requested_end_date": end_date,
        "message": "NAV history fetched and reconciled successfully.",
    }


@router.get("/schemes/{scheme_code}/analytics", response_model=FundAnalyticsResponse)
def get_fund_analytics(
    scheme_code: int,
    session: Annotated[Session, Depends(get_db)],
    start_date: date | None = None,
    end_date: date | None = None,
    benchmark_code: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    annual_risk_free_rate: Annotated[Decimal, Query(ge=Decimal("-1"))] = Decimal("0"),
    periods_per_year: Annotated[int, Query(ge=1, le=366)] = 252,
    benchmark_source: Annotated[str, Query(min_length=1, max_length=40)] = "niftyindices",
    allow_nav_conflicts: bool = False,
    calendar_year_as_of_date: date | None = None,
    frequency: Literal["daily", "weekly", "monthly", "quarterly", "yearly"] = "daily",
) -> FundAnalyticsResponse:
    """Calculate one fund's metrics from reconciled NAV and optional benchmark TRI."""
    _validate_scheme_code(scheme_code)
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date.")
    if annual_risk_free_rate <= Decimal("-1"):
        raise HTTPException(
            status_code=422,
            detail="annual_risk_free_rate must be greater than -1.",
        )
    try:
        report = analyze_fund(
            session,
            scheme_code,
            benchmark_code,
            start_date,
            end_date,
            annual_risk_free_rate,
            periods_per_year,
            benchmark_source,
            allow_nav_conflicts,
            calendar_year_as_of_date,
            frequency,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FundAnalyticsResponse.model_validate(_report_payload(report))


@router.post("/schemes/compare", response_model=FundComparisonResponse)
def compare_selected_funds(
    request: FundComparisonRequest,
    session: Annotated[Session, Depends(get_db)],
) -> FundComparisonResponse:
    """Compare up to five funds on the exact shared NAV/benchmark observation dates."""
    try:
        report = compare_funds(
            session,
            request.scheme_codes,
            request.benchmark_code,
            request.start_date,
            request.end_date,
            request.annual_risk_free_rate,
            request.periods_per_year,
            request.benchmark_source,
            request.allow_nav_conflicts,
            request.calendar_year_as_of_date,
            request.frequency,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload = _report_payload(report)
    return FundComparisonResponse.model_validate(payload)


@router.post(
    "/schemes/{scheme_code}/sip-simulation",
    response_model=SipSimulationResponse,
)
def run_sip_simulation(
    scheme_code: int,
    request: SipSimulationRequest,
    session: Annotated[Session, Depends(get_db)],
) -> SipSimulationResponse:
    """Simulate hypothetical SIP instalments using exact reconciled NAV dates."""
    _validate_scheme_code(scheme_code)
    if session.get(MutualFundScheme, scheme_code) is None:
        raise HTTPException(status_code=404, detail="Scheme not found in the local catalogue.")
    try:
        prices, _ = load_fund_prices(
            session, scheme_code, request.start_date, request.valuation_date
        )
        result = simulate_monthly_sip(
            prices,
            request.start_date,
            request.end_date,
            request.monthly_amount,
            request.valuation_date,
            request.day_of_month,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SipSimulationResponse.model_validate({"scheme_code": scheme_code, **asdict(result)})


@router.get(
    "/schemes/{scheme_code}/transactions",
    response_model=list[InvestorTransactionResponse],
)
def list_investor_transactions(
    scheme_code: int,
    session: Annotated[Session, Depends(get_db)],
    start_date: date | None = None,
    end_date: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[InvestorTransactionResponse]:
    """List the local transaction ledger for a single scheme."""
    _validate_scheme_code(scheme_code)
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date.")
    if session.get(MutualFundScheme, scheme_code) is None:
        raise HTTPException(status_code=404, detail="Scheme not found in the local catalogue.")
    statement = select(InvestorTransaction).where(InvestorTransaction.scheme_code == scheme_code)
    if start_date:
        statement = statement.where(InvestorTransaction.transaction_date >= start_date)
    if end_date:
        statement = statement.where(InvestorTransaction.transaction_date <= end_date)
    rows = session.scalars(
        statement.order_by(
            InvestorTransaction.transaction_date,
            InvestorTransaction.transaction_id,
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return [InvestorTransactionResponse.model_validate(row) for row in rows]


@router.post(
    "/schemes/{scheme_code}/transactions",
    response_model=InvestorTransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_investor_transaction(
    scheme_code: int,
    request: InvestorTransactionCreate,
    session: Annotated[Session, Depends(get_db)],
) -> InvestorTransactionResponse:
    """Append one validated transaction to the personal investor ledger."""
    _validate_scheme_code(scheme_code)
    if session.get(MutualFundScheme, scheme_code) is None:
        raise HTTPException(status_code=404, detail="Scheme not found in the local catalogue.")
    record = InvestorTransaction(scheme_code=scheme_code, **request.model_dump())
    session.add(record)
    try:
        session.commit()
        session.refresh(record)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="The transaction conflicts with an existing reference or database constraint.",
        ) from exc
    return InvestorTransactionResponse.model_validate(record)


@router.delete(
    "/transactions/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_investor_transaction(
    transaction_id: int,
    session: Annotated[Session, Depends(get_db)],
) -> Response:
    """Delete an incorrect manually entered ledger row."""
    record = session.get(InvestorTransaction, transaction_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Investor transaction not found.")
    session.delete(record)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/schemes/{scheme_code}/investor-returns",
    response_model=InvestorReturnsResponse,
)
def get_investor_returns(
    scheme_code: int,
    session: Annotated[Session, Depends(get_db)],
    as_of_date: date | None = None,
) -> InvestorReturnsResponse:
    """Calculate actual ledger XIRR and open-unit valuation at an exact reconciled NAV date."""
    _validate_scheme_code(scheme_code)
    if session.get(MutualFundScheme, scheme_code) is None:
        raise HTTPException(status_code=404, detail="Scheme not found in the local catalogue.")
    nav_statement = select(NavReconciliation).where(NavReconciliation.scheme_code == scheme_code)
    if as_of_date is not None:
        nav_statement = nav_statement.where(NavReconciliation.nav_date == as_of_date)
    latest = session.scalars(
        nav_statement.order_by(NavReconciliation.nav_date.desc()).limit(1)
    ).first()
    if latest is None:
        raise HTTPException(
            status_code=422,
            detail="No exact reconciled NAV is available for the requested valuation date.",
        )
    if latest.status == "conflict":
        raise HTTPException(
            status_code=422,
            detail="The valuation NAV is conflicted and cannot be used for investor returns.",
        )

    records = session.scalars(
        select(InvestorTransaction)
        .where(
            InvestorTransaction.scheme_code == scheme_code,
            InvestorTransaction.transaction_date <= latest.nav_date,
        )
        .order_by(InvestorTransaction.transaction_date, InvestorTransaction.transaction_id)
    ).all()
    inputs = [
        InvestorTransactionInput(
            transaction_date=item.transaction_date,
            transaction_type=item.transaction_type,
            amount=Decimal(item.amount),
            units=Decimal(item.units) if item.units is not None else None,
        )
        for item in records
    ]
    try:
        report = calculate_investor_returns(inputs, latest.nav_date, Decimal(latest.canonical_nav))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return InvestorReturnsResponse.model_validate({"scheme_code": scheme_code, **asdict(report)})


@router.get(
    "/schemes/{scheme_code}/active-risk",
    response_model=ActiveRiskResponse,
)
def get_active_risk(
    scheme_code: int,
    benchmark_code: Annotated[str, Query(min_length=1, max_length=80)],
    session: Annotated[Session, Depends(get_db)],
    start_date: date,
    end_date: date,
    periods_per_year: Annotated[int, Query(ge=1, le=366)] = 252,
    benchmark_source: Annotated[str, Query(min_length=1, max_length=40)] = "niftyindices",
) -> ActiveRiskResponse:
    """Calculate tracking error and information ratio over exact aligned return intervals."""
    _validate_scheme_code(scheme_code)
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date.")
    try:
        prices, _, return_basis, coverage_status, coverage_reason = load_fund_return_prices(
            session, scheme_code, start_date, end_date
        )
        if return_basis == "nav_only_excludes_idcw":
            raise ValueError(
                coverage_reason
                or "Verified IDCW total-return coverage is required for tracking "
                "error and information ratio."
            )
        benchmark_prices = load_benchmark_prices(
            session, benchmark_code, start_date, end_date, benchmark_source
        )
        metrics = calculate_active_risk_metrics(
            period_returns(prices), period_returns(benchmark_prices), periods_per_year
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ActiveRiskResponse(
        scheme_code=scheme_code,
        benchmark_code=benchmark_code,
        start_date=start_date,
        end_date=end_date,
        periods_per_year=periods_per_year,
        aligned_observation_count=metrics.aligned_observation_count,
        tracking_error=metrics.tracking_error,
        information_ratio=metrics.information_ratio,
        mean_active_return=metrics.mean_active_return,
        coverage_ratio=metrics.coverage_ratio,
        fund_return_basis=return_basis,
        benchmark_return_basis="tri",
    )
