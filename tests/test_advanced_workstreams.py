"""Regression coverage for security data, hybrid retrieval and research routing."""

from datetime import UTC, datetime
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
        "observed_at": datetime(2026, 11, 25, 10, 0, tzinfo=UTC),
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


def test_security_router_does_not_misclassify_dividend_yield_as_an_event():
    assert classify_intents(
        "Show the stock valuation and dividend yield for my holdings",
        [125497],
    ) == ["portfolio", "security"]


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


def test_security_grounding_contract_requires_market_observation_citation():
    from mutual_fund_agent_analysis.evaluation.runner import evaluate_grounding_contract

    result = evaluate_grounding_contract(
        {
            "answer": "Available stock observations are shown.",
            "results": {"security": {"securities": []}},
            "citations": [{"type": "security_market_observation"}],
        }
    )
    assert result["grounding_contract_passed"] is True

    missing = evaluate_grounding_contract(
        {"answer": "Unsupported stock analysis.", "results": {"security": {}}, "citations": []}
    )
    assert missing["grounding_contract_passed"] is False


def test_quote_only_observation_does_not_erase_older_fundamentals_or_events():
    from datetime import date
    from types import SimpleNamespace

    latest_quote = SimpleNamespace(
        security_key="INE002A01018",
        isin="INE002A01018",
        security_name="Example Industries",
        symbol="EXAMPLE",
        exchange="NSE",
        observed_at=datetime(2026, 11, 25, 10, 0, tzinfo=UTC),
        observation_id=2,
        last_price=Decimal("130"),
        change_pct=Decimal("2"),
        day_high=None,
        day_low=None,
        volume=None,
        market_status="trading",
        retrieved_at=datetime(2026, 11, 25, 10, 1, tzinfo=UTC),
        source_key="quote_provider",
        source_url="https://example.com/quote",
        fundamentals_as_of=None,
        fundamentals_json={},
        corporate_events_json=[],
        content_hash="b" * 64,
    )
    older_fundamentals = SimpleNamespace(
        **{
            **latest_quote.__dict__,
            "observed_at": datetime(2026, 10, 1, 10, 0, tzinfo=UTC),
            "observation_id": 1,
            "last_price": Decimal("120"),
            "source_key": "fundamentals_provider",
            "source_url": "https://example.com/fundamentals",
            "fundamentals_as_of": date(2026, 9, 30),
            "fundamentals_json": {"pe_ratio": "22.5"},
            "corporate_events_json": [{"title": "Board meeting", "verification_status": "unverified"}],
            "content_hash": "a" * 64,
        }
    )

    class SequentialSession:
        def __init__(self):
            self.calls = 0

        def scalars(self, _statement):
            self.calls += 1
            rows = [latest_quote, older_fundamentals] if self.calls == 1 else []

            class Result:
                def all(self):
                    return rows

            return Result()

    result = security_profile(SequentialSession(), "INE002A01018")

    assert result["market"]["last_price"] == Decimal("130")
    assert result["fundamentals"]["metrics"]["pe_ratio"] == "22.5"
    assert result["fundamentals"]["source_key"] == "fundamentals_provider"
    assert result["corporate_events"][0]["title"] == "Board meeting"
