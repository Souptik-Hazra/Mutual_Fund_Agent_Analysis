"""Tests for offline agent routing evaluation."""

from mutual_fund_agent_analysis.evaluation.runner import evaluate_routing


def test_routing_evaluator_reports_exact_accuracy_and_per_intent_scores():
    result = evaluate_routing([
        {"question": "Show CAGR and risk", "scheme_codes": [10001], "expected_intents": ["fund"]},
        {"question": "Show holdings and sectors", "scheme_codes": [10001], "expected_intents": ["portfolio"]},
    ])
    assert result["case_count"] == 2
    assert result["exact_match_accuracy"] == 1.0
    assert result["per_intent"]["fund"]["recall"] == 1.0
