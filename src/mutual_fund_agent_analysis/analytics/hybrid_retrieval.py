"""Deterministic reciprocal-rank fusion for lexical and semantic document retrieval."""

from __future__ import annotations

from typing import Any


def reciprocal_rank_fusion(
    lexical: list[dict[str, Any]],
    semantic: list[dict[str, Any]],
    *,
    limit: int,
    rank_constant: int = 60,
) -> list[dict[str, Any]]:
    """Merge retrieval channels by stable document/chunk identity without mixing raw scores."""
    if limit < 1 or rank_constant < 1:
        raise ValueError("limit and rank_constant must be positive.")

    merged: dict[tuple[Any, Any], dict[str, Any]] = {}
    scores: dict[tuple[Any, Any], float] = {}
    modes: dict[tuple[Any, Any], set[str]] = {}
    for mode, rows in (("lexical", lexical), ("semantic", semantic)):
        seen: set[tuple[Any, Any]] = set()
        for rank, row in enumerate(rows, start=1):
            citation = row.get("citation") or {}
            key = (citation.get("document_id", row.get("document_id")), citation.get("chunk_id"))
            if key[0] is None or key[1] is None or key in seen:
                continue
            seen.add(key)
            scores[key] = scores.get(key, 0.0) + 1.0 / (rank_constant + rank)
            modes.setdefault(key, set()).add(mode)
            if key not in merged:
                merged[key] = dict(row)
            else:
                # Prefer the richer lexical record for provenance fields; semantic text may be retained
                # when the lexical channel did not return this chunk.
                for field, value in row.items():
                    if merged[key].get(field) in (None, "") and value not in (None, ""):
                        merged[key][field] = value

    ranked = sorted(scores, key=lambda key: (-scores[key], key[0], key[1]))
    results = []
    for key in ranked[:limit]:
        row = merged[key]
        row["retrieval_score"] = scores[key]
        row["retrieval_modes"] = sorted(modes[key])
        row["retrieval_mode"] = (
            "hybrid_rrf" if len(modes[key]) == 2 else next(iter(modes[key]))
        )
        results.append(row)
    return results
