"""Shared test fixtures."""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


@pytest.fixture(scope="session")
def postgres_engine() -> Engine:
    """Provide the PostgreSQL integration database when configured."""
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    engine = create_engine(database_url, pool_pre_ping=True)
    yield engine
    engine.dispose()
