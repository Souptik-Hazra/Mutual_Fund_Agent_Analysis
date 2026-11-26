"""Deterministic entity resolution and source-evidence registry services."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import urlparse

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.models.intelligence import (
    DataSource,
    EntityAlias,
    EntityEvidenceLink,
    EntityIdentifier,
    EntityRelationship,
    EvidenceRecord,
    ResearchEntity,
)

ENTITY_TYPES = {
    "amc", "scheme", "company", "security", "sector", "benchmark",
    "index", "person", "event", "regulator", "other",
}
VERIFICATION_STATUSES = {"unverified", "corroborated", "verified", "disputed", "retracted"}
RESOLUTION_METHODS = {"identifier", "exact_alias", "manual", "model_reviewed"}


@dataclass(frozen=True)
class EntityResolution:
    """Result of deterministic identity matching; ambiguous aliases are never auto-selected."""

    status: str
    entity: ResearchEntity | None
    matched_by: str | None
    candidates: tuple[ResearchEntity, ...] = ()


def normalize_name(value: str) -> str:
    """Normalize Unicode and whitespace while retaining meaningful punctuation."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Name must be a non-empty string.")
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def normalize_identifier(value: str) -> str:
    """Normalize an external identifier without deleting significant punctuation."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Identifier value must be a non-empty string.")
    return "".join(unicodedata.normalize("NFKC", value).upper().split())


def _validate_date_range(valid_from: date | None, valid_to: date | None) -> None:
    if valid_from and valid_to and valid_to < valid_from:
        raise ValueError("valid_to must be on or after valid_from.")


def _validate_aware_datetime(value: datetime | None, field_name: str) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{field_name} must include a timezone offset.")


def _require_entity(session: Session, entity_id: int) -> ResearchEntity:
    entity = session.get(ResearchEntity, entity_id)
    if entity is None:
        raise ValueError(f"Entity {entity_id} does not exist.")
    if entity.status != "active":
        raise ValueError(
            "Aliases, identifiers, and evidence can only be linked to active entities."
        )
    return entity


def create_entity(
    session: Session, entity_type: str, canonical_name: str, description: str | None = None
) -> ResearchEntity:
    """Create or return a canonical entity by type and normalized name."""
    normalized_type = entity_type.strip().lower()
    if normalized_type not in ENTITY_TYPES:
        raise ValueError(f"Unsupported entity_type: {entity_type!r}.")
    normalized_name = normalize_name(canonical_name)
    existing = session.scalar(
        select(ResearchEntity).where(
            ResearchEntity.entity_type == normalized_type,
            ResearchEntity.normalized_name == normalized_name,
        )
    )
    if existing:
        if description and not existing.description:
            existing.description = description.strip()
        return existing
    entity = ResearchEntity(
        entity_type=normalized_type,
        canonical_name=" ".join(canonical_name.split()),
        normalized_name=normalized_name,
        description=description.strip() if description else None,
        status="active",
    )
    # A concurrent request may create the same canonical entity after the
    # lookup above. Isolate the insert in a savepoint so a unique-key race
    # does not poison the caller's transaction.
    try:
        with session.begin_nested():
            session.add(entity)
            session.flush()
        return entity
    except IntegrityError:
        existing = session.scalar(
            select(ResearchEntity).where(
                ResearchEntity.entity_type == normalized_type,
                ResearchEntity.normalized_name == normalized_name,
            )
        )
        if existing is None:
            raise
        if description and not existing.description:
            existing.description = description.strip()
        return existing


def add_entity_alias(
    session: Session,
    entity_id: int,
    alias: str,
    alias_type: str = "common",
    source_key: str | None = None,
    valid_from: date | None = None,
    valid_to: date | None = None,
    is_primary: bool = False,
) -> EntityAlias:
    """Add an alias; duplicate names across different entities remain explicitly ambiguous."""
    entity = _require_entity(session, entity_id)
    _validate_date_range(valid_from, valid_to)
    normalized = normalize_name(alias)
    normalized_alias_type = alias_type.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,29}", normalized_alias_type):
        raise ValueError("alias_type must be a 1–30 character lowercase identifier.")
    if source_key and session.get(DataSource, source_key) is None:
        raise ValueError(f"Unknown source_key: {source_key!r}.")
    if is_primary:
        session.query(EntityAlias).filter(
            EntityAlias.entity_id == entity_id, EntityAlias.is_primary.is_(True)
        ).update({"is_primary": False}, synchronize_session="fetch")
    existing = session.scalar(
        select(EntityAlias).where(
            EntityAlias.entity_id == entity_id,
            EntityAlias.normalized_alias == normalized,
            EntityAlias.valid_from.is_not_distinct_from(valid_from),
        )
    )
    if existing:
        existing.alias = alias.strip()
        existing.alias_type = normalized_alias_type
        existing.source_key = source_key
        existing.valid_to = valid_to
        existing.is_primary = is_primary
        return existing
    record = EntityAlias(
        entity_id=entity.entity_id, alias=alias.strip(), normalized_alias=normalized,
        alias_type=normalized_alias_type, source_key=source_key, valid_from=valid_from,
        valid_to=valid_to, is_primary=is_primary,
    )
    session.add(record)
    session.flush()
    return record


def add_entity_identifier(
    session: Session,
    entity_id: int,
    namespace: str,
    identifier_value: str,
    source_key: str | None = None,
    valid_from: date | None = None,
    valid_to: date | None = None,
    is_primary: bool = False,
) -> EntityIdentifier:
    """Register a globally unique identifier within its explicit namespace."""
    entity = _require_entity(session, entity_id)
    _validate_date_range(valid_from, valid_to)
    normalized_namespace = namespace.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_.:-]{1,59}", normalized_namespace):
        raise ValueError("namespace must be a 2–60 character identifier namespace.")
    normalized_value = normalize_identifier(identifier_value)
    if len(normalized_value) > 160:
        raise ValueError("identifier_value must not exceed 160 normalized characters.")
    if source_key and session.get(DataSource, source_key) is None:
        raise ValueError(f"Unknown source_key: {source_key!r}.")
    if is_primary:
        session.query(EntityIdentifier).filter(
            EntityIdentifier.entity_id == entity_id,
            EntityIdentifier.namespace == normalized_namespace,
            EntityIdentifier.is_primary.is_(True),
        ).update({"is_primary": False}, synchronize_session="fetch")
    existing = session.scalar(
        select(EntityIdentifier).where(
            EntityIdentifier.namespace == normalized_namespace,
            EntityIdentifier.normalized_value == normalized_value,
        )
    )
    if existing:
        if existing.entity_id != entity_id:
            raise ValueError(
                f"{normalized_namespace}:{normalized_value} is already assigned to another entity."
            )
        existing.identifier_value = identifier_value.strip()
        existing.source_key = source_key
        existing.valid_from = valid_from
        existing.valid_to = valid_to
        existing.is_primary = is_primary
        return existing
    record = EntityIdentifier(
        entity_id=entity.entity_id, namespace=normalized_namespace,
        identifier_value=identifier_value.strip(), normalized_value=normalized_value,
        source_key=source_key, valid_from=valid_from, valid_to=valid_to, is_primary=is_primary,
    )
    session.add(record)
    session.flush()
    return record


def record_evidence(
    session: Session,
    source_key: str,
    external_id: str | None = None,
    canonical_url: str | None = None,
    title: str | None = None,
    published_at: datetime | None = None,
    retrieved_at: datetime | None = None,
    effective_from: date | None = None,
    effective_to: date | None = None,
    content_hash: str | None = None,
    verification_status: str = "unverified",
    confidence: Decimal | None = None,
    metadata: dict | None = None,
) -> EvidenceRecord:
    """Create or refresh a source reference while preserving its provenance fields."""
    source = session.get(DataSource, source_key)
    if source is None:
        raise ValueError(f"Unknown source_key: {source_key!r}.")
    if not source.enabled:
        raise ValueError(f"Source {source_key!r} is disabled.")
    if verification_status not in VERIFICATION_STATUSES:
        raise ValueError("Unsupported verification_status.")
    if verification_status == "verified" and (
        not source.is_official or source.source_type != "official"
    ):
        raise ValueError("Verified evidence requires an enabled registered official source.")
    _validate_aware_datetime(published_at, "published_at")
    _validate_aware_datetime(retrieved_at, "retrieved_at")
    if external_id is not None and not external_id.strip():
        raise ValueError("external_id cannot be blank.")
    if effective_from and effective_to and effective_to < effective_from:
        raise ValueError("effective_to must be on or after effective_from.")
    if confidence is not None and (
        not confidence.is_finite() or confidence < 0 or confidence > 1
    ):
        raise ValueError("confidence must be between 0 and 1.")
    if canonical_url:
        parsed = urlparse(canonical_url)
        allowed_schemes = {"https"} if verification_status == "verified" else {"http", "https"}
        if (
            parsed.scheme not in allowed_schemes
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("canonical_url must be an absolute HTTPS URL without credentials when verified.")
        if verification_status == "verified" and source.base_url:
            registered = urlparse(source.base_url)
            try:
                actual_port = parsed.port or 443
                registered_port = registered.port or 443
            except ValueError as exc:
                raise ValueError("canonical_url or registered source has an invalid port.") from exc
            actual_host = (parsed.hostname or "").lower().rstrip(".")
            registered_host = (registered.hostname or "").lower().rstrip(".")
            if (
                registered.scheme != "https"
                or actual_port != registered_port
                or not (
                    actual_host == registered_host
                    or actual_host.endswith("." + registered_host)
                )
            ):
                raise ValueError("Verified evidence URL must match the registered official source host.")
    if content_hash and not re.fullmatch(r"[a-fA-F0-9]{32,128}", content_hash):
        raise ValueError("content_hash must be a hexadecimal digest between 32 and 128 characters.")
    existing = None
    if external_id:
        existing = session.scalar(
            select(EvidenceRecord).where(
                EvidenceRecord.source_key == source_key,
                EvidenceRecord.external_id == external_id.strip(),
            )
        )
    values = {
        "canonical_url": canonical_url,
        "title": title.strip() if title else None,
        "published_at": published_at,
        "retrieved_at": retrieved_at or datetime.now(UTC),
        "effective_from": effective_from,
        "effective_to": effective_to,
        "content_hash": content_hash.lower() if content_hash else None,
        "verification_status": verification_status,
        "confidence": confidence,
        "metadata_json": metadata or {},
    }
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        return existing
    record = EvidenceRecord(
        source_key=source_key, external_id=external_id.strip() if external_id else None, **values
    )
    session.add(record)
    session.flush()
    return record


def link_entity_evidence(
    session: Session,
    entity_id: int,
    evidence_id: int,
    relation_type: str = "mentions",
    confidence: Decimal | None = None,
    resolution_method: str = "manual",
    verified_at: datetime | None = None,
) -> EntityEvidenceLink:
    """Attach evidence to an entity with an auditable relation and resolution method."""
    _require_entity(session, entity_id)
    if session.get(EvidenceRecord, evidence_id) is None:
        raise ValueError(f"Evidence {evidence_id} does not exist.")
    if resolution_method not in RESOLUTION_METHODS:
        raise ValueError("Unsupported resolution_method.")
    _validate_aware_datetime(verified_at, "verified_at")
    normalized_relation = relation_type.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", normalized_relation):
        raise ValueError("relation_type must be a 1–40 character lowercase identifier.")
    if confidence is not None and (
        not confidence.is_finite() or confidence < 0 or confidence > 1
    ):
        raise ValueError("confidence must be between 0 and 1.")
    link = session.get(EntityEvidenceLink, (entity_id, evidence_id))
    if link is None:
        link = EntityEvidenceLink(
            entity_id=entity_id, evidence_id=evidence_id,
            relation_type=normalized_relation, confidence=confidence,
            resolution_method=resolution_method, verified_at=verified_at,
        )
        session.add(link)
    else:
        link.relation_type = normalized_relation
        link.confidence = confidence
        link.resolution_method = resolution_method
        link.verified_at = verified_at
    session.flush()
    return link


def resolve_entity(
    session: Session,
    entity_type: str | None = None,
    namespace: str | None = None,
    identifier_value: str | None = None,
    alias: str | None = None,
    as_of: date | None = None,
    source_key: str | None = None,
) -> EntityResolution:
    """Resolve exact identifiers first, then exact aliases; never fuzzy-match identities."""
    normalized_type = entity_type.strip().lower() if entity_type else None
    if normalized_type and normalized_type not in ENTITY_TYPES:
        raise ValueError(f"Unsupported entity_type: {entity_type!r}.")
    if bool(namespace) != bool(identifier_value):
        raise ValueError("namespace and identifier_value must be supplied together.")
    if not namespace and not alias:
        raise ValueError("Provide an identifier or an alias to resolve.")
    if source_key and session.get(DataSource, source_key) is None:
        raise ValueError(f"Unknown source_key: {source_key!r}.")
    effective_date = as_of or datetime.now(UTC).date()
    if namespace and identifier_value:
        statement = (
            select(ResearchEntity)
            .join(EntityIdentifier, EntityIdentifier.entity_id == ResearchEntity.entity_id)
            .where(
                EntityIdentifier.namespace == namespace.strip().upper(),
                EntityIdentifier.normalized_value == normalize_identifier(identifier_value),
                ResearchEntity.status == "active",
                (EntityIdentifier.valid_from.is_(None))
                | (EntityIdentifier.valid_from <= effective_date),
                (EntityIdentifier.valid_to.is_(None))
                | (EntityIdentifier.valid_to >= effective_date),
            )
        )
        if normalized_type:
            statement = statement.where(ResearchEntity.entity_type == normalized_type)
        entity = session.scalars(statement).first()
        if entity:
            return EntityResolution("resolved", entity, "identifier", (entity,))
        if not alias:
            return EntityResolution("not_found", None, None)
    normalized_alias = normalize_name(alias) if alias else None
    statement = (
        select(ResearchEntity)
        .join(EntityAlias, EntityAlias.entity_id == ResearchEntity.entity_id)
        .where(
            EntityAlias.normalized_alias == normalized_alias,
            ResearchEntity.status == "active",
            (EntityAlias.valid_from.is_(None)) | (EntityAlias.valid_from <= effective_date),
            (EntityAlias.valid_to.is_(None)) | (EntityAlias.valid_to >= effective_date),
        )
    )
    if source_key:
        statement = statement.where(
            or_(EntityAlias.source_key == source_key, EntityAlias.source_key.is_(None))
        )
    if normalized_type:
        statement = statement.where(ResearchEntity.entity_type == normalized_type)
    candidates = tuple(
        session.scalars(statement.order_by(ResearchEntity.entity_id)).unique().all()
    )
    if len(candidates) == 1:
        return EntityResolution("resolved", candidates[0], "exact_alias", candidates)
    if len(candidates) > 1:
        return EntityResolution("ambiguous", None, "exact_alias", candidates)
    return EntityResolution("not_found", None, None)



def create_entity_relationship(
    session: Session,
    from_entity_id: int,
    to_entity_id: int,
    relation_type: str,
    source_key: str | None = None,
    evidence_id: int | None = None,
    valid_from: date | None = None,
    valid_to: date | None = None,
    confidence: Decimal | None = None,
    verification_status: str = "unverified",
    metadata: dict | None = None,
) -> EntityRelationship:
    """Create or update a typed, temporal relationship between canonical entities."""
    _require_entity(session, from_entity_id)
    _require_entity(session, to_entity_id)
    if from_entity_id == to_entity_id:
        raise ValueError("An entity cannot have a relationship with itself.")
    normalized_relation = relation_type.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,49}", normalized_relation):
        raise ValueError("relation_type must be a 2–50 character lowercase identifier.")
    _validate_date_range(valid_from, valid_to)
    if verification_status not in VERIFICATION_STATUSES:
        raise ValueError("Unsupported verification_status.")
    if confidence is not None and (
        not confidence.is_finite() or confidence < 0 or confidence > 1
    ):
        raise ValueError("confidence must be between 0 and 1.")
    if source_key and session.get(DataSource, source_key) is None:
        raise ValueError(f"Unknown source_key: {source_key!r}.")
    evidence = session.get(EvidenceRecord, evidence_id) if evidence_id else None
    if evidence_id and evidence is None:
        raise ValueError(f"Evidence {evidence_id} does not exist.")
    if evidence is not None:
        if source_key and evidence.source_key != source_key:
            raise ValueError("source_key must match the linked evidence source.")
        source_key = source_key or evidence.source_key
    if verification_status == "verified":
        if evidence is None or evidence.verification_status != "verified":
            raise ValueError("A verified relationship requires linked verified evidence.")
        source = session.get(DataSource, source_key) if source_key else None
        if (
            source is None
            or not source.enabled
            or not source.is_official
            or source.source_type != "official"
        ):
            raise ValueError("A verified relationship requires an enabled registered official source.")

    existing = session.scalar(
        select(EntityRelationship).where(
            EntityRelationship.from_entity_id == from_entity_id,
            EntityRelationship.to_entity_id == to_entity_id,
            EntityRelationship.relation_type == normalized_relation,
            EntityRelationship.valid_from.is_not_distinct_from(valid_from),
        )
    )
    values = {
        "source_key": source_key,
        "evidence_id": evidence_id,
        "valid_to": valid_to,
        "confidence": confidence,
        "verification_status": verification_status,
        "metadata_json": metadata or {},
    }
    if existing:
        if verification_status == "unverified" and existing.verification_status != "unverified":
            values["verification_status"] = existing.verification_status
        if evidence_id is None:
            values["evidence_id"] = existing.evidence_id
        if source_key is None:
            values["source_key"] = existing.source_key
        if confidence is None:
            values["confidence"] = existing.confidence
        for key, value in values.items():
            setattr(existing, key, value)
        return existing
    record = EntityRelationship(
        from_entity_id=from_entity_id,
        to_entity_id=to_entity_id,
        relation_type=normalized_relation,
        valid_from=valid_from,
        **values,
    )
    session.add(record)
    session.flush()
    return record
