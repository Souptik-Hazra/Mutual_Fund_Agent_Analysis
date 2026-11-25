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
