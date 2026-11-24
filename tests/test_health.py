"""Health endpoint tests."""

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from mutual_fund_agent_analysis.api.routes import health
from mutual_fund_agent_analysis.main import create_app


def test_liveness_returns_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_ready_when_database_is_available(monkeypatch) -> None:
    monkeypatch.setattr(health, "check_database_connection", lambda: None)
    client = TestClient(create_app())
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "connected"}


def test_readiness_returns_503_when_database_is_unavailable(monkeypatch) -> None:
    def raise_database_error() -> None:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(health, "check_database_connection", raise_database_error)
    client = TestClient(create_app())
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable or schema migrations are not current."}


def test_readiness_returns_503_when_migrations_are_pending(monkeypatch) -> None:
    def raise_migration_error() -> None:
        raise RuntimeError("Database schema migrations are not current.")

    monkeypatch.setattr(health, "check_database_connection", raise_migration_error)
    client = TestClient(create_app())
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Database is unavailable or schema migrations are not current."
    }
