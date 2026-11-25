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
