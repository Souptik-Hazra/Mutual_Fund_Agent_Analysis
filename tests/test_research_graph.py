"""Tests for the LangGraph supervisor and its deterministic routing layer."""

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
