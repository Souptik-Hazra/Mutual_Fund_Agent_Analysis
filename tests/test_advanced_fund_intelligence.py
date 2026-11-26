"""Regression tests for advanced fund intelligence foundations."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import mutual_fund_agent_analysis.analytics.portfolio_intelligence as portfolio_module
from mutual_fund_agent_analysis.analytics.category_benchmarks import resolve_category_benchmark
from mutual_fund_agent_analysis.analytics.portfolio_intelligence import actual_portfolio_exposure
from mutual_fund_agent_analysis.analytics.security_intelligence import security_profile
from mutual_fund_agent_analysis.data.providers.twelvedata import TwelveDataClient
from mutual_fund_agent_analysis.models.security import SecurityMarketObservation


def test_quote_parser_requires_timestamp():
    with pytest.raises(ValueError, match="timestamp"):
        TwelveDataClient._timestamp({"symbol": "INFY", "close": "1500"})


def test_quote_parser_rejects_naive_timestamp():
    with pytest.raises(ValueError, match="timezone"):
        TwelveDataClient._timestamp({"datetime": "2026-11-25 10:00:00"})


def test_benchmark_resolver_fails_closed_on_overlap():
    scheme = SimpleNamespace(
        scheme_category="Large Cap", scheme_type="Equity", plan_type="direct", option_type="growth"
    )

    class Session:
        def scalars(self, _query):
            return self

        def all(self):
            return [object(), object()]

    with pytest.raises(ValueError, match="Multiple active"):
        resolve_category_benchmark(Session(), scheme, date(2026, 11, 26))


def test_actual_exposure_rejects_invalid_selection():
    with pytest.raises(ValueError, match="distinct"):
        actual_portfolio_exposure(None, [1, 1])
    with pytest.raises(ValueError, match="one and twenty"):
        actual_portfolio_exposure(None, [])


def test_benchmark_resolver_requires_enabled_official_source():
    mapping = SimpleNamespace(
        source_key="unverified", benchmark_code="NIFTY100", benchmark_source="niftyindices"
    )

    class Rows:
        def all(self):
            return [mapping]

    class Session:
        def scalars(self, _query):
            return Rows()

        def get(self, _model, _key):
            return SimpleNamespace(enabled=True, is_official=False, source_type="provider")

    scheme = SimpleNamespace(
        scheme_category="Large Cap", scheme_type="Equity", plan_type="direct", option_type="growth"
    )
    assert resolve_category_benchmark(Session(), scheme, date(2026, 11, 26)) is None


def test_benchmark_resolver_accepts_effective_mapping_with_official_registry_source():
    mapping = SimpleNamespace(
        source_key="nifty_official", benchmark_code="NIFTY100", benchmark_source="niftyindices"
    )

    class Rows:
        def all(self):
            return [mapping]

    class Session:
        def scalars(self, _query):
            return Rows()

        def get(self, _model, _key):
            return SimpleNamespace(enabled=True, is_official=True, source_type="official")

    scheme = SimpleNamespace(
        scheme_category="Large Cap", scheme_type="Equity", plan_type="direct", option_type="growth"
    )
    assert resolve_category_benchmark(Session(), scheme, date(2026, 11, 26)) is mapping


def test_actual_exposure_fully_redeemed_fund_is_excluded_from_valuation(monkeypatch):
    class Rows:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class Session:
        def scalars(self, query):
            entity = getattr(query, "column_descriptions", [{}])[0].get("entity")
            if entity is portfolio_module.MutualFundScheme:
                return Rows([SimpleNamespace(scheme_code=101, scheme_name="Redeemed")])
            if entity is portfolio_module.InvestorTransaction:
                return Rows([
                    SimpleNamespace(
                        transaction_type="purchase",
                        units=Decimal("10"),
                        transaction_date=date(2024, 1, 1),
                        transaction_id=1,
                    ),
                    SimpleNamespace(
                        transaction_type="redemption",
                        units=Decimal("10"),
                        transaction_date=date(2024, 2, 1),
                        transaction_id=2,
                    ),
                ])
            raise AssertionError("A zero-unit position must not query NAV or holdings.")

    result = portfolio_module.actual_portfolio_exposure(Session(), [101])
    assert result["total_valued_portfolio_inr"] == Decimal("0")
    assert result["valued_funds"] == []
    assert result["coverage"]["valued_fund_count"] == 0
    assert result["excluded_funds"][0]["scheme_code"] == 101
    assert "remaining units" in result["excluded_funds"][0]["reason"]


def test_actual_exposure_keeps_partially_redeemed_positive_units_for_nav():
    from decimal import Decimal

    class Rows:
        def __init__(self, rows): self.rows = rows
        def all(self): return self.rows

    class Session:
        def scalars(self, query):
            entity = query.column_descriptions[0]["entity"]
            if entity is portfolio_module.MutualFundScheme:
                return Rows([SimpleNamespace(scheme_code=102, scheme_name="Partial")])
            if entity is portfolio_module.InvestorTransaction:
                return Rows([
                    SimpleNamespace(
                        transaction_type="purchase",
                        units=Decimal("10"),
                        transaction_date=date(2024, 1, 1),
                        transaction_id=1,
                    ),
                    SimpleNamespace(
                        transaction_type="redemption",
                        units=Decimal("4"),
                        transaction_date=date(2024, 2, 1),
                        transaction_id=2,
                    ),
                ])
            raise AssertionError("Unexpected holdings query for no disclosed portfolio.")

        def scalar(self, query):
            assert query.column_descriptions[0]["entity"] is portfolio_module.NavReconciliation
            return SimpleNamespace(canonical_nav=Decimal("20"), nav_date=date(2026, 11, 25))

    result = portfolio_module.actual_portfolio_exposure(Session(), [102])
    assert result["total_valued_portfolio_inr"] == Decimal("120")
    assert result["coverage"]["valued_fund_count"] == 1
    assert result["valued_funds"][0]["units"] == Decimal("6")
    assert result["valued_funds"][0]["market_value_inr"] == Decimal("120")

def test_security_history_contract_is_bounded_typed_and_chronological():
    older = SimpleNamespace(
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        observation_id=1,
        last_price=10,
        change_pct=1,
        source_key="provider",
        source_url="https://provider.example/old",
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        content_hash="a",
        fundamentals_json={"pe_ratio": 10},
        fundamentals_as_of=date(2025, 12, 31),
        corporate_events_json=[],
        security_name="Example Co",
        isin=None,
        symbol="EX",
        exchange="NSE",
        day_high=11,
        day_low=9,
        volume=100,
        market_status="closed",
    )
    newer = SimpleNamespace(
        **{
            **older.__dict__,
            "observed_at": datetime(2026, 2, 1, tzinfo=UTC),
            "observation_id": 2,
            "content_hash": "b",
        }
    )
    class ScalarRows:
        def __init__(self, rows):
            self.rows = rows

        def first(self):
            return self.rows[0] if self.rows else None

        def all(self):
            return self.rows
    class Session:
        def scalars(self, query):
            if query.column_descriptions[0]["entity"] is SecurityMarketObservation:
                return ScalarRows([newer, older])
            return ScalarRows([])
    payload = security_profile(Session(), "EX", history_limit=2, history_type="all")
    assert [item["content_hash"] for item in payload["observation_history"]] == ["a", "b"]
    assert payload["observation_history_order"] == "ascending"
    assert payload["observation_history_type"] == "all"
    assert payload["observation_history"][0]["fundamentals"]["pe_ratio"] == 10


def test_security_history_rejects_unbounded_or_unknown_filters():
    with pytest.raises(ValueError, match="history_limit"):
        security_profile(None, "EX", history_limit=501)
    with pytest.raises(ValueError, match="history_type"):
        security_profile(None, "EX", history_type="everything")


def test_indian_as_of_day_includes_late_evening_exchange_observation():
    india_late = datetime(2026, 11, 25, 23, 45, tzinfo=ZoneInfo("Asia/Kolkata"))
    expected_cutoff = datetime(
        2026, 11, 25, 23, 59, 59, 999999, tzinfo=ZoneInfo("Asia/Kolkata")
    ).astimezone(timezone.utc)
    observed = SimpleNamespace(
        observed_at=india_late,
        observation_id=1,
        last_price=10,
        change_pct=0,
        source_key="provider",
        source_url=None,
        retrieved_at=india_late,
        content_hash="late-india-observation",
        fundamentals_json={},
        fundamentals_as_of=None,
        corporate_events_json=[],
        security_name="Example Co",
        isin=None,
        symbol="EX",
        exchange="NSE",
        day_high=10,
        day_low=10,
        volume=1,
        market_status="closed",
    )

    class ScalarRows:
        def first(self):
            return observed

        def all(self):
            return [observed]

    class Session:
        def scalars(self, query):
            rendered = str(query)
            if "security_market_observations" in rendered:
                # SQL bind parameters carry the date cutoff for all quote/history selectors.
                params = query.compile().params
                cutoff_values = [
                    value for value in params.values() if isinstance(value, datetime)
                ]
                assert expected_cutoff in cutoff_values
                return ScalarRows()
            return ScalarRowsEmpty()

    class ScalarRowsEmpty:
        def first(self):
            return None

        def all(self):
            return []

    payload = security_profile(Session(), "EX", as_of=date(2026, 11, 25))
    assert payload["availability"] == "available"
    assert payload["observation_history"][0]["content_hash"] == "late-india-observation"
