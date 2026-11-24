"""Database engine, sessions, and connection checks."""
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from mutual_fund_agent_analysis.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create a pooled SQLAlchemy engine on first use."""
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=1800,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Return the shared session factory."""
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that always closes the request-scoped session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def check_database_connection() -> None:
    """Raise the underlying SQLAlchemy exception when the database is unavailable."""
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))
