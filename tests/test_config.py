"""Configuration validation tests."""

import pytest
from pydantic import ValidationError

from mutual_fund_agent_analysis.core.config import Settings


def test_production_rejects_development_database_credentials():
    with pytest.raises(ValidationError, match='DATABASE_URL must be explicitly configured'):
        Settings(app_env='production')


def test_production_accepts_explicit_database_url():
    settings = Settings(
        app_env='production',
        database_url='postgresql+psycopg://app:secure-password@db.example.com:5432/funds',
    )
    assert settings.app_env == 'production'
