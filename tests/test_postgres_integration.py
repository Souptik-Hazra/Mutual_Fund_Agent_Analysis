"""PostgreSQL integration tests for migrations and NAV persistence."""

import os
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
from mutual_fund_agent_analysis.models import MutualFundScheme, NavObservation


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
    command.upgrade(config, "head")
    tables = inspect(migrated_postgres).get_table_names()
    assert "mutual_fund_schemes" in tables
    assert "nav_observations" in tables
    assert "alembic_version" in tables
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
