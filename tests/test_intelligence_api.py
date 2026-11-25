"""API contract tests for entity and evidence endpoints."""

from fastapi.testclient import TestClient

from mutual_fund_agent_analysis.main import create_app


def test_intelligence_routes_are_registered():
    client = TestClient(create_app())
    response = client.get("/api/v1/intelligence/sources")
    assert response.status_code in {200, 503}


def test_entity_create_request_rejects_blank_name():
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/intelligence/entities",
        json={"entity_type": "company", "canonical_name": "   "},
    )
    assert response.status_code == 422


def test_resolve_request_requires_lookup_key():
    client = TestClient(create_app())
    response = client.post("/api/v1/intelligence/resolve", json={"entity_type": "company"})
    assert response.status_code == 422


def test_evidence_request_rejects_invalid_confidence():
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/intelligence/evidence",
        json={"source_key": "amfi", "confidence": "1.2"},
    )
    assert response.status_code == 422
