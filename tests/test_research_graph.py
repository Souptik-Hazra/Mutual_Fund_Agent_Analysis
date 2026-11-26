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

    research_graph._run_tools({"request": request, "session": object(), "intents": ["portfolio"]})

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


def test_router_selects_category_specialist_for_peer_rankings():
    assert classify_intents("Rank this fund against category peers", [125497]) == ["category"]


def test_router_selects_actual_investor_exposure_specialist():
    assert classify_intents(
        "Show my actual investor exposure from the ledger", [125497, 120503]
    ) == ["actual_exposure"]


def test_router_keeps_hypothetical_portfolio_exposure_separate():
    assert classify_intents(
        "Compare equity exposure across these fund portfolios", [125497, 120503]
    ) == ["portfolio"]


def test_category_specialist_uses_existing_deterministic_peer_service(monkeypatch):
    requested_end = date(2026, 11, 25)
    captured = {}

    def analyze(session, code, start_date, end_date, **kwargs):
        captured.update(code=code, start_date=start_date, end_date=end_date, **kwargs)
        return {
            "category": "Large Cap",
            "start_date": date(2025, 1, 1),
            "end_date": requested_end,
            "observation_dates": 200,
            "return_basis": "growth_nav",
            "peer_count": 8,
            "excluded_peers": [],
            "rankings": [],
        }

    monkeypatch.setattr(research_graph, "analyze_category_peers", analyze)
    request = ResearchAssistantRequest(
        question="Rank fund category peers",
        scheme_codes=[125497],
        start_date=date(2025, 1, 1),
        end_date=requested_end,
        top_k=4,
    )
    result = research_graph._run_tools(
        {"request": request, "session": object(), "intents": ["category"]}
    )
    assert captured == {
        "code": 125497,
        "start_date": date(2025, 1, 1),
        "end_date": requested_end,
        "max_peers": 40,
        "benchmark_code": None,
        "benchmark_source": "niftyindices",
    }
    assert result["results"]["category"]["return_basis"] == "growth_nav"
    assert result["citations"][0]["type"] == "category_peer_analysis"


def test_actual_exposure_specialist_uses_ledger_service(monkeypatch):
    captured = {}

    def exposure(session, codes, as_of_date):
        captured["codes"] = codes
        captured["as_of_date"] = as_of_date
        return {
            "valuation_basis": "ledger units x reconciled NAV",
            "coverage": {"valued_fund_count": 1, "selected_fund_count": 2},
            "valued_funds": [{"scheme_code": 125497, "nav_date": date(2026, 11, 25)}],
            "excluded_funds": [{"scheme_code": 120503, "reason": "No units"}],
            "equity_exposure": [],
            "warning": "Dated holdings disclosures only.",
        }

    monkeypatch.setattr(research_graph, "actual_portfolio_exposure", exposure)
    request = ResearchAssistantRequest(
        question="Show my actual investor exposure",
        scheme_codes=[125497, 120503],
        as_of_date=date(2026, 11, 20),
    )
    result = research_graph._run_tools(
        {"request": request, "session": object(), "intents": ["actual_exposure"]}
    )
    assert captured["codes"] == [125497, 120503]
    assert captured["as_of_date"] == date(2026, 11, 20)
    assert result["citations"][0]["valuation_dates"][0]["nav_date"] == date(2026, 11, 25)


def test_fund_specialist_preserves_exact_deterministic_result(monkeypatch):
    expected = {
        "cagr": "0.1250",
        "volatility": "0.0825",
        "observation_count": 240,
        "return_basis": "growth_nav",
    }
    monkeypatch.setattr(research_graph, "analyze_fund", lambda *args, **kwargs: expected)
    request = ResearchAssistantRequest(
        question="Show CAGR and volatility",
        scheme_codes=[125497],
    )
    result = research_graph._run_tools(
        {"request": request, "session": object(), "intents": ["fund"]}
    )
    assert result["results"]["fund"] == expected


def test_portfolio_specialist_preserves_disclosure_allocation_and_overlap(monkeypatch):
    snapshot = SimpleNamespace(
        effective_date=date(2026, 10, 31),
        content_hash="d" * 64,
        document_url="https://amc.example/portfolio.pdf",
        source_key="amc_disclosures",
        retrieved_at=None,
    )
    expected_snapshot = {
        "holdings": [{"security_key": "INE1", "weight_pct": "12.5"}],
        "sector_allocation": [{"sector": "Banks", "weight_pct": "30.0"}],
        "hhi_0_to_1": "0.18",
    }
    expected_comparison = {
        "pairwise_overlap": [{"scheme_a": 125497, "scheme_b": 120503, "overlap_pct": "42.0"}]
    }
    monkeypatch.setattr(research_graph, "latest_snapshot", lambda *args: snapshot)
    monkeypatch.setattr(research_graph, "portfolio_payload", lambda *args: expected_snapshot)
    monkeypatch.setattr(research_graph, "compare_portfolios", lambda *args: expected_comparison)
    request = ResearchAssistantRequest(
        question="Compare fund portfolio holdings overlap",
        scheme_codes=[125497, 120503],
    )
    result = research_graph._run_tools(
        {"request": request, "session": object(), "intents": ["portfolio"]}
    )
    assert result["results"]["portfolio"] == {
        "snapshots": [expected_snapshot, expected_snapshot],
        "comparison": expected_comparison,
    }


def test_security_specialist_preserves_market_and_fundamental_observations(monkeypatch):
    expected = {
        "securities": [
            {
                "security_key": "INE1",
                "market": {"last_price": "125.50", "source_key": "quotes"},
                "fundamentals": {"metrics": {"pe_ratio": "22.5"}, "source_key": "fundamentals"},
                "corporate_events": [],
            }
        ],
        "coverage": {"schemes_with_disclosures": 1},
    }
    snapshot = SimpleNamespace(
        effective_date=date(2026, 10, 31),
        content_hash="e" * 64,
        document_url="https://amc.example/portfolio.pdf",
        source_key="amc_disclosures",
        retrieved_at=None,
    )
    monkeypatch.setattr(research_graph, "securities_for_funds", lambda *args, **kwargs: expected)
    monkeypatch.setattr(research_graph, "latest_snapshot", lambda *args, **kwargs: snapshot)
    request = ResearchAssistantRequest(
        question="Compare underlying stock fundamentals",
        scheme_codes=[125497],
    )
    result = research_graph._run_tools(
        {"request": request, "session": object(), "intents": ["security"]}
    )
    assert result["results"]["security"] == expected
    assert {item["type"] for item in result["citations"]} == {
        "portfolio_disclosure",
        "security_market_observation",
    }


def test_event_specialist_preserves_historical_event_snapshot(monkeypatch):
    expected = {
        "events": [
            {
                "event_id": 77,
                "title": "Board meeting",
                "status": "scheduled",
                "published_at": "2026-10-25T10:00:00+00:00",
                "event_date": "2026-11-05",
                "canonical_url": "https://nse.example/77",
            }
        ],
        "as_of": "2026-11-01T00:00:00+00:00",
    }
    monkeypatch.setattr(research_graph, "events_for_fund_exposure", lambda *args: expected)
    request = ResearchAssistantRequest(
        question="Show upcoming company events",
        scheme_codes=[125497],
        start_date=date(2026, 10, 1),
        end_date=date(2026, 11, 30),
    )
    result = research_graph._run_tools(
        {"request": request, "session": object(), "intents": ["events"]}
    )
    assert result["results"]["events"] == [expected]
    assert result["citations"][0]["event_id"] == 77


def test_social_specialist_preserves_aggregated_sentiment_metrics(monkeypatch):
    expected = {
        "post_count": 10,
        "sentiment_distribution": {"positive": 4, "neutral": 3, "negative": 3},
        "weighted_sentiment": "0.1250",
    }
    monkeypatch.setattr(research_graph, "social_analytics", lambda *args: expected)
    request = ResearchAssistantRequest(question="Show global Reddit sentiment")
    result = research_graph._run_tools(
        {"request": request, "session": object(), "intents": ["social"]}
    )
    assert result["results"]["social"]["aggregation"] == expected


def test_document_specialist_preserves_retrieval_citations(monkeypatch):
    expected = {
        "results": [
            {
                "document_id": 3,
                "title": "Scheme factsheet",
                "page_number": 5,
                "text": "Expense ratio is 0.75%.",
                "citation": {
                    "content_hash": "f" * 64,
                    "canonical_url": "https://amc.example/fs.pdf",
                },
            }
        ],
        "retrieval_mode": "lexical_fallback",
    }
    monkeypatch.setattr(research_graph, "search_documents", lambda *args: expected)
    request = ResearchAssistantRequest(question="Find expense ratio in factsheet")
    result = research_graph._run_tools(
        {"request": request, "session": object(), "intents": ["documents"]}
    )
    assert result["results"]["documents"] == expected
    assert result["citations"][0]["content_hash"] == "f" * 64


def test_assistant_request_rejects_as_of_date_after_end_date():
    from pydantic import ValidationError
    import pytest

    with pytest.raises(ValidationError, match="as_of_date cannot be later"):
        ResearchAssistantRequest(
            question="Show my actual exposure",
            scheme_codes=[125497],
            end_date=date(2026, 6, 30),
            as_of_date=date(2026, 7, 1),
        )
