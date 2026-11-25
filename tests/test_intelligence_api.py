"""API contract tests for entity and evidence endpoints."""

from fastapi.testclient import TestClient

from mutual_fund_agent_analysis.api.routes.intelligence import router as intelligence_router
from mutual_fund_agent_analysis.database.session import get_db
from mutual_fund_agent_analysis.main import create_app


def _client() -> TestClient:
    app = create_app()

    def unused_database():
        yield None

    app.dependency_overrides[get_db] = unused_database
    return TestClient(app)


def test_intelligence_routes_are_registered():
    paths = {route.path for route in intelligence_router.routes if hasattr(route, "path")}
    assert "/intelligence/sources" in paths
    assert "/intelligence/entities" in paths
    assert "/intelligence/resolve" in paths
    assert "/intelligence/entities/{entity_id}/relationships" in paths
    assert "/intelligence/entities/{entity_id}/aliases" in paths
    assert "/intelligence/entities/{entity_id}/identifiers" in paths


def test_entity_create_request_rejects_blank_name():
    client = _client()
    response = client.post(
        "/api/v1/intelligence/entities",
        json={"entity_type": "company", "canonical_name": "   "},
    )
    assert response.status_code == 422


def test_resolve_request_requires_lookup_key():
    client = _client()
    response = client.post("/api/v1/intelligence/resolve", json={"entity_type": "company"})
    assert response.status_code == 422


def test_evidence_request_rejects_invalid_confidence():
    client = _client()
    response = client.post(
        "/api/v1/intelligence/evidence",
        json={"source_key": "amfi", "confidence": "1.2"},
    )
    assert response.status_code == 422


def test_evidence_pagination_is_bounded():
    client = _client()
    response = client.get(
        "/api/v1/intelligence/entities/1/evidence",
        params={"limit": 101},
    )
    assert response.status_code == 422
    entity_response = client.get("/api/v1/intelligence/entities", params={"limit": 101})
    assert entity_response.status_code == 422
