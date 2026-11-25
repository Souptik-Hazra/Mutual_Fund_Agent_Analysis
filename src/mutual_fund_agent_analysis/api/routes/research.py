"""Portfolio, event, social, and document intelligence APIs."""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.api.schemas.research import (
    DocumentMetadata, EventInput, PortfolioCompareRequest, PortfolioImportRequest,
    SocialPostInput,
)
from mutual_fund_agent_analysis.data.services.research_intelligence import (
    compare_portfolios, create_market_event, create_social_post, extract_pdf_text,
    import_portfolio_snapshot, latest_snapshot, portfolio_history, portfolio_payload,
    search_documents, security_fund_exposure, social_analytics, store_document,
)
from mutual_fund_agent_analysis.database.session import get_db
from mutual_fund_agent_analysis.models import MarketEvent, PortfolioSnapshot
from mutual_fund_agent_analysis.models.research import ResearchDocument

router = APIRouter(tags=["research-intelligence"])


def _domain_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/portfolios/import", status_code=status.HTTP_201_CREATED)
def ingest_portfolio(
    payload: PortfolioImportRequest,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    """Persist one AMC disclosure snapshot; repeat imports with the same hash are idempotent."""
    try:
        snapshot = import_portfolio_snapshot(session, payload)
        return portfolio_payload(session, snapshot)
    except ValueError as exc:
        raise _domain_error(exc) from exc


@router.get("/portfolios/{scheme_code}")
def get_portfolio(
    scheme_code: int,
    session: Annotated[Session, Depends(get_db)],
    as_of: date | None = None,
) -> dict:
    if scheme_code <= 0:
        raise HTTPException(status_code=422, detail="scheme_code must be positive.")
    snapshot = latest_snapshot(session, scheme_code, as_of)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No portfolio disclosure found.")
    return portfolio_payload(session, snapshot)


@router.get("/portfolios/{scheme_code}/history")
def get_portfolio_history(scheme_code: int, session: Annotated[Session, Depends(get_db)]) -> dict:
    if scheme_code <= 0:
        raise HTTPException(status_code=422, detail="scheme_code must be positive.")
    return {"scheme_code": scheme_code, "snapshots": portfolio_history(session, scheme_code)}


@router.get("/portfolios/{scheme_code}/holdings")
def get_portfolio_holdings(
    scheme_code: int,
    session: Annotated[Session, Depends(get_db)],
    as_of: date | None = None,
    asset_class: str | None = Query(default=None, pattern="^(equity|debt|cash|derivative|reit_invit|gold|other)$"),
) -> dict:
    snapshot = latest_snapshot(session, scheme_code, as_of)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No portfolio disclosure found.")
    result = portfolio_payload(session, snapshot)
    if asset_class:
        result["holdings"] = [row for row in result["holdings"] if row["asset_class"] == asset_class]
    return result


@router.get("/portfolios/{scheme_code}/sectors")
def get_portfolio_sectors(
    scheme_code: int, session: Annotated[Session, Depends(get_db)], as_of: date | None = None,
) -> dict:
    snapshot = latest_snapshot(session, scheme_code, as_of)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No portfolio disclosure found.")
    result = portfolio_payload(session, snapshot)
    return {"scheme_code": scheme_code, "effective_date": snapshot.effective_date,
            "sector_allocation": result["sector_allocation"], "asset_allocation": result["asset_allocation"]}


@router.get("/portfolios/{scheme_code}/changes")
def get_portfolio_changes(scheme_code: int, session: Annotated[Session, Depends(get_db)]) -> dict:
    snapshots = session.scalars(select(PortfolioSnapshot).where(
        PortfolioSnapshot.scheme_code == scheme_code
    ).order_by(PortfolioSnapshot.effective_date.desc()).limit(2)).all()
    if len(snapshots) < 2:
        return {"scheme_code": scheme_code, "available": False, "reason": "Two disclosure periods are required."}
    current, previous = snapshots
    from mutual_fund_agent_analysis.models import PortfolioHolding
    old = {r.security_key: r for r in session.scalars(select(PortfolioHolding).where(PortfolioHolding.snapshot_id == previous.snapshot_id))}
    new = {r.security_key: r for r in session.scalars(select(PortfolioHolding).where(PortfolioHolding.snapshot_id == current.snapshot_id))}
    added, removed, changed = [], [], []
    for key in sorted(new.keys() - old.keys()):
        added.append({"security_key": key, "name": new[key].security_name, "weight_pct": new[key].weight_pct})
    for key in sorted(old.keys() - new.keys()):
        removed.append({"security_key": key, "name": old[key].security_name, "weight_pct": old[key].weight_pct})
    for key in sorted(old.keys() & new.keys()):
        before, after = old[key].weight_pct, new[key].weight_pct
        if before != after:
            changed.append({"security_key": key, "name": new[key].security_name,
                            "previous_weight_pct": before, "current_weight_pct": after,
                            "change_percentage_points": (after or 0) - (before or 0)})
    return {"scheme_code": scheme_code, "previous_effective_date": previous.effective_date,
            "current_effective_date": current.effective_date, "added": added, "removed": removed,
            "weight_changes": changed,
            "caveat": "Snapshot differences can reflect issuer naming or classification changes; verify source rows before interpreting as trading activity."}


@router.post("/portfolios/compare")
def compare_selected_portfolios(
    payload: PortfolioCompareRequest, session: Annotated[Session, Depends(get_db)],
) -> dict:
    try:
        return compare_portfolios(session, payload.scheme_codes)
    except ValueError as exc:
        raise _domain_error(exc) from exc


@router.get("/securities/{security_key}/fund-exposure")
def get_security_exposure(security_key: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    return security_fund_exposure(session, security_key)


@router.post("/events", status_code=status.HTTP_201_CREATED)
def ingest_event(payload: EventInput, session: Annotated[Session, Depends(get_db)]) -> dict:
    try:
        row = create_market_event(session, payload)
    except ValueError as exc:
        raise _domain_error(exc) from exc
    return {"event_id": row.event_id, "title": row.title, "status": row.status,
            "event_type": row.event_type, "event_date": row.event_date,
            "published_at": row.published_at, "source_key": row.source_key,
            "evidence_id": row.evidence_id, "canonical_url": row.canonical_url}


@router.get("/events")
def list_events(
    session: Annotated[Session, Depends(get_db)],
    start_date: date | None = None,
    end_date: date | None = None,
    status_filter: str | None = Query(default=None, alias="status", pattern="^(confirmed|scheduled|reported|unverified|speculative|disproved|outdated)$"),
    entity_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be <= end_date.")
    stmt = select(MarketEvent)
    if start_date:
        stmt = stmt.where(MarketEvent.event_date >= start_date)
    if end_date:
        stmt = stmt.where(MarketEvent.event_date <= end_date)
    if status_filter:
        stmt = stmt.where(MarketEvent.status == status_filter)
    if entity_id:
        stmt = stmt.where(MarketEvent.related_entity_id == entity_id)
    rows = session.scalars(stmt.order_by(MarketEvent.event_date.desc().nullslast(), MarketEvent.published_at.desc().nullslast()).limit(limit)).all()
    return {"count": len(rows), "items": [{
        "event_id": r.event_id, "title": r.title, "summary": r.summary,
        "event_type": r.event_type, "status": r.status, "event_date": r.event_date,
        "published_at": r.published_at, "source_key": r.source_key,
        "related_entity_id": r.related_entity_id, "evidence_id": r.evidence_id,
        "canonical_url": r.canonical_url, "confidence": r.confidence,
    } for r in rows]}


@router.post("/social/posts", status_code=status.HTTP_201_CREATED)
def ingest_social_post(payload: SocialPostInput, session: Annotated[Session, Depends(get_db)]) -> dict:
    try:
        row = create_social_post(session, payload)
    except ValueError as exc:
        raise _domain_error(exc) from exc
    return {"post_id": row.post_id, "source_key": row.source_key, "external_id": row.external_id,
            "sentiment_label": row.sentiment_label, "sentiment_score": row.sentiment_score,
            "published_at": row.published_at}


@router.get("/social/analytics")
def get_social_analytics(
    session: Annotated[Session, Depends(get_db)],
    entity_id: int | None = Query(default=None, gt=0),
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be <= end_date.")
    return social_analytics(session, entity_id, start_date, end_date)


@router.post("/documents/upload", status_code=status.HTTP_201_CREATED)
async def upload_research_document(
    session: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
    source_key: str = Form(...),
    title: str = Form(...),
    scheme_code: int | None = Form(default=None),
    related_entity_id: int | None = Form(default=None),
    effective_date: date | None = Form(default=None),
    published_at: str | None = Form(default=None),
) -> dict:
    if file.content_type != "application/pdf" and not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF uploads are supported in this release.")
    content = await file.read(25 * 1024 * 1024 + 1)
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF exceeds the 25 MB upload limit.")
    try:
        extracted, pages = extract_pdf_text(content)
        published = None
        if published_at:
            from datetime import datetime
            published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        document = store_document(
            session, source_key=source_key, title=title, media_type=file.content_type or "application/pdf",
            content=content, extracted_text=extracted, page_count=pages, scheme_code=scheme_code,
            related_entity_id=related_entity_id, effective_date=effective_date,
            published_at=published, original_filename=file.filename,
        )
    except ValueError as exc:
        raise _domain_error(exc) from exc
    return {"document_id": document.document_id, "title": document.title,
            "content_hash": document.content_hash, "page_count": document.page_count,
            "chunk_count": len(document.extracted_text) // 1200 + 1,
            "effective_date": document.effective_date, "source_key": document.source_key}


@router.get("/documents")
def list_documents(
    session: Annotated[Session, Depends(get_db)],
    scheme_code: int | None = Query(default=None, gt=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    stmt = select(ResearchDocument)
    if scheme_code:
        stmt = stmt.where(ResearchDocument.scheme_code == scheme_code)
    rows = session.scalars(stmt.order_by(ResearchDocument.created_at.desc()).limit(limit)).all()
    return {"count": len(rows), "items": [{
        "document_id": d.document_id, "title": d.title, "source_key": d.source_key,
        "scheme_code": d.scheme_code, "effective_date": d.effective_date,
        "published_at": d.published_at, "content_hash": d.content_hash,
        "page_count": d.page_count, "canonical_url": d.canonical_url,
    } for d in rows]}


@router.get("/documents/search")
def search_research_documents(
    q: Annotated[str, Query(min_length=3, max_length=500)],
    session: Annotated[Session, Depends(get_db)],
    scheme_code: int | None = Query(default=None, gt=0),
    limit: int = Query(default=8, ge=1, le=30),
) -> dict:
    try:
        return search_documents(session, q, scheme_code, limit)
    except ValueError as exc:
        raise _domain_error(exc) from exc
