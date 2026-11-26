"""Regression tests for advanced fund intelligence foundations."""

from datetime import date
from types import SimpleNamespace

import pytest

from mutual_fund_agent_analysis.analytics.category_benchmarks import resolve_category_benchmark
from mutual_fund_agent_analysis.analytics.portfolio_intelligence import actual_portfolio_exposure
from mutual_fund_agent_analysis.data.providers.twelvedata import TwelveDataClient


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
    from decimal import Decimal
    from types import SimpleNamespace
    import mutual_fund_agent_analysis.analytics.portfolio_intelligence as module

    class Rows:
        def __init__(self, rows): self.rows = rows
        def all(self): return self.rows

    class Session:
        def scalars(self, query):
            entity = getattr(query, "column_descriptions", [{}])[0].get("entity")
            if entity is module.MutualFundScheme:
                return Rows([SimpleNamespace(scheme_code=101, scheme_name="Redeemed")])
            if entity is module.InvestorTransaction:
                return Rows([
                    SimpleNamespace(transaction_type="purchase", units=Decimal("10"), transaction_date=date(2024,1,1), transaction_id=1),
                    SimpleNamespace(transaction_type="redemption", units=Decimal("10"), transaction_date=date(2024,2,1), transaction_id=2),
                ])
            raise AssertionError("A zero-unit position must not query NAV or holdings.")

    result = module.actual_portfolio_exposure(Session(), [101])
    assert result["total_valued_portfolio_inr"] == Decimal("0")
    assert result["valued_funds"] == []
    assert result["coverage"]["valued_fund_count"] == 0
    assert result["excluded_funds"][0]["scheme_code"] == 101
    assert "remaining units" in result["excluded_funds"][0]["reason"]


def test_actual_exposure_keeps_partially_redeemed_positive_units_for_nav(monkeypatch):
    from decimal import Decimal
    import mutual_fund_agent_analysis.analytics.portfolio_intelligence as module

    class Rows:
        def __init__(self, rows): self.rows = rows
        def all(self): return self.rows

    class Session:
        def scalars(self, query):
            entity = query.column_descriptions[0]["entity"]
            if entity is module.MutualFundScheme:
                return Rows([SimpleNamespace(scheme_code=102, scheme_name="Partial")])
            if entity is module.InvestorTransaction:
                return Rows([
                    SimpleNamespace(transaction_type="purchase", units=Decimal("10"), transaction_date=date(2024,1,1), transaction_id=1),
                    SimpleNamespace(transaction_type="redemption", units=Decimal("4"), transaction_date=date(2024,2,1), transaction_id=2),
                ])
            raise AssertionError("Unexpected holdings query for no disclosed portfolio.")

        def scalar(self, query):
            assert query.column_descriptions[0]["entity"] is module.NavReconciliation
            return SimpleNamespace(canonical_nav=Decimal("20"), nav_date=date(2026,11,25))

    result = module.actual_portfolio_exposure(Session(), [102])
    assert result["total_valued_portfolio_inr"] == Decimal("120")
    assert result["coverage"]["valued_fund_count"] == 1
    assert result["valued_funds"][0]["units"] == Decimal("6")
    assert result["valued_funds"][0]["market_value_inr"] == Decimal("120")
