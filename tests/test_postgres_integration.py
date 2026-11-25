"""PostgreSQL integration tests for migrations and NAV persistence."""

import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.core.config import get_settings
from mutual_fund_agent_analysis.data.providers.mfapi import MFAPINavResponse
from mutual_fund_agent_analysis.data.repositories.nav_repository import upsert_nav_response
from mutual_fund_agent_analysis.data.services.nav_sync import sync_scheme_nav
from mutual_fund_agent_analysis.database.session import (
    check_database_connection,
    get_engine,
    get_session_factory,
)
from mutual_fund_agent_analysis.models import (
    BenchmarkIndex,
    BenchmarkObservation,
    BenchmarkSyncRun,
    EntityAlias,
    EntityEvidenceLink,
    EntityIdentifier,
    EntityRelationship,
    EvidenceRecord,
    MutualFundScheme,
    NavObservation,
    NavReconciliation,
    ProviderSyncRun,
    ResearchEntity,
)


@pytest.fixture(scope="module")
def migrated_postgres() -> Engine:
    """Run real Alembic migrations against a dedicated TEST_DATABASE_URL."""
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")

    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    get_settings.cache_clear()
    root = Path(__file__).parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        if get_engine.cache_info().currsize:
            get_engine().dispose()
        get_session_factory.cache_clear()
        get_engine.cache_clear()
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
        get_settings.cache_clear()


def make_response(nav: str = "25.12345678", include_metadata: bool = True) -> MFAPINavResponse:
    metadata = {
        "scheme_code": 991234,
        "scheme_name": "Integration Test Equity Fund",
    }
    if include_metadata:
        metadata.update({"fund_house": "Test AMC", "scheme_category": "Equity"})
    return MFAPINavResponse.model_validate(
        {
            "meta": metadata,
            "data": [{"date": "25-11-2026", "nav": nav}],
            "status": "SUCCESS",
        }
    )


def test_00_postgres_migration_upgrade_downgrade_upgrade(migrated_postgres: Engine) -> None:
    """Verify the actual PostgreSQL schema can migrate both directions."""
    root = Path(__file__).parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.downgrade(config, "base")
    assert "mutual_fund_schemes" not in inspect(migrated_postgres).get_table_names()
    command.upgrade(config, "0001_initial_market_data")
    original_key = inspect(migrated_postgres).get_pk_constraint("nav_observations")
    assert set(original_key["constrained_columns"]) == {"scheme_code", "nav_date"}
    with migrated_postgres.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO mutual_fund_schemes "
                "(scheme_code, scheme_name, fund_house, source) "
                "VALUES (880001, 'Migration Backfill Equity Fund', "
                "'Migration AMC', 'amfi')"
            )
        )
    command.upgrade(config, "0005_benchmark_tri")
    with migrated_postgres.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO benchmark_indices "
                "(benchmark_code, benchmark_name, provider) "
                "VALUES ('MIGRATION_TEST', 'Migration Test Index', 'niftyindices')"
            )
        )
    command.upgrade(config, "head")
    tables = inspect(migrated_postgres).get_table_names()
    assert "mutual_fund_schemes" in tables
    assert "nav_observations" in tables
    assert "provider_sync_runs" in tables
    assert "nav_reconciliations" in tables
    assert "benchmark_indices" in tables
    assert "benchmark_observations" in tables
    assert "benchmark_sync_runs" in tables
    assert "data_sources" in tables
    assert "research_entities" in tables
    assert "entity_aliases" in tables
    assert "entity_identifiers" in tables
    assert "evidence_records" in tables
    assert "entity_evidence_links" in tables
    assert "entity_relationships" in tables
    assert "alembic_version" in tables
    alias_indexes = {
        item["name"] for item in inspect(migrated_postgres).get_indexes("entity_aliases")
    }
    identifier_indexes = {
        item["name"] for item in inspect(migrated_postgres).get_indexes("entity_identifiers")
    }
    assert "uq_entity_aliases_primary" in alias_indexes
    assert "uq_entity_identifiers_primary" in identifier_indexes
    with Session(migrated_postgres) as session:
        scheme_identifier = session.scalar(
            select(EntityIdentifier).where(
                EntityIdentifier.namespace == "AMFI_SCHEME_CODE",
                EntityIdentifier.normalized_value == "880001",
            )
        )
        benchmark_identifier = session.scalar(
            select(EntityIdentifier).where(
                EntityIdentifier.namespace == "BENCHMARK_CODE",
                EntityIdentifier.normalized_value == "MIGRATION_TEST",
            )
        )
        assert scheme_identifier is not None
        assert benchmark_identifier is not None
        benchmark_alias = session.scalar(
            select(EntityAlias).where(
                EntityAlias.entity_id == benchmark_identifier.entity_id,
                EntityAlias.normalized_alias == "migration test index",
            )
        )
        assert benchmark_alias is not None
        scheme_entity = session.get(ResearchEntity, scheme_identifier.entity_id)
        assert scheme_entity is not None
        amc_entity = session.scalar(
            select(ResearchEntity).where(
                ResearchEntity.entity_type == "amc",
                ResearchEntity.canonical_name == "Migration AMC",
            )
        )
        assert amc_entity is not None
        relationship = session.scalar(
            select(EntityRelationship).where(
                EntityRelationship.from_entity_id == scheme_entity.entity_id,
                EntityRelationship.to_entity_id == amc_entity.entity_id,
                EntityRelationship.relation_type == "managed_by",
            )
        )
        assert relationship is not None
        assert relationship.verification_status == "unverified"
    source_key = inspect(migrated_postgres).get_pk_constraint("nav_observations")
    assert set(source_key["constrained_columns"]) == {"scheme_code", "nav_date", "source"}
    check_database_connection()
    command.downgrade(config, "0001_initial_market_data")
    with pytest.raises(RuntimeError, match="migrations are not current"):
        check_database_connection()
    command.upgrade(config, "head")
    check_database_connection()


def test_postgres_upsert_is_idempotent_and_preserves_provider_observations(
    migrated_postgres: Engine,
) -> None:
    """Repeated writes update one provider without replacing another provider."""
    with Session(migrated_postgres) as session, session.begin():
        assert upsert_nav_response(session, make_response(), source="mfapi") == 1
        assert upsert_nav_response(session, make_response("25.50"), source="amfi") == 1
        assert upsert_nav_response(session, make_response("25.75"), source="mfapi") == 1

    with Session(migrated_postgres) as session:
        rows = session.scalars(
            select(NavObservation).where(NavObservation.scheme_code == 991234)
        ).all()
        values = {row.source: row.nav for row in rows}
        assert values == {"mfapi": 25.75, "amfi": 25.50}
        sync_runs = session.scalars(
            select(ProviderSyncRun).where(ProviderSyncRun.scheme_code == 991234)
        ).all()
        assert len(sync_runs) == 3
        reconciliation = session.get(NavReconciliation, (991234, date(2026, 11, 25)))
        assert reconciliation is not None
        assert reconciliation.status == "conflict"
        assert reconciliation.canonical_source == "amfi"
        assert {key: Decimal(value) for key, value in reconciliation.source_values.items()} == {
            "amfi": Decimal("25.50"),
            "mfapi": Decimal("25.75"),
        }
        assert sync_runs[0].response_payload["meta"]["scheme_code"] == 991234
        assert sync_runs[0].observation_count == 1
        scheme_entity = session.scalar(
            select(ResearchEntity).where(
                ResearchEntity.entity_type == "scheme",
                ResearchEntity.canonical_name == "Integration Test Equity Fund [991234]",
            )
        )
        assert scheme_entity is not None
        scheme_identifier = session.scalar(
            select(EntityIdentifier).where(
                EntityIdentifier.namespace == "AMFI_SCHEME_CODE",
                EntityIdentifier.normalized_value == "991234",
            )
        )
        assert scheme_identifier is not None
        assert scheme_identifier.entity_id == scheme_entity.entity_id
        manager_relationship = session.scalar(
            select(EntityRelationship).where(
                EntityRelationship.from_entity_id == scheme_entity.entity_id,
                EntityRelationship.relation_type == "managed_by",
            )
        )
        assert manager_relationship is not None
        assert manager_relationship.verification_status == "unverified"
        assert manager_relationship.evidence_id is not None
        sync_evidence = session.scalars(
            select(EvidenceRecord).where(
                EvidenceRecord.source_key.in_(["amfi", "mfapi"]),
                EvidenceRecord.external_id.like("provider-sync-run:%"),
            )
        ).all()
        assert len(sync_evidence) == 3
        assert all(
            session.get(EntityEvidenceLink, (scheme_entity.entity_id, item.evidence_id))
            for item in sync_evidence
        )


def test_scheme_identity_survives_provider_name_changes(migrated_postgres: Engine) -> None:
    first = MFAPINavResponse.model_validate(
        {
            "meta": {"scheme_code": 991237, "scheme_name": "Old Scheme Name"},
            "data": [{"date": "25-11-2026", "nav": "10.0"}],
            "status": "SUCCESS",
        }
    )
    renamed = MFAPINavResponse.model_validate(
        {
            "meta": {"scheme_code": 991237, "scheme_name": "New Scheme Name"},
            "data": [{"date": "26-11-2026", "nav": "10.1"}],
            "status": "SUCCESS",
        }
    )
    with Session(migrated_postgres) as session, session.begin():
        upsert_nav_response(session, first, source="mfapi")
        upsert_nav_response(session, renamed, source="amfi")

    with Session(migrated_postgres) as session:
        identifier = session.scalar(
            select(EntityIdentifier).where(
                EntityIdentifier.namespace == "AMFI_SCHEME_CODE",
                EntityIdentifier.normalized_value == "991237",
            )
        )
        assert identifier is not None
        aliases = session.scalars(
            select(EntityAlias).where(EntityAlias.entity_id == identifier.entity_id)
        ).all()
        assert {alias.alias for alias in aliases} >= {"Old Scheme Name", "New Scheme Name"}


def test_postgres_upsert_does_not_erase_optional_scheme_metadata(
    migrated_postgres: Engine,
) -> None:
    """Missing optional fields in a later response preserve existing values."""
    with Session(migrated_postgres) as session, session.begin():
        upsert_nav_response(session, make_response(), source="mfapi")
        upsert_nav_response(session, make_response(include_metadata=False), source="mfapi")

    with Session(migrated_postgres) as session:
        scheme = session.get(MutualFundScheme, 991234)
        assert scheme is not None
        assert scheme.fund_house == "Test AMC"
        assert scheme.scheme_category == "Equity"


def test_sync_uses_savepoint_inside_caller_transaction(migrated_postgres: Engine) -> None:
    """A sync can run after a caller query without committing its transaction."""

    class StubClient:
        def get_nav_history(self, scheme_code, start_date=None, end_date=None):
            assert scheme_code == 991235
            return MFAPINavResponse.model_validate(
                {
                    "meta": {"scheme_code": 991235, "scheme_name": "Nested Transaction Fund"},
                    "data": [{"date": "25-11-2026", "nav": "10.5"}],
                    "status": "SUCCESS",
                }
            )

    with Session(migrated_postgres) as session:
        session.execute(text("SELECT 1"))
        assert session.in_transaction()
        assert sync_scheme_nav(session, 991235, client=StubClient()) == 1
        assert session.in_transaction()
        session.commit()

    with Session(migrated_postgres) as session:
        assert session.get(MutualFundScheme, 991235) is not None


def test_postgres_repository_rejects_invalid_source(migrated_postgres: Engine) -> None:
    with Session(migrated_postgres) as session:
        with pytest.raises(ValueError, match="source must contain"):
            upsert_nav_response(session, make_response(), source=" ")


def test_sync_savepoint_remains_rollbackable_by_outer_transaction(
    migrated_postgres: Engine,
) -> None:
    class StubClient:
        def get_nav_history(self, scheme_code, start_date=None, end_date=None):
            return MFAPINavResponse.model_validate(
                {
                    "meta": {"scheme_code": 991236, "scheme_name": "Rollback Test Fund"},
                    "data": [{"date": "25-11-2026", "nav": "11.5"}],
                    "status": "SUCCESS",
                }
            )

    with Session(migrated_postgres) as session:
        session.execute(text("SELECT 1"))
        sync_scheme_nav(session, 991236, client=StubClient())
        session.rollback()

    with Session(migrated_postgres) as session:
        assert session.get(MutualFundScheme, 991236) is None


def test_postgres_benchmark_tri_upsert_is_idempotent(migrated_postgres: Engine) -> None:
    from mutual_fund_agent_analysis.data.providers.niftyindices import (
        BenchmarkPoint,
        BenchmarkResponse,
    )
    from mutual_fund_agent_analysis.data.repositories.benchmark_repository import (
        upsert_benchmark_response,
    )

    response = BenchmarkResponse(
        benchmark_code="NIFTY 50",
        benchmark_name="Nifty 50",
        data=[
            BenchmarkPoint(
                date=date(2026, 11, 24),
                tri="35600.00",
                ntr="31000.00",
            ),
            BenchmarkPoint(
                date=date(2026, 11, 25),
                tri="35793.78",
                ntr="31169.30",
            ),
        ],
        raw_payload={"provider": "niftyindices", "fixture": True},
    )
    with Session(migrated_postgres) as session, session.begin():
        assert upsert_benchmark_response(session, response) == 2
        assert upsert_benchmark_response(session, response) == 2

    with Session(migrated_postgres) as session:
        benchmark = session.get(BenchmarkIndex, "NIFTY 50")
        assert benchmark is not None
        rows = session.scalars(
            select(BenchmarkObservation).where(BenchmarkObservation.benchmark_code == "NIFTY 50")
        ).all()
        assert len(rows) == 2
        assert {row.source for row in rows} == {"niftyindices"}
        assert rows[0].tri_value > 0
        runs = session.scalars(
            select(BenchmarkSyncRun).where(BenchmarkSyncRun.benchmark_code == "NIFTY 50")
        ).all()
        assert len(runs) == 2
        assert runs[0].response_payload["fixture"] is True
        benchmark_identifier = session.scalar(
            select(EntityIdentifier).where(
                EntityIdentifier.namespace == "BENCHMARK_CODE",
                EntityIdentifier.normalized_value == "NIFTY 50",
            )
        )
        assert benchmark_identifier is not None
        benchmark_entity = session.get(ResearchEntity, benchmark_identifier.entity_id)
        assert benchmark_entity is not None
        assert benchmark_entity.entity_type == "benchmark"
        benchmark_evidence = session.scalars(
            select(EvidenceRecord).where(
                EvidenceRecord.source_key == "niftyindices",
                EvidenceRecord.external_id.like("benchmark-sync-run:%"),
            )
        ).all()
        assert len(benchmark_evidence) == 2
        assert all(
            session.get(EntityEvidenceLink, (benchmark_entity.entity_id, item.evidence_id))
            for item in benchmark_evidence
        )
