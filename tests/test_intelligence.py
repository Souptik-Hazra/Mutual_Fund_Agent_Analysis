"""Tests for the common intelligence foundation."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.data.services.intelligence import (
    add_entity_alias, add_entity_identifier, create_entity, link_entity_evidence,
    normalize_identifier, normalize_name, record_evidence, resolve_entity,
)
from mutual_fund_agent_analysis.database.base import Base
from mutual_fund_agent_analysis.models.intelligence import DataSource


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[Base.metadata.tables[name] for name in (
            "data_sources", "research_entities", "entity_aliases", "entity_identifiers",
            "evidence_records", "entity_evidence_links",
        )],
    )
    with Session(engine) as db:
        db.add_all([
            DataSource(
                source_key="amfi", display_name="AMFI", source_type="official",
                authority_tier=1, is_official=True, enabled=True, metadata_json={},
            ),
            DataSource(
                source_key="mfapi", display_name="MFAPI", source_type="provider",
                authority_tier=2, is_official=False, enabled=True, metadata_json={},
            ),
        ])
        db.commit()
        yield db
    engine.dispose()


def test_normalization_is_unicode_and_whitespace_safe():
    assert normalize_name("  HDFC\u00a0  Mutual Fund ") == "hdfc mutual fund"
    assert normalize_identifier(" in e 000123 ") == "INE000123"


def test_entity_creation_is_idempotent(session):
    first = create_entity(session, "scheme", "HDFC Flexi Cap Fund")
    second = create_entity(session, "scheme", "  HDFC   Flexi Cap Fund ")
    assert first.entity_id == second.entity_id


def test_identifier_resolution_has_priority(session):
    entity = create_entity(session, "scheme", "HDFC Flexi Cap Fund")
    add_entity_identifier(session, entity.entity_id, "AMFI_SCHEME_CODE", "12345", "amfi")
    add_entity_alias(session, entity.entity_id, "HDFC Flexi Cap")
    result = resolve_entity(session, namespace="AMFI_SCHEME_CODE", identifier_value="12345")
    assert result.status == "resolved"
    assert result.matched_by == "identifier"
    assert result.entity.entity_id == entity.entity_id


def test_ambiguous_alias_is_not_auto_resolved(session):
    first = create_entity(session, "company", "ABC Limited")
    second = create_entity(session, "company", "ABC Holdings")
    add_entity_alias(session, first.entity_id, "ABC")
    add_entity_alias(session, second.entity_id, "ABC")
    result = resolve_entity(session, entity_type="company", alias="abc")
    assert result.status == "ambiguous"
    assert result.entity is None
    assert len(result.candidates) == 2


def test_alias_validity_is_temporal(session):
    entity = create_entity(session, "company", "Old Name Limited")
    add_entity_alias(
        session, entity.entity_id, "Old Name",
        valid_from=date(2010, 1, 1), valid_to=date(2020, 1, 1),
    )
    current = resolve_entity(session, alias="Old Name", as_of=date(2025, 1, 1))
    historical = resolve_entity(session, alias="Old Name", as_of=date(2015, 1, 1))
    assert current.status == "not_found"
    assert historical.status == "resolved"


def test_source_specific_alias_resolution(session):
    first = create_entity(session, "company", "ABC Holdings")
    second = create_entity(session, "company", "ABC Limited")
    add_entity_alias(session, first.entity_id, "ABC", source_key="amfi")
    add_entity_alias(session, second.entity_id, "ABC", source_key="mfapi")
    amfi_result = resolve_entity(session, alias="ABC", source_key="amfi")
    mfapi_result = resolve_entity(session, alias="ABC", source_key="mfapi")
    assert amfi_result.status == "resolved"
    assert amfi_result.entity.entity_id == first.entity_id
    assert mfapi_result.status == "resolved"
    assert mfapi_result.entity.entity_id == second.entity_id


def test_identifier_cannot_be_reassigned(session):
    first = create_entity(session, "company", "ABC Limited")
    second = create_entity(session, "company", "XYZ Limited")
    add_entity_identifier(session, first.entity_id, "ISIN", "INE000000001", "amfi")
    with pytest.raises(ValueError, match="already assigned"):
        add_entity_identifier(session, second.entity_id, "ISIN", "INE000000001", "amfi")


def test_evidence_is_idempotent_and_linked(session):
    entity = create_entity(session, "scheme", "HDFC Flexi Cap Fund")
    evidence = record_evidence(
        session, "amfi", external_id="nav-report-2026-11-25",
        canonical_url="https://www.amfiindia.com/", title="AMFI NAV report",
        published_at=datetime(2026, 11, 25, tzinfo=timezone.utc),
        confidence=Decimal("0.990"), verification_status="verified",
    )
    same = record_evidence(
        session, "amfi", external_id="nav-report-2026-11-25",
        title="Updated AMFI NAV report", verification_status="verified",
    )
    assert evidence.evidence_id == same.evidence_id
    link = link_entity_evidence(
        session, entity.entity_id, evidence.evidence_id,
        "published_by", Decimal("0.99"), "manual",
    )
    assert link.entity_id == entity.entity_id
    assert link.evidence_id == evidence.evidence_id


def test_invalid_evidence_url_and_confidence_rejected(session):
    with pytest.raises(ValueError, match="HTTP"):
        record_evidence(session, "amfi", canonical_url="javascript:alert(1)")
    with pytest.raises(ValueError, match="confidence"):
        record_evidence(session, "amfi", confidence=Decimal("1.5"))


def test_unknown_and_disabled_sources_are_rejected(session):
    with pytest.raises(ValueError, match="Unknown source"):
        record_evidence(session, "unknown")
    session.add(DataSource(
        source_key="disabled", display_name="Disabled", source_type="social",
        authority_tier=4, is_official=False, enabled=False, metadata_json={},
    ))
    session.flush()
    with pytest.raises(ValueError, match="disabled"):
        record_evidence(session, "disabled")
