"""Offline routing and response-grounding evaluation; no LLM or network calls."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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
            stats = per_intent.setdefault(
                intent, {"expected": 0, "predicted": 0, "true_positive": 0}
            )
            stats["expected"] += int(intent in expected)
            stats["predicted"] += int(intent in predicted)
            stats["true_positive"] += int(intent in expected and intent in predicted)
        rows.append(
            {
                "question": case["question"],
                "expected": expected,
                "predicted": predicted,
                "passed": passed,
            }
        )
    precision_recall = {}
    for intent, stats in per_intent.items():
        precision_recall[intent] = {
            "precision": stats["true_positive"] / stats["predicted"] if stats["predicted"] else 0.0,
            "recall": stats["true_positive"] / stats["expected"] if stats["expected"] else 0.0,
        }
    return {
        "case_count": len(cases),
        "exact_match_accuracy": exact / len(cases),
        "per_intent": precision_recall,
        "cases": rows,
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
    first_rank = next(
        (index for index, identifier in enumerate(retrieved_ids, 1) if identifier in expected), None
    )
    return {
        "precision_at_k": len(set(relevant)) / len(retrieved_ids),
        "recall_at_k": len(set(relevant)) / len(expected),
        "reciprocal_rank": 1 / first_rank if first_rank else 0.0,
    }


def evaluate_grounding_contract(response: dict[str, Any]) -> dict[str, Any]:
    """Check structured assistant response completeness and evidence coverage."""
    results = response.get("results") or {}
    citations = response.get("citations") or []
    expected_types = {
        "fund": {"financial_data"},
        "category": {"category_peer_analysis"},
        "actual_exposure": {"actual_investor_exposure"},
        "portfolio": {"portfolio_disclosure"},
        "security": {
            "security_market_observation",
            "security_corporate_event",
            "portfolio_disclosure",
        },
        "events": {"market_event"},
        "social": {"social_aggregation"},
        "documents": {"document_chunk"},
    }
    citation_types = {citation.get("type") for citation in citations if isinstance(citation, dict)}
    missing_groups = [
        group for group in results if not (expected_types.get(group, {None}) & citation_types)
    ]
    answer_nonempty = bool(str(response.get("answer", "")).strip())
    evidence_present = not results or not missing_groups
    return {
        "answer_nonempty": answer_nonempty,
        "result_group_count": len(results),
        "citation_count": len(citations),
        "has_structured_results": isinstance(results, dict),
        "evidence_present": evidence_present,
        "missing_citation_groups": missing_groups,
        "grounding_contract_passed": answer_nonempty
        and isinstance(results, dict)
        and evidence_present,
    }


def evaluate_evidence_quality(
    response: dict[str, Any],
    *,
    require_citations: bool | None = None,
) -> dict[str, Any]:
    """Measure citation provenance, verification and temporal anomalies."""
    citations = response.get("citations") or []
    if not isinstance(citations, list):
        citations = []
    results = response.get("results") or {}
    required = bool(results) if require_citations is None else require_citations
    complete = 0
    verified = 0
    stale = 0
    future_publications = 0
    malformed = 0

    def parse_timestamp(value: Any) -> datetime:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed

    for citation in citations:
        if not isinstance(citation, dict):
            malformed += 1
            continue
        source_url = citation.get("canonical_url")
        retrieved = citation.get("retrieved_at")
        published = citation.get("published_at")
        has_provenance = all((citation.get("source_key"), source_url, retrieved))
        complete += int(has_provenance)
        verified += int(citation.get("verification_status") == "verified")
        citation_is_malformed = False
        if source_url:
            parsed_url = urlparse(str(source_url))
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
                citation_is_malformed = True
        retrieved_at = None
        if retrieved:
            try:
                retrieved_at = parse_timestamp(retrieved)
            except (TypeError, ValueError, OverflowError):
                citation_is_malformed = True
        published_at = None
        if published:
            try:
                published_at = parse_timestamp(published)
            except (TypeError, ValueError, OverflowError):
                citation_is_malformed = True
        if published_at is not None and retrieved_at is not None:
            if published_at > retrieved_at:
                future_publications += 1
            elif (retrieved_at - published_at).days > 365:
                stale += 1
        malformed += int(citation_is_malformed)
    citation_count = len(citations)
    provenance_completeness = complete / citation_count if citation_count else 0.0
    verified_ratio = verified / citation_count if citation_count else 0.0
    unsupported_claims = response.get("unsupported_claims") or []
    unsupported_claim_count = (
        len(unsupported_claims)
        if isinstance(unsupported_claims, (list, tuple, set))
        else int(bool(unsupported_claims))
    )
    passed = (
        (not required or citation_count > 0)
        and (not required or complete == citation_count)
        and malformed == 0
        and future_publications == 0
        and stale == 0
        and unsupported_claim_count == 0
    )
    return {
        "citation_count": citation_count,
        "provenance_completeness": provenance_completeness,
        "verified_citation_ratio": verified_ratio,
        "stale_citation_count": stale,
        "future_publication_count": future_publications,
        "malformed_citation_count": malformed,
        "unsupported_claim_count": unsupported_claim_count,
        "evidence_quality_passed": passed,
    }


def evaluate_evidence_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Run a reviewed set of evidence-contract cases and compare expected outcomes."""
    if not cases:
        raise ValueError("Evidence evaluation dataset is empty.")
    rows = []
    passed = 0
    for case in cases:
        metrics = evaluate_evidence_quality(
            case["response"],
            require_citations=case.get("require_citations"),
        )
        expected = bool(case["expected_pass"])
        actual = bool(metrics["evidence_quality_passed"])
        correct = actual == expected
        passed += int(correct)
        rows.append(
            {
                "name": case["name"],
                "expected_pass": expected,
                "actual_pass": actual,
                "case_passed": correct,
                "metrics": metrics,
            }
        )
    return {
        "case_count": len(cases),
        "correct_outcomes": passed,
        "accuracy": passed / len(cases),
        "cases": rows,
    }


def load_and_evaluate_evidence(path: str | Path) -> dict[str, Any]:
    """Load reviewed evidence-contract cases from JSON."""
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    return evaluate_evidence_cases(cases)
