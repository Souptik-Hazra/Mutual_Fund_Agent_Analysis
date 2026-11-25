"""API endpoints for entities, identifiers, source registry, and evidence provenance."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.api.schemas.intelligence import (
    AliasCreateRequest,
    AliasResponse,
    DataSourceResponse,
    EntityCreateRequest,
    EntityEvidenceLinkRequest,
    EntityEvidenceLinkResponse,
    EntityResolveRequest,
    EntityResolveResponse,
    EntityResponse,
    EvidenceCreateRequest,
    EvidenceResponse,
    IdentifierCreateRequest,
    IdentifierResponse,
)
from mutual_fund_agent_analysis.data.services.intelligence import (
    add_entity_alias,
    add_entity_identifier,
    create_entity,
    link_entity_evidence,
    record_evidence,
    resolve_entity,
)
from mutual_fund_agent_analysis.database.session import get_db
from mutual_fund_agent_analysis.models.intelligence import (
    DataSource,
    EntityEvidenceLink,
    EvidenceRecord,
    ResearchEntity,
)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def _commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The requested record conflicts with an existing identity or constraint.",
        ) from exc


def _entity_or_404(session: Session, entity_id: int) -> ResearchEntity:
    entity = session.get(ResearchEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found.")
    return entity


@router.get("/sources", response_model=list[DataSourceResponse])
def list_sources(session: Annotated[Session, Depends(get_db)]):
    rows = session.scalars(
        select(DataSource).order_by(DataSource.authority_tier, DataSource.display_name)
    ).all()
    return [DataSourceResponse.model_validate(row) for row in rows]


@router.post("/entities", response_model=EntityResponse, status_code=status.HTTP_201_CREATED)
def create_entity_endpoint(
    request: EntityCreateRequest, session: Annotated[Session, Depends(get_db)]
):
    try:
        entity = create_entity(
            session, request.entity_type, request.canonical_name, request.description
        )
        _commit(session)
        return EntityResponse.model_validate(entity)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/entities/{entity_id}", response_model=EntityResponse)
def get_entity(entity_id: int, session: Annotated[Session, Depends(get_db)]):
    return EntityResponse.model_validate(_entity_or_404(session, entity_id))


@router.post(
    "/entities/{entity_id}/aliases", response_model=AliasResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_alias_endpoint(
    entity_id: int, request: AliasCreateRequest, session: Annotated[Session, Depends(get_db)]
):
    try:
        record = add_entity_alias(
            session, entity_id, request.alias, request.alias_type, request.source_key,
            request.valid_from, request.valid_to, request.is_primary,
        )
        _commit(session)
        return AliasResponse.model_validate(record)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/entities/{entity_id}/identifiers", response_model=IdentifierResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_identifier_endpoint(
    entity_id: int, request: IdentifierCreateRequest, session: Annotated[Session, Depends(get_db)]
):
    try:
        record = add_entity_identifier(
            session, entity_id, request.namespace, request.identifier_value, request.source_key,
            request.valid_from, request.valid_to, request.is_primary,
        )
        _commit(session)
        return IdentifierResponse.model_validate(record)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/evidence", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
def create_evidence_endpoint(
    request: EvidenceCreateRequest, session: Annotated[Session, Depends(get_db)]
):
    try:
        record = record_evidence(
            session, request.source_key, request.external_id, request.canonical_url,
            request.title, request.published_at, request.retrieved_at, request.effective_from,
            request.effective_to, request.content_hash, request.verification_status,
            request.confidence, request.metadata,
        )
        _commit(session)
        return EvidenceResponse.model_validate(record)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/entities/{entity_id}/evidence/{evidence_id}",
    response_model=EntityEvidenceLinkResponse, status_code=status.HTTP_201_CREATED,
)
def link_evidence_endpoint(
    entity_id: int, evidence_id: int, request: EntityEvidenceLinkRequest,
    session: Annotated[Session, Depends(get_db)],
):
    try:
        record = link_entity_evidence(
            session, entity_id, evidence_id, request.relation_type, request.confidence,
            request.resolution_method, request.verified_at,
        )
        _commit(session)
        return EntityEvidenceLinkResponse.model_validate(record)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/entities/{entity_id}/evidence", response_model=list[EvidenceResponse])
def list_entity_evidence(entity_id: int, session: Annotated[Session, Depends(get_db)]):
    _entity_or_404(session, entity_id)
    rows = session.scalars(
        select(EvidenceRecord)
        .join(EntityEvidenceLink, EntityEvidenceLink.evidence_id == EvidenceRecord.evidence_id)
        .where(EntityEvidenceLink.entity_id == entity_id)
        .order_by(EvidenceRecord.published_at.desc().nullslast(), EvidenceRecord.evidence_id.desc())
    ).all()
    return [EvidenceResponse.model_validate(row) for row in rows]


@router.post("/resolve", response_model=EntityResolveResponse)
def resolve_entity_endpoint(
    request: EntityResolveRequest, session: Annotated[Session, Depends(get_db)]
):
    try:
        result = resolve_entity(
            session, request.entity_type, request.namespace, request.identifier_value,
            request.alias, request.as_of, request.source_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return EntityResolveResponse(
        status=result.status,
        matched_by=result.matched_by,
        entity=EntityResponse.model_validate(result.entity) if result.entity else None,
        candidates=[EntityResponse.model_validate(item) for item in result.candidates],
    )
