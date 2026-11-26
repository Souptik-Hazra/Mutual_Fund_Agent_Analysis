"""Advanced category benchmark, unified fund profile and actual portfolio APIs."""

from dataclasses import asdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.analytics.category_benchmarks import resolve_category_benchmark
from mutual_fund_agent_analysis.analytics.fund_intelligence import analyze_category_peers
from mutual_fund_agent_analysis.analytics.portfolio_intelligence import actual_portfolio_exposure
from mutual_fund_agent_analysis.analytics.service import analyze_fund
from mutual_fund_agent_analysis.data.services.research_intelligence import (
    events_for_fund_exposure,
    latest_snapshot,
    portfolio_payload,
)
from mutual_fund_agent_analysis.database.session import get_db
from mutual_fund_agent_analysis.models.category_benchmark import CategoryBenchmarkMapping
from mutual_fund_agent_analysis.models.scheme import MutualFundScheme

router = APIRouter(prefix="/fund-intelligence", tags=["advanced-fund-intelligence"])


class CategoryBenchmarkCreate(BaseModel):
    scheme_category: str = Field(min_length=2, max_length=250)
    scheme_type: str | None = Field(default=None, max_length=120)
    plan_type: str | None = Field(default=None, max_length=20)
    option_type: str | None = Field(default=None, max_length=30)
    benchmark_code: str = Field(min_length=1, max_length=80)
    benchmark_source: str = Field(default="niftyindices", min_length=1, max_length=40)
    effective_from: date
    effective_to: date | None = None
    source_key: str = Field(min_length=2, max_length=60)
    rationale: str = Field(min_length=10, max_length=1000)


@router.post("/category-benchmarks", status_code=201)
def create_category_benchmark(
    payload: CategoryBenchmarkCreate, session: Annotated[Session, Depends(get_db)]
) -> dict:
    if payload.effective_to and payload.effective_to < payload.effective_from:
        raise HTTPException(status_code=422, detail="effective_to cannot precede effective_from.")
    from mutual_fund_agent_analysis.models.intelligence import DataSource

    source = session.get(DataSource, payload.source_key)
    if (
        source is None
        or not source.enabled
        or not source.is_official
        or source.source_type != "official"
    ):
        raise HTTPException(
            status_code=422,
            detail="source_key must reference an enabled official source.",
        )
    exact = (
        CategoryBenchmarkMapping.scheme_category == payload.scheme_category.strip(),
        CategoryBenchmarkMapping.scheme_type.is_(None)
        if payload.scheme_type is None
        else CategoryBenchmarkMapping.scheme_type == payload.scheme_type,
        CategoryBenchmarkMapping.plan_type.is_(None)
        if payload.plan_type is None
        else CategoryBenchmarkMapping.plan_type == payload.plan_type,
        CategoryBenchmarkMapping.option_type.is_(None)
        if payload.option_type is None
        else CategoryBenchmarkMapping.option_type == payload.option_type,
        CategoryBenchmarkMapping.active.is_(True),
    )
    for row in session.scalars(select(CategoryBenchmarkMapping).where(*exact)).all():
        if payload.effective_from <= (row.effective_to or date.max) and row.effective_from <= (
            payload.effective_to or date.max
        ):
            raise HTTPException(
                status_code=409, detail="An active mapping overlaps this effective date range."
            )
    row = CategoryBenchmarkMapping(
        **payload.model_dump(exclude={"scheme_category"}),
        scheme_category=payload.scheme_category.strip(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return {
        "mapping_id": row.mapping_id,
        "scheme_category": row.scheme_category,
        "scheme_type": row.scheme_type,
        "plan_type": row.plan_type,
        "option_type": row.option_type,
        "benchmark_code": row.benchmark_code,
        "benchmark_source": row.benchmark_source,
        "effective_from": row.effective_from,
        "effective_to": row.effective_to,
        "source_key": row.source_key,
        "rationale": row.rationale,
        "active": row.active,
    }


@router.get("/schemes/{scheme_code}/benchmark")
def get_scheme_benchmark(
    scheme_code: int, session: Annotated[Session, Depends(get_db)], as_of: date | None = None
) -> dict:
    scheme = session.get(MutualFundScheme, scheme_code)
    if scheme is None:
        raise HTTPException(status_code=404, detail="Scheme not found.")
    try:
        mapping = resolve_category_benchmark(session, scheme, as_of)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if mapping is None:
        return {"scheme_code": scheme_code, "availability": "unmapped", "benchmark": None}
    source = session.get(DataSource, mapping.source_key)
    return {
        "scheme_code": scheme_code,
        "availability": "mapped",
        "benchmark": {
            "code": mapping.benchmark_code,
            "source": mapping.benchmark_source,
            "effective_from": mapping.effective_from,
            "effective_to": mapping.effective_to,
            "rationale": mapping.rationale,
            "source_key": mapping.source_key,
            "source_name": source.display_name if source else None,
            "source_is_official": bool(source and source.is_official and source.enabled),
        },
    }


@router.get("/schemes/{scheme_code}/profile")
def fund_research_profile(
    scheme_code: int,
    session: Annotated[Session, Depends(get_db)],
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    scheme = session.get(MutualFundScheme, scheme_code)
    if scheme is None:
        raise HTTPException(status_code=404, detail="Scheme not found.")
    result = {
        "scheme": {
            "scheme_code": scheme.scheme_code,
            "scheme_name": scheme.scheme_name,
            "fund_house": scheme.fund_house,
            "category": scheme.scheme_category,
            "scheme_type": scheme.scheme_type,
            "plan_type": scheme.plan_type,
            "option_type": scheme.option_type,
        },
        "sections": {},
        "generated_for": {"start_date": start_date, "end_date": end_date},
    }
    mapping = None
    try:
        mapping = resolve_category_benchmark(session, scheme, end_date)
        result["sections"]["benchmark_mapping"] = {
            "status": "available" if mapping else "unmapped",
            "benchmark": None
            if mapping is None
            else {
                "code": mapping.benchmark_code,
                "source": mapping.benchmark_source,
                "effective_from": mapping.effective_from,
                "effective_to": mapping.effective_to,
                "rationale": mapping.rationale,
                "source_key": mapping.source_key,
                "source_name": (
                    session.get(DataSource, mapping.source_key).display_name
                    if session.get(DataSource, mapping.source_key) else None
                ),
            },
        }
    except ValueError as exc:
        result["sections"]["benchmark_mapping"] = {"status": "ambiguous", "reason": str(exc)}
    try:
        report = analyze_fund(
            session,
            scheme_code,
            benchmark_code=mapping.benchmark_code if mapping else None,
            benchmark_source=mapping.benchmark_source if mapping else "niftyindices",
            start_date=start_date,
            end_date=end_date,
        )
        result["sections"]["performance_and_risk"] = {"status": "available", "data": asdict(report)}
    except ValueError as exc:
        result["sections"]["performance_and_risk"] = {"status": "unavailable", "reason": str(exc)}
    try:
        category = analyze_category_peers(
            session,
            scheme_code,
            start_date,
            end_date,
            benchmark_code=mapping.benchmark_code if mapping else None,
            benchmark_source=mapping.benchmark_source if mapping else "niftyindices",
        )
        result["sections"]["category_position"] = {"status": "available", "data": category}
    except ValueError as exc:
        result["sections"]["category_position"] = {"status": "unavailable", "reason": str(exc)}
    snapshot = latest_snapshot(session, scheme_code, end_date)
    result["sections"]["portfolio_disclosure"] = (
        {"status": "available", "data": portfolio_payload(session, snapshot)}
        if snapshot
        else {"status": "unavailable", "reason": "No portfolio disclosure is stored."}
    )
    events = events_for_fund_exposure(session, scheme_code, start_date, end_date, 30)
    result["sections"]["market_events"] = {
        "status": "available" if events.get("events") else "unavailable",
        "data": events,
        "limitation": (
            "Only locally stored fund-linked events are included; no live news fetch is implied."
        ),
    }
    result["limitations"] = [
        "NAV-only return metrics exclude IDCW distributions unless "
        "distribution-aware series are available.",
        "Portfolio holdings are dated AMC disclosures, not real-time positions.",
        "Missing sources or incomplete records are reported as unavailable rather than estimated.",
    ]
    return result


@router.get("/portfolio/actual-exposure")
def get_actual_portfolio_exposure(
    session: Annotated[Session, Depends(get_db)],
    scheme_codes: Annotated[list[int], Query(min_length=1, max_length=20)],
) -> dict:
    try:
        return actual_portfolio_exposure(session, scheme_codes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
