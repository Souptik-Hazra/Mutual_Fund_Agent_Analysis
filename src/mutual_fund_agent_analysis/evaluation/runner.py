"""Offline routing and response-grounding evaluation; no LLM or network calls."""

import json
from pathlib import Path
from typing import Any

from mutual_fund_agent_analysis.agents.research_graph import classify_intents


def evaluate_routing(cases: list[dict[str, Any]]) -> dict[str, Any]:
    if not cases:
        raise ValueError("Evaluation dataset is empty.")
    exact = 0
    per_intent: dict[str, dict[str, int]] = {}
    rows = []
    for case in cases:
        expected = case["expected_intents"]
        predicted = classify_intents(case["question"], case.get("scheme_codes", []))
        passed = predicted == expected
        exact += int(passed)
        for intent in set(expected) | set(predicted):
            stats = per_intent.setdefault(intent, {"expected": 0, "predicted": 0, "true_positive": 0})
            stats["expected"] += int(intent in expected)
            stats["predicted"] += int(intent in predicted)
            stats["true_positive"] += int(intent in expected and intent in predicted)
        rows.append({"question": case["question"], "expected": expected,
                     "predicted": predicted, "passed": passed})
    precision_recall = {}
    for intent, stats in per_intent.items():
        precision_recall[intent] = {
            "precision": stats["true_positive"] / stats["predicted"] if stats["predicted"] else 0.0,
            "recall": stats["true_positive"] / stats["expected"] if stats["expected"] else 0.0,
        }
    return {
        "case_count": len(cases), "exact_match_accuracy": exact / len(cases),
        "per_intent": precision_recall, "cases": rows,
    }


def load_and_evaluate(path: str | Path) -> dict[str, Any]:
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    return evaluate_routing(cases)



def retrieval_metrics(expected_ids: list[int], retrieved_ids: list[int]) -> dict[str, float]:
    """Calculate precision@k, recall@k and reciprocal rank for a reviewed query."""
    expected = set(expected_ids)
    if not expected:
        raise ValueError("expected_ids must contain at least one relevant document/chunk.")
    if not retrieved_ids:
        return {"precision_at_k": 0.0, "recall_at_k": 0.0, "reciprocal_rank": 0.0}
    relevant = [identifier for identifier in retrieved_ids if identifier in expected]
    first_rank = next((index for index, identifier in enumerate(retrieved_ids, 1)
                       if identifier in expected), None)
    return {
        "precision_at_k": len(set(relevant)) / len(retrieved_ids),
        "recall_at_k": len(set(relevant)) / len(expected),
        "reciprocal_rank": 1 / first_rank if first_rank else 0.0,
    }


def evaluate_grounding_contract(response: dict[str, Any]) -> dict[str, Any]:
    """Check structured assistant response completeness and evidence coverage."""
    results = response.get("results") or {}
    citations = response.get("citations") or []
    result_groups = len(results)
    citation_groups = {
        citation.get("type") for citation in citations if isinstance(citation, dict)
    }
    missing_groups = [
        group for group in results
        if group not in citation_groups and not any(
            citation.get("type") in {
                "financial_data", "portfolio_disclosure", "market_event",
                "social_aggregation", "document_chunk",
            }
            for citation in citations if isinstance(citation, dict)
        )
    ]
    return {
        "answer_nonempty": bool(str(response.get("answer", "")).strip()),
        "result_group_count": result_groups,
        "citation_count": len(citations),
        "has_structured_results": isinstance(results, dict),
        "evidence_present": bool(citations) if result_groups else True,
        "missing_citation_groups": missing_groups,
        "grounding_contract_passed": bool(str(response.get("answer", "")).strip())
        and isinstance(results, dict)
        and (bool(citations) if result_groups else True),
    }
