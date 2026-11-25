"""Tests for the LangGraph supervisor and its deterministic routing layer."""

from datetime import date
from types import SimpleNamespace

import mutual_fund_agent_analysis.agents.research_graph as research_graph
from mutual_fund_agent_analysis.agents.research_graph import build_research_graph, classify_intents
from mutual_fund_agent_analysis.api.schemas.assistant import ResearchAssistantRequest


def test_router_selects_fund_analysis_for_performance_question():
    assert classify_intents("Show CAGR and risk for this fund", [125497]) == ["fund"]


def test_router_selects_multiple_specialists_when_question_needs_them():
    routes = classify_intents("Review holdings and recent company news", [125497])
    assert routes == ["portfolio", "events"]


def test_event_exposure_does_not_trigger_separate_portfolio_agent():
    assert classify_intents("Show event exposure for my fund", [125497]) == ["events"]


def test_router_does_not_call_fund_analytics_for_portfolio_overlap():
    assert classify_intents("Compare overlap between two portfolios", [125497, 120503]) == [
        "portfolio"
    ]


def test_router_defaults_to_fund_for_explicit_scheme_code():
    assert classify_intents("Analyse this scheme", [125497]) == ["fund"]


def test_router_defaults_to_document_search_without_other_intent():
    assert classify_intents("Find information about this scheme") == ["documents"]


def test_assistant_request_validates_codes_and_date_order():
    request = ResearchAssistantRequest(
        question="Compare these funds", scheme_codes=[125497, 120503]
    )
    assert len(request.scheme_codes) == 2


def test_graph_compiles_with_supervisor_and_specialist_nodes():
    graph = build_research_graph()
    assert {"plan", "specialist_agents", "synthesize"}.issubset(graph.get_graph().nodes)


def test_portfolio_comparison_respects_requested_end_date(monkeypatch):
    requested_end = date(2025, 12, 31)
    snapshot = SimpleNamespace(
        effective_date=date(2025, 12, 1),
        content_hash="a" * 64,
        document_url=None,
    )
    captured = {}

    monkeypatch.setattr(research_graph, "latest_snapshot", lambda *args: snapshot)
    monkeypatch.setattr(research_graph, "portfolio_payload", lambda *args: {"holdings": []})

    def compare(session, codes, as_of=None):
        captured["codes"] = codes
        captured["as_of"] = as_of
        return {"as_of": as_of}

    monkeypatch.setattr(research_graph, "compare_portfolios", compare)
    request = ResearchAssistantRequest(
        question="Compare portfolio holdings",
        scheme_codes=[125497, 120503],
        end_date=requested_end,
    )

    research_graph._run_tools(
        {"request": request, "session": object(), "intents": ["portfolio"]}
    )

    assert captured == {"codes": [125497, 120503], "as_of": requested_end}


def test_fund_specific_social_research_requires_a_complete_date_range(monkeypatch):
    def unexpected_global_fallback(*args):
        raise AssertionError("Fund-specific requests must not fall back to global sentiment.")

    monkeypatch.setattr(research_graph, "social_analytics", unexpected_global_fallback)
    request = ResearchAssistantRequest(
        question="Show sentiment for this fund",
        scheme_codes=[125497],
    )

    result = research_graph._run_tools(
        {"request": request, "session": object(), "intents": ["social"]}
    )

    assert "social" not in result["results"]
    assert any("requires both start_date and end_date" in item for item in result["errors"])


def test_global_social_research_is_explicitly_labelled(monkeypatch):
    monkeypatch.setattr(
        research_graph,
        "social_analytics",
        lambda *args: {"post_count": 3},
    )
    request = ResearchAssistantRequest(question="Show overall social sentiment")

    result = research_graph._run_tools(
        {"request": request, "session": object(), "intents": ["social"]}
    )

    assert result["results"]["social"]["scope"] == "global"
    assert result["results"]["social"]["aggregation"]["post_count"] == 3
    assert result["citations"][0]["scope"] == "global"
