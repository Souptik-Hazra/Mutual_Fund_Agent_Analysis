"""Regression coverage for security data, hybrid retrieval and research routing."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from mutual_fund_agent_analysis.agents.research_graph import classify_intents
from mutual_fund_agent_analysis.analytics.hybrid_retrieval import reciprocal_rank_fusion
from mutual_fund_agent_analysis.analytics.security_intelligence import security_profile
from mutual_fund_agent_analysis.api.routes.market_data import SecurityObservationInput


def valid_security_observation(**overrides):
    payload = {
        "security_key": "INE002A01018",
        "security_name": "Example Industries",
        "source_key": "test_provider",
        "observed_at": datetime(2026, 11, 25, 10, 0, tzinfo=timezone.utc),
        "last_price": Decimal("125.50"),
        "fundamentals_as_of": "2026-09-30",
        "fundamentals": {"pe_ratio": "22.5", "roe_pct": "14.2"},
    }
    payload.update(overrides)
    return payload


def test_security_observation_accepts_dated_source_metrics():
    observation = SecurityObservationInput(**valid_security_observation())
    assert observation.fundamentals["pe_ratio"] == Decimal("22.5")
    assert observation.observed_at.utcoffset().total_seconds() == 0


def test_security_observation_rejects_unknown_fundamental_fields():
    with pytest.raises(ValidationError, match="Unsupported fundamental metric"):
        SecurityObservationInput(
            **valid_security_observation(fundamentals={"forecast_return": "0.3"})
        )


def test_security_observation_requires_timezone_aware_timestamp():
    with pytest.raises(ValidationError, match="must include a timezone"):
        SecurityObservationInput(
            **valid_security_observation(observed_at=datetime(2026, 11, 25, 10, 0))
        )


def test_security_observation_rejects_future_fundamentals_date():
    with pytest.raises(ValidationError, match="cannot be after observed_at"):
        SecurityObservationInput(
            **valid_security_observation(fundamentals_as_of="2026-12-01")
        )


def test_security_router_selects_underlying_security_specialist():
    assert classify_intents(
        "Compare P/E ratio, ROE and fundamentals of underlying stocks",
        [125497],
    ) == ["security"]


def test_security_router_can_run_with_fund_performance():
    assert classify_intents(
        "Show fund returns and underlying stock fundamentals",
        [125497],
    ) == ["fund", "security"]


def test_hybrid_retrieval_fuses_same_chunk_from_both_channels():
    lexical = [
        {
            "document_id": 1,
            "chunk_index": 2,
            "text": "Expense ratio is disclosed.",
            "citation": {"document_id": 1, "chunk_id": 12, "chunk_index": 2},
        },
        {
            "document_id": 2,
            "chunk_index": 0,
            "text": "Other document.",
            "citation": {"document_id": 2, "chunk_id": 20, "chunk_index": 0},
        },
    ]
    semantic = [
        {
            "document_id": 1,
            "chunk_index": 2,
            "text": "Expense ratio is disclosed.",
            "citation": {"document_id": 1, "chunk_index": 2},
        },
        {
            "document_id": 3,
            "chunk_index": 1,
            "text": "Semantic match.",
            "citation": {"document_id": 3, "chunk_index": 1},
        },
    ]

    results = reciprocal_rank_fusion(lexical, semantic, limit=3)

    assert results[0]["document_id"] == 1
    assert results[0]["retrieval_modes"] == ["lexical", "semantic"]
    assert results[0]["retrieval_mode"] == "hybrid_rrf"
    assert len(results) == 3


def test_hybrid_retrieval_handles_empty_channels_and_rejects_invalid_limit():
    assert reciprocal_rank_fusion([], [], limit=5) == []
    with pytest.raises(ValueError, match="must be positive"):
        reciprocal_rank_fusion([], [], limit=0)


def test_security_profile_abstains_when_no_provider_observation_exists():
    class EmptySession:
        def scalars(self, _statement):
            class Result:
                @staticmethod
                def all():
                    return []

            return Result()

    result = security_profile(EmptySession(), "ine002a01018")

    assert result["security_key"] == "INE002A01018"
    assert result["availability"] == "no_market_observation"
    assert result["fundamentals"]["availability"] == "unavailable"
    assert result["market"] is None
