"""API tests for the personal research assistant."""


def test_assistant_capabilities_are_available_without_provider_credentials(client):
    response = client.get("/api/v1/assistant/capabilities")
    assert response.status_code == 200
    payload = response.json()
    assert payload["orchestration"] == "LangGraph"
    expected = {
        "fund",
        "category",
        "portfolio",
        "actual_exposure",
        "security",
        "events",
        "social",
        "documents",
    }
    assert set(payload["agents"]) == expected
    assert {item["id"] for item in payload["capabilities"]} == expected
