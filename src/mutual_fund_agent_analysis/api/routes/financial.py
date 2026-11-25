"""Financial data quality, scheme metadata history, and IDCW APIs."""

# ruff: noqa: E501

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.analytics.distributions import (
    payout_distribution_index,
    reinvested_distribution_index,
)
from mutual_fund_agent_analysis.api.schemas.financial import (
    CoverageAuditResponse,
    DistributionCoverageAttestationCreate,
    DistributionCoverageAttestationResponse,
    DistributionObservationCreate,
    DistributionObservationResponse,
    IDCWTotalReturnResponse,
    SchemeMetadataObservationCreate,
    SchemeMetadataObservationResponse,
)
from mutual_fund_agent_analysis.database.session import get_db
from mutual_fund_agent_analysis.models import (
    BenchmarkObservation,
    DataSource,
    DistributionCoverageAttestation,
    DistributionObservation,
    DocumentChunk,
    MarketEvent,
    MutualFundScheme,
    NavObservation,
    NavReconciliation,
    PortfolioHolding,
    PortfolioSnapshot,
    ProviderSyncRun,
    ResearchDocument,
    SchemeMetadataObservation,
    SocialPost,
)

router = APIRouter(tags=["financial-reliability"])


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _source_or_422(session: Session, source_key: str) -> DataSource:
    source = session.get(DataSource, source_key)
    if source is None:
        raise HTTPException(
            status_code=422,
            detail=f"Source '{source_key}' is not registered. Register its provenance first.",
        )
    if not source.enabled:
        raise HTTPException(status_code=422, detail="The selected source is disabled.")
    return source


def _validate_source_url(
    source: DataSource,
    source_url: str,
    *,
    require_registered_host: bool = False,
) -> None:
    if not source.base_url:
        if require_registered_host:
            raise HTTPException(
                status_code=422,
                detail="A verified record requires a registered source base_url for host validation.",
            )
        return
    expected = (urlparse(source.base_url).hostname or "").lower()
    actual = (urlparse(source_url).hostname or "").lower()
    if expected and actual and actual != expected and not actual.endswith("." + expected):
        raise HTTPException(
            status_code=422,
            detail="The evidence URL host does not match the registered source host.",
        )


def _scheme_or_404(session: Session, scheme_code: int) -> MutualFundScheme:
    if scheme_code <= 0:
        raise HTTPException(status_code=422, detail="scheme_code must be a positive integer.")
    scheme = session.get(MutualFundScheme, scheme_code)
    if scheme is None:
        raise HTTPException(status_code=404, detail="Scheme not found in the local catalogue.")
    return scheme


@router.get("/audit/coverage", response_model=CoverageAuditResponse)
def get_coverage_audit(
    session: Annotated[Session, Depends(get_db)],
) -> CoverageAuditResponse:
    """Return database row counts, coverage windows, and latest provider-sync time."""

    def count(model: Any) -> int:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)

    nav_range = session.execute(
        select(func.min(NavReconciliation.nav_date), func.max(NavReconciliation.nav_date))
    ).one()
    benchmark_range = session.execute(
        select(
            func.min(BenchmarkObservation.observation_date),
            func.max(BenchmarkObservation.observation_date),
        )
    ).one()
    sync = session.execute(
        select(func.count(ProviderSyncRun.id), func.max(ProviderSyncRun.fetched_at))
    ).one()
    counts = {
        "schemes": count(MutualFundScheme),
        "nav_observations": count(NavObservation),
        "reconciled_nav_dates": count(NavReconciliation),
        "nav_conflicts": int(
            session.scalar(
                select(func.count())
                .select_from(NavReconciliation)
                .where(NavReconciliation.status == "conflict")
            )
            or 0
        ),
        "benchmark_observations": count(BenchmarkObservation),
        "portfolio_snapshots": count(PortfolioSnapshot),
        "portfolio_holdings": count(PortfolioHolding),
        "market_events": count(MarketEvent),
        "social_posts": count(SocialPost),
        "research_documents": count(ResearchDocument),
        "document_chunks": count(DocumentChunk),
        "registered_sources": count(DataSource),
        "scheme_metadata_observations": count(SchemeMetadataObservation),
        "distribution_observations": count(DistributionObservation),
        "distribution_coverage_attestations": count(DistributionCoverageAttestation),
    }
    return CoverageAuditResponse(
        generated_at=datetime.now(UTC),
        counts=counts,
        ranges={
            "reconciled_nav": {
                "first_date": nav_range[0],
                "last_date": nav_range[1],
            },
            "benchmark": {
                "first_date": benchmark_range[0],
                "last_date": benchmark_range[1],
            },
        },
        provider_sync={
            "run_count": int(sync[0] or 0),
            "latest_fetched_at": sync[1],
        },
    )


@router.post(
    "/schemes/{scheme_code}/metadata-observations",
    response_model=SchemeMetadataObservationResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_scheme_metadata_observation(
    scheme_code: int,
    request: SchemeMetadataObservationCreate,
    session: Annotated[Session, Depends(get_db)],
) -> SchemeMetadataObservationResponse:
    """Append a source-attributed metadata observation without erasing its history."""
    scheme = _scheme_or_404(session, scheme_code)
    source = _source_or_422(session, request.source_key)
    source_url = str(request.source_url)
    _validate_source_url(
        source, source_url, require_registered_host=request.verification_status == "verified"
    )
    if request.verification_status == "verified" and not source.is_official:
        raise HTTPException(
            status_code=422,
            detail="Only a registered official source can back verified scheme metadata.",
        )
    payload = request.model_dump(mode="json")
    payload_hash = _hash_payload(payload)
    existing = session.scalar(
        select(SchemeMetadataObservation).where(
            SchemeMetadataObservation.scheme_code == scheme_code,
            SchemeMetadataObservation.source_key == request.source_key,
            SchemeMetadataObservation.content_hash == payload_hash,
        )
    )
    if existing is not None:
        return SchemeMetadataObservationResponse.model_validate(existing)

    record = SchemeMetadataObservation(
        scheme_code=scheme_code,
        source_key=request.source_key,
        source_url=source_url,
        content_hash=payload_hash,
        **request.model_dump(exclude={"source_key", "source_url", "metadata"}),
        metadata_json=request.metadata,
    )
    session.add(record)

    if request.verification_status == "verified":
        if request.plan_type is not None:
            scheme.plan_type = request.plan_type
        if request.option_type is not None:
            scheme.option_type = request.option_type
        if request.lifecycle_type is not None:
            scheme.lifecycle_type = request.lifecycle_type
        if request.launch_date is not None:
            scheme.launch_date = request.launch_date
        if request.closure_date is not None:
            scheme.closure_date = request.closure_date
        if request.expense_ratio is not None:
            scheme.effective_expense_ratio = request.expense_ratio
            scheme.expense_ratio_effective_date = request.expense_ratio_effective_date
            scheme.expense_ratio_source_key = request.source_key
    try:
        session.commit()
        session.refresh(record)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Metadata observation conflicts with an existing record.",
        ) from exc
    return SchemeMetadataObservationResponse.model_validate(record)


@router.get(
    "/schemes/{scheme_code}/metadata-observations",
    response_model=list[SchemeMetadataObservationResponse],
)
def list_scheme_metadata_observations(
    scheme_code: int,
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=250)] = 100,
) -> list[SchemeMetadataObservationResponse]:
    _scheme_or_404(session, scheme_code)
    rows = session.scalars(
        select(SchemeMetadataObservation)
        .where(SchemeMetadataObservation.scheme_code == scheme_code)
        .order_by(
            SchemeMetadataObservation.observed_at.desc(),
            SchemeMetadataObservation.metadata_id.desc(),
        )
        .limit(limit)
    ).all()
    return [SchemeMetadataObservationResponse.model_validate(item) for item in rows]


@router.post(
    "/schemes/{scheme_code}/distributions",
    response_model=DistributionObservationResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_distribution_observation(
    scheme_code: int,
    request: DistributionObservationCreate,
    session: Annotated[Session, Depends(get_db)],
) -> DistributionObservationResponse:
    """Append an IDCW declaration or correction with a stable revision key."""
    _scheme_or_404(session, scheme_code)
    source = _source_or_422(session, request.source_key)
    source_url = str(request.source_url)
    _validate_source_url(
        source, source_url, require_registered_host=request.verification_status == "verified"
    )
    if request.verification_status == "verified" and not source.is_official:
        raise HTTPException(
            status_code=422,
            detail="Only a registered official source can back a verified distribution.",
        )

    previous = None
    if request.supersedes_distribution_id is not None:
        previous = session.get(DistributionObservation, request.supersedes_distribution_id)
        if previous is None or previous.scheme_code != scheme_code:
            raise HTTPException(
                status_code=404,
                detail="The superseded distribution was not found for this scheme.",
            )
        if (
            previous.external_id != request.external_id
            or previous.source_key != request.source_key
            or request.revision <= previous.revision
        ):
            raise HTTPException(
                status_code=422,
                detail="A correction must retain the source/external ID and increase the revision.",
            )
        if previous.status != "active":
            raise HTTPException(
                status_code=409, detail="Only an active distribution can be superseded."
            )

    payload = request.model_dump(mode="json")
    payload_hash = _hash_payload(payload)
    duplicate = session.scalar(
        select(DistributionObservation).where(
            DistributionObservation.scheme_code == scheme_code,
            DistributionObservation.source_key == request.source_key,
            DistributionObservation.external_id == request.external_id,
            DistributionObservation.revision == request.revision,
        )
    )
    if duplicate is not None:
        if duplicate.content_hash != payload_hash:
            raise HTTPException(
                status_code=409,
                detail="The same distribution revision was submitted with different content.",
            )
        return DistributionObservationResponse.model_validate(duplicate)

    record = DistributionObservation(
        scheme_code=scheme_code,
        source_key=request.source_key,
        external_id=request.external_id,
        source_url=source_url,
        content_hash=payload_hash,
        **request.model_dump(exclude={"source_key", "external_id", "source_url", "metadata"}),
        metadata_json=request.metadata,
    )
    if previous is not None:
        previous.status = "revised"
    session.add(record)
    try:
        session.commit()
        session.refresh(record)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Distribution revision conflicts with an existing record.",
        ) from exc
    return DistributionObservationResponse.model_validate(record)


@router.get(
    "/schemes/{scheme_code}/distributions",
    response_model=list[DistributionObservationResponse],
)
def list_distribution_observations(
    scheme_code: int,
    session: Annotated[Session, Depends(get_db)],
    start_date: date | None = None,
    end_date: date | None = None,
    include_superseded: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 250,
) -> list[DistributionObservationResponse]:
    _scheme_or_404(session, scheme_code)
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date.")
    statement = select(DistributionObservation).where(
        DistributionObservation.scheme_code == scheme_code
    )
    if start_date:
        statement = statement.where(DistributionObservation.ex_date >= start_date)
    if end_date:
        statement = statement.where(DistributionObservation.ex_date <= end_date)
    if not include_superseded:
        statement = statement.where(DistributionObservation.status == "active")
    rows = session.scalars(
        statement.order_by(DistributionObservation.ex_date, DistributionObservation.revision).limit(
            limit
        )
    ).all()
    return [DistributionObservationResponse.model_validate(item) for item in rows]


@router.post(
    "/schemes/{scheme_code}/distribution-coverage",
    response_model=DistributionCoverageAttestationResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_distribution_coverage_attestation(
    scheme_code: int,
    request: DistributionCoverageAttestationCreate,
    session: Annotated[Session, Depends(get_db)],
) -> DistributionCoverageAttestationResponse:
    """Persist a scoped source attestation for complete IDCW distribution coverage."""
    _scheme_or_404(session, scheme_code)
    source = _source_or_422(session, request.source_key)
    source_url = str(request.source_url)
    _validate_source_url(
        source, source_url, require_registered_host=request.verification_status == "verified"
    )
    if request.verification_status == "verified" and not source.is_official:
        raise HTTPException(
            status_code=422,
            detail="A verified coverage attestation must reference an official source.",
        )
    payload = request.model_dump(mode="json")
    payload_hash = _hash_payload(payload)
    existing = session.scalar(
        select(DistributionCoverageAttestation).where(
            DistributionCoverageAttestation.scheme_code == scheme_code,
            DistributionCoverageAttestation.source_key == request.source_key,
            DistributionCoverageAttestation.external_id == request.external_id,
            DistributionCoverageAttestation.content_hash == payload_hash,
        )
    )
    if existing is not None:
        return DistributionCoverageAttestationResponse.model_validate(existing)
    record = DistributionCoverageAttestation(
        scheme_code=scheme_code,
        source_key=request.source_key,
        external_id=request.external_id,
        source_url=source_url,
        content_hash=payload_hash,
        **request.model_dump(exclude={"source_key", "external_id", "source_url", "metadata"}),
        metadata_json=request.metadata,
    )
    session.add(record)
    try:
        session.commit()
        session.refresh(record)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Distribution coverage attestation conflicts with an existing record.",
        ) from exc
    return DistributionCoverageAttestationResponse.model_validate(record)


@router.get(
    "/schemes/{scheme_code}/distribution-coverage",
    response_model=list[DistributionCoverageAttestationResponse],
)
def list_distribution_coverage_attestations(
    scheme_code: int,
    session: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[DistributionCoverageAttestationResponse]:
    _scheme_or_404(session, scheme_code)
    rows = session.scalars(
        select(DistributionCoverageAttestation)
        .where(DistributionCoverageAttestation.scheme_code == scheme_code)
        .order_by(DistributionCoverageAttestation.attested_at.desc())
        .limit(limit)
    ).all()
    return [DistributionCoverageAttestationResponse.model_validate(item) for item in rows]


@router.get(
    "/schemes/{scheme_code}/idcw-total-return",
    response_model=IDCWTotalReturnResponse,
)
def get_idcw_total_return(
    scheme_code: int,
    session: Annotated[Session, Depends(get_db)],
    start_date: date,
    end_date: date,
    coverage_attestation_id: int | None = None,
) -> IDCWTotalReturnResponse:
    """Build the option-specific IDCW series only against a verified coverage attestation."""
    scheme = _scheme_or_404(session, scheme_code)
    if start_date >= end_date:
        raise HTTPException(status_code=422, detail="start_date must be earlier than end_date.")

    if scheme.option_type == "idcw_payout":
        return_basis = "idcw_payout_total_return"
        methodology = (
            "Fixed original units; cumulative per-unit cash payouts are added to the "
            "ex-date NAV and are not reinvested or assumed to earn interest."
        )
        index_builder = payout_distribution_index
        limitations = [
            "This scheme-level payout index is pre-tax and assumes payout cash earns no interest.",
            "Investor tax, transaction timing, actual cash use and reinvestment are excluded.",
        ]
    elif scheme.option_type == "idcw_reinvestment":
        return_basis = "idcw_reinvested_total_return"
        methodology = (
            "Base-100 index; ex-date distributions are reinvested at the ex-date NAV "
            "using (NAV + distribution per unit) / prior NAV."
        )
        index_builder = reinvested_distribution_index
        limitations = [
            "This is a scheme-level reinvested distribution index, not an investor-specific post-tax return.",
            "Exit loads, investor tax, transaction timing and reinvestment charges are excluded.",
        ]
    else:
        return_basis = "idcw_reinvested_total_return"
        methodology = "Unavailable: scheme option is not explicitly classified as IDCW payout or reinvestment."
        index_builder = reinvested_distribution_index
        limitations = [
            "The scheme must have a verified IDCW payout or IDCW reinvestment option classification.",
        ]

    def blocked(reason: str) -> IDCWTotalReturnResponse:
        return IDCWTotalReturnResponse(
            scheme_code=scheme_code,
            start_date=start_date,
            end_date=end_date,
            status="blocked_incomplete_coverage",
            return_basis=return_basis,
            methodology=methodology,
            coverage_complete=False,
            coverage_attestation_id=coverage_attestation_id,
            observation_count=0,
            series=[],
            limitations=limitations + [reason],
        )

    if scheme.option_type not in {"idcw_payout", "idcw_reinvestment"}:
        return blocked(
            "Only explicitly classified IDCW payout and IDCW reinvestment options are supported."
        )
    if coverage_attestation_id is None:
        return blocked("A persisted official-source coverage attestation is required.")
    attestation = session.get(DistributionCoverageAttestation, coverage_attestation_id)
    if attestation is None or attestation.scheme_code != scheme_code:
        return blocked("The coverage attestation does not exist for this scheme.")
    coverage_source = session.get(DataSource, attestation.source_key)
    if (
        not attestation.coverage_complete
        or attestation.verification_status != "verified"
        or coverage_source is None
        or not coverage_source.enabled
        or not coverage_source.is_official
        or attestation.start_date > start_date
        or attestation.end_date < end_date
    ):
        return blocked(
            "The attestation must be verified, official, enabled, complete, and cover the full requested interval."
        )

    nav_rows = session.scalars(
        select(NavReconciliation)
        .where(
            NavReconciliation.scheme_code == scheme_code,
            NavReconciliation.nav_date >= start_date,
            NavReconciliation.nav_date <= end_date,
        )
        .order_by(NavReconciliation.nav_date)
    ).all()
    if any(row.status == "conflict" for row in nav_rows):
        raise HTTPException(
            status_code=422,
            detail="NAV conflicts must be resolved before total-return calculation.",
        )
    if len(nav_rows) < 2:
        raise HTTPException(
            status_code=422, detail="At least two reconciled NAV observations are required."
        )

    distribution_rows = session.scalars(
        select(DistributionObservation)
        .where(
            DistributionObservation.scheme_code == scheme_code,
            DistributionObservation.source_key == attestation.source_key,
            DistributionObservation.option_type == scheme.option_type,
            DistributionObservation.ex_date > nav_rows[0].nav_date,
            DistributionObservation.ex_date <= nav_rows[-1].nav_date,
        )
        .order_by(DistributionObservation.ex_date, DistributionObservation.revision)
    ).all()
    active_rows = [item for item in distribution_rows if item.status == "active"]
    distributions: dict[date, Decimal] = {}
    for item in active_rows:
        source = session.get(DataSource, item.source_key)
        if (
            item.verification_status != "verified"
            or source is None
            or not source.enabled
            or not source.is_official
        ):
            return blocked(
                "At least one in-range distribution is not verified against an enabled official source."
            )
        distributions[item.ex_date] = distributions.get(item.ex_date, Decimal("0")) + Decimal(
            item.amount_per_unit
        )

    try:
        points = index_builder(
            [(row.nav_date, Decimal(row.canonical_nav)) for row in nav_rows],
            distributions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return IDCWTotalReturnResponse(
        scheme_code=scheme_code,
        start_date=points[0].date,
        end_date=points[-1].date,
        status="ready",
        return_basis=return_basis,
        methodology=methodology,
        coverage_complete=True,
        coverage_attestation_id=attestation.attestation_id,
        observation_count=len(points),
        series=[
            {
                "date": item.date,
                "nav": item.nav,
                "distribution_per_unit": item.distribution_per_unit,
                "nav_index": item.nav_index,
                "total_return_index": item.total_return_index,
            }
            for item in points
        ],
        limitations=limitations + [
            "Coverage is based on the stored source attestation; the application does not independently discover omitted distributions."
        ],
    )


@router.get("/portfolios/{scheme_code}/quality")
def get_portfolio_quality(
    scheme_code: int,
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Expose missing-weight and unresolved-equity coverage for the latest snapshot."""
    _scheme_or_404(session, scheme_code)
    snapshot = session.scalars(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.scheme_code == scheme_code)
        .order_by(PortfolioSnapshot.effective_date.desc(), PortfolioSnapshot.snapshot_id.desc())
        .limit(1)
    ).first()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No portfolio snapshot is available.")
    holdings = session.scalars(
        select(PortfolioHolding).where(PortfolioHolding.snapshot_id == snapshot.snapshot_id)
    ).all()
    total_weight = sum((Decimal(item.weight_pct or 0) for item in holdings), Decimal("0"))
    equity = [item for item in holdings if item.asset_class == "equity"]
    equity_weight = sum((Decimal(item.weight_pct or 0) for item in equity), Decimal("0"))
    unresolved_weight = sum(
        (
            Decimal(item.weight_pct or 0)
            for item in equity
            if not item.isin and not item.company_entity_id
        ),
        Decimal("0"),
    )
    resolved_equity = max(Decimal("0"), equity_weight - unresolved_weight)
    return {
        "scheme_code": scheme_code,
        "snapshot_id": snapshot.snapshot_id,
        "effective_date": snapshot.effective_date,
        "holding_count": len(holdings),
        "reported_weight_pct": total_weight,
        "equity_weight_pct": equity_weight,
        "unresolved_equity_weight_pct": unresolved_weight,
        "resolved_equity_coverage_pct": (
            resolved_equity / equity_weight * Decimal("100") if equity_weight else None
        ),
        "weight_total_warning": total_weight > Decimal("105") or total_weight < Decimal("95"),
        "methodology_note": (
            "An equity holding is unresolved only when both ISIN and canonical company entity "
            "are absent; non-equity rows are reported separately."
        ),
    }
