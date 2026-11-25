"""Deterministic tests for routing and LangGraph evaluation contracts."""

from mutual_fund_agent_analysis.agents.research_graph import classify_intents
from mutual_fund_agent_analysis.api.schemas.assistant import ResearchAssistantRequest


def test_router_selects_fund_analysis_for_performance_question():
    assert classify_intents("Show CAGR and risk for this fund", [125497]) == ["fund"]


def test_router_selects_multiple_specialists_when_question_needs_them():
    routes = classify_intents("Review holdings and recent company news", [125497])
    assert routes == ["portfolio", "events"]


def test_router_defaults_to_fund_for_explicit_scheme_code():
    assert classify_intents("Analyse this scheme", [125497]) == ["fund"]


def test_router_defaults_to_document_search_without_other_intent():
    assert classify_intents("Find information about this scheme") == ["documents"]


def test_assistant_request_validates_codes_and_date_order():
    request = ResearchAssistantRequest(question="Compare these funds", scheme_codes=[125497, 120503])
    assert len(request.scheme_codes) == 2
