"""Fund explorer, scheme discovery, single-fund analysis, and comparison endpoints."""

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.analytics.service import analyze_fund, compare_funds
from mutual_fund_agent_analysis.api.schemas.funds import (
    FundAnalyticsResponse,
    FundComparisonRequest,
    FundComparisonResponse,
    SchemeDetail,
    SchemeDiscoveryResponse,
    SchemePage,
    SchemeSummary,
)
from mutual_fund_agent_analysis.data.providers.mfapi import MFAPIClient
from mutual_fund_agent_analysis.database.session import get_db
from mutual_fund_agent_analysis.models import MutualFundScheme, NavReconciliation

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
    if plan == "direct":
        filters.append(MutualFundScheme.scheme_name.ilike("%DIRECT%"))
    elif plan == "regular":
        filters.append(MutualFundScheme.scheme_name.ilike("%REGULAR%"))
    if option == "growth":
        filters.append(MutualFundScheme.scheme_name.ilike("%GROWTH%"))
    elif option == "idcw":
        filters.append(
            (MutualFundScheme.scheme_name.ilike("%IDCW%"))
            | (MutualFundScheme.scheme_name.ilike("%DIVIDEND%"))
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
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload = _report_payload(report)
    return FundComparisonResponse.model_validate(payload)
