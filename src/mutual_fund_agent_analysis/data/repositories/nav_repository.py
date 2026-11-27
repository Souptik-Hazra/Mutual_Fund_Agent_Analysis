"""Idempotent PostgreSQL upserts for schemes, NAVs, and reconciliation results."""

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.data.providers.contracts import NavResponse
from mutual_fund_agent_analysis.data.services.scheme_metadata_sync import classify_scheme_name
from mutual_fund_agent_analysis.data.services.intelligence import (
    add_entity_alias,
    add_entity_identifier,
    create_entity,
    create_entity_relationship,
    link_entity_evidence,
    record_evidence,
)
from mutual_fund_agent_analysis.data.services.nav_reconciliation import (
    NAV_RECONCILIATION_TOLERANCE,
    build_reconciliation,
)
from mutual_fund_agent_analysis.models import (
    DataSource,
    EntityIdentifier,
    ResearchEntity,
    MutualFundScheme,
    NavObservation,
    NavReconciliation,
    ProviderSyncRun,
    SchemeMetadataObservation,
)


def _reconcile_dates(session: Session, scheme_code: int, nav_dates: set[date]) -> None:
    if not nav_dates:
        return
    observations = session.scalars(
        select(NavObservation).where(
            NavObservation.scheme_code == scheme_code,
            NavObservation.nav_date.in_(nav_dates),
        )
    ).all()
    grouped: dict = {}
    for observation in observations:
        grouped.setdefault(observation.nav_date, {})[observation.source] = Decimal(
            observation.nav
        )

    for nav_date, values in grouped.items():
        result = build_reconciliation(values, NAV_RECONCILIATION_TOLERANCE)
        statement = insert(NavReconciliation).values(
            scheme_code=scheme_code,
            nav_date=nav_date,
            source_values=result["source_values"],
            canonical_nav=result["canonical_nav"],
            canonical_source=result["canonical_source"],
            absolute_difference=result["absolute_difference"],
            relative_difference=result["relative_difference"],
            status=result["status"],
            tolerance=result["tolerance"],
            evaluated_at=datetime.now(UTC),
        )
        statement = statement.on_conflict_do_update(
            index_elements=[NavReconciliation.scheme_code, NavReconciliation.nav_date],
            set_={
                "source_values": statement.excluded.source_values,
                "canonical_nav": statement.excluded.canonical_nav,
                "canonical_source": statement.excluded.canonical_source,
                "absolute_difference": statement.excluded.absolute_difference,
                "relative_difference": statement.excluded.relative_difference,
                "status": statement.excluded.status,
                "tolerance": statement.excluded.tolerance,
                "evaluated_at": statement.excluded.evaluated_at,
            },
        )
        session.execute(statement)


def upsert_nav_response(
    session: Session,
    response: NavResponse,
    source: str = "mfapi",
) -> int:
    """Upsert source-specific observations and refresh their canonical decisions."""
    normalized_source = source.strip().lower()
    if not normalized_source or len(normalized_source) > 40:
        raise ValueError("source must contain between 1 and 40 characters.")
    metadata = response.meta
    scheme_values = {
        "scheme_code": metadata.scheme_code,
        "scheme_name": metadata.scheme_name,
        "fund_house": metadata.fund_house,
        "scheme_type": metadata.scheme_type,
        "scheme_category": metadata.scheme_category,
        "isin_growth": metadata.isin_growth,
        "isin_div_reinvestment": metadata.isin_div_reinvestment,
        "source": normalized_source,
        "source_updated_at": datetime.now(UTC),
    }
    scheme_statement = insert(MutualFundScheme).values(**scheme_values)
    excluded = scheme_statement.excluded
    scheme_statement = scheme_statement.on_conflict_do_update(
        index_elements=[MutualFundScheme.scheme_code],
        set_={
            "scheme_name": func.coalesce(MutualFundScheme.scheme_name, excluded.scheme_name),
            "fund_house": func.coalesce(MutualFundScheme.fund_house, excluded.fund_house),
            "scheme_type": func.coalesce(MutualFundScheme.scheme_type, excluded.scheme_type),
            "scheme_category": func.coalesce(
                MutualFundScheme.scheme_category, excluded.scheme_category
            ),
            "isin_growth": func.coalesce(MutualFundScheme.isin_growth, excluded.isin_growth),
            "isin_div_reinvestment": func.coalesce(
                MutualFundScheme.isin_div_reinvestment, excluded.isin_div_reinvestment
            ),
            "source": excluded.source,
            "source_updated_at": excluded.source_updated_at,
        },
    )
    session.execute(scheme_statement)

    source_record = session.get(DataSource, normalized_source)
    source_key = normalized_source if source_record is not None else None
    if source_record is not None:
        raw_metadata = {
            "scheme_code": metadata.scheme_code,
            "scheme_name": metadata.scheme_name,
            "fund_house": metadata.fund_house,
            "scheme_type": metadata.scheme_type,
            "scheme_category": metadata.scheme_category,
            "isin_growth": metadata.isin_growth,
            "isin_div_reinvestment": metadata.isin_div_reinvestment,
            "nav_observation_count": len(response.data),
        }
        encoded_metadata = json.dumps(
            raw_metadata, sort_keys=True, separators=(",", ":"), default=str
        )
        metadata_hash = hashlib.sha256(encoded_metadata.encode("utf-8")).hexdigest()
        plan_type, option_type = classify_scheme_name(metadata.scheme_name)
        source_url = (
            (response.raw_payload or {}).get("endpoint")
            or source_record.base_url
            or "https://api.mfapi.in"
        )
        metadata_statement = insert(SchemeMetadataObservation).values(
            scheme_code=metadata.scheme_code,
            source_key=normalized_source,
            source_url=source_url,
            content_hash=metadata_hash,
            observed_at=datetime.now(UTC),
            plan_type=plan_type,
            option_type=option_type,
            verification_status="unverified",
            verification_note=(
                "Captured from NAV provider metadata; canonical classifications "
                "require independent verification."
            ),
            metadata_json=raw_metadata,
        ).on_conflict_do_nothing(constraint="uq_scheme_metadata_source_hash")
        session.execute(metadata_statement)
    entity = session.scalar(
        select(ResearchEntity)
        .join(EntityIdentifier, EntityIdentifier.entity_id == ResearchEntity.entity_id)
        .where(
            EntityIdentifier.namespace == "AMFI_SCHEME_CODE",
            EntityIdentifier.normalized_value == str(metadata.scheme_code),
        )
    )
    if entity is None:
        entity = create_entity(
            session,
            "scheme",
            f"{metadata.scheme_name} [{metadata.scheme_code}]",
        )
        add_entity_identifier(
            session, entity.entity_id, "AMFI_SCHEME_CODE", str(metadata.scheme_code),
            source_key=source_key, is_primary=True,
        )
    add_entity_alias(
        session, entity.entity_id, metadata.scheme_name,
        alias_type="provider_name", source_key=source_key, is_primary=True,
    )
    for isin in (metadata.isin_growth, metadata.isin_div_reinvestment):
        if isin:
            add_entity_identifier(
                session, entity.entity_id, "ISIN", isin, source_key=source_key,
            )
    if metadata.fund_house:
        amc = create_entity(session, "amc", metadata.fund_house)
        add_entity_alias(
            session, amc.entity_id, metadata.fund_house,
            alias_type="provider_name", source_key=source_key, is_primary=True,
        )
        create_entity_relationship(
            session,
            entity.entity_id,
            amc.entity_id,
            "managed_by",
            source_key=source_key,
            verification_status="unverified",
            metadata={"provider_scheme_code": metadata.scheme_code},
        )

    fetched_at = datetime.now(UTC)
    nav_values = [
        {
            "scheme_code": metadata.scheme_code,
            "nav_date": point.date,
            "nav": point.nav,
            "source": normalized_source,
            "fetched_at": fetched_at,
        }
        for point in response.data
    ]
    processed = 0
    affected_dates = {value["nav_date"] for value in nav_values}
    for offset in range(0, len(nav_values), 1000):
        batch = nav_values[offset : offset + 1000]
        nav_statement = insert(NavObservation).values(batch)
        nav_statement = nav_statement.on_conflict_do_update(
            index_elements=[
                NavObservation.scheme_code,
                NavObservation.nav_date,
                NavObservation.source,
            ],
            set_={
                "nav": nav_statement.excluded.nav,
                "fetched_at": nav_statement.excluded.fetched_at,
            },
        )
        session.execute(nav_statement)
        processed += len(batch)

    raw_payload = response.raw_payload
    if raw_payload is None:
        raw_payload = (
            response.model_dump(mode="json")
            if hasattr(response, "model_dump")
            else {
                "provider": normalized_source,
                "scheme_code": metadata.scheme_code,
                "observations": [
                    {"date": point.date.isoformat(), "nav": str(point.nav)}
                    for point in response.data
                ],
            }
        )
    sync_run = ProviderSyncRun(
        scheme_code=metadata.scheme_code,
        source=normalized_source,
        fetched_at=fetched_at,
        observation_count=processed,
        response_payload=raw_payload,
    )
    session.add(sync_run)
    session.flush()
    if source_key is not None:
        content_hash = hashlib.sha256(
            json.dumps(raw_payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        evidence = record_evidence(
            session,
            source_key,
            external_id=f"provider-sync-run:{sync_run.id}",
            title=f"NAV provider sync for scheme {metadata.scheme_code}",
            retrieved_at=fetched_at,
            content_hash=content_hash,
            verification_status="unverified",
            metadata={
                "scheme_code": metadata.scheme_code,
                "sync_run_id": sync_run.id,
                "observation_count": processed,
            },
        )
        link_entity_evidence(
            session,
            entity.entity_id,
            evidence.evidence_id,
            relation_type="nav_sync",
            resolution_method="identifier",
        )
        if metadata.fund_house:
            amc = create_entity(session, "amc", metadata.fund_house)
            create_entity_relationship(
                session,
                entity.entity_id,
                amc.entity_id,
                "managed_by",
                source_key=source_key,
                evidence_id=evidence.evidence_id,
                verification_status="unverified",
                metadata={"provider_scheme_code": metadata.scheme_code},
            )
    _reconcile_dates(session, metadata.scheme_code, affected_dates)
    return processed
