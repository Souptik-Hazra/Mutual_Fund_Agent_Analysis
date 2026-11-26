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


def test_streaming_assistant_exposes_one_research_run_id(client, monkeypatch):
    from mutual_fund_agent_analysis.api.routes import assistant as assistant_routes

    class FakeGraph:
        def stream(self, state, stream_mode):
            assert stream_mode == "updates"
            run_id = state["research_run_id"]
            yield {"plan": {"intents": ["documents"], "research_run_id": run_id}}
            yield {
                "specialist_agents": {
                    "results": {},
                    "errors": [],
                    "citations": [],
                    "research_run_id": run_id,
                }
            }
            yield {
                "synthesize": {
                    "answer": "Research completed.",
                    "model_used": None,
                    "research_run_id": run_id,
                }
            }

    monkeypatch.setattr(assistant_routes, "build_research_graph", lambda: FakeGraph())
    response = client.post(
        "/api/v1/assistant/research/stream",
        json={"question": "Summarize my fund documents"},
    )

    assert response.status_code == 200
    run_id = response.headers["X-Research-Run-ID"]
    frames = [frame for frame in response.text.split("\n\n") if frame.strip()]
    complete = next(frame for frame in frames if frame.startswith("event: complete"))
    payload_line = next(line for line in complete.splitlines() if line.startswith("data: "))
    import json

    payload = json.loads(payload_line.removeprefix("data: "))
    assert payload["research_run_id"] == run_id
    assert all(run_id in frame for frame in frames)


def test_non_streaming_assistant_exposes_research_run_id(client, monkeypatch):
    from mutual_fund_agent_analysis.api.routes import assistant as assistant_routes

    class FakeGraph:
        def invoke(self, state):
            run_id = state["research_run_id"]
            return {
                "intents": ["documents"],
                "answer": "Research completed.",
                "results": {},
                "citations": [],
                "errors": [],
                "model_used": None,
                "research_run_id": run_id,
            }

    monkeypatch.setattr(assistant_routes, "build_research_graph", lambda: FakeGraph())
    response = client.post(
        "/api/v1/assistant/research",
        json={"question": "Summarize my fund documents"},
    )

    assert response.status_code == 200
    assert response.json()["research_run_id"]
