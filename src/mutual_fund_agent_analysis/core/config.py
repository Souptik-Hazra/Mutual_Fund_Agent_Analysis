"""Typed application settings loaded from environment variables."""
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets are never logged or exposed in API responses."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    app_name: str = "Mutual Fund Agent Analysis"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    database_url: str = (
        "postgresql+psycopg://mfa:mfa_dev_password@localhost:5432/mutual_fund_agent"
    )
    llm_provider: Literal["gemini", "groq", "openai"] = "gemini"
    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = None
    groq_api_key: SecretStr | None = None
    groq_model: str | None = None
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    langsmith_api_key: SecretStr | None = None
    langsmith_tracing: bool = False
    langsmith_project: str = "mutual-fund-agent-analysis"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings so all components share one configuration."""
    return Settings()
