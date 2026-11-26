"""Regression tests for advanced fund intelligence foundations."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import mutual_fund_agent_analysis.analytics.portfolio_intelligence as portfolio_module
from mutual_fund_agent_analysis.analytics.category_benchmarks import resolve_category_benchmark
from mutual_fund_agent_analysis.analytics.portfolio_intelligence import (
    _holding_weight_coverage,
    actual_portfolio_exposure,
)
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
                return Rows(
                    [
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
                    ]
                )
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
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class Session:
        def scalars(self, query):
            entity = query.column_descriptions[0]["entity"]
            if entity is portfolio_module.MutualFundScheme:
                return Rows([SimpleNamespace(scheme_code=102, scheme_name="Partial")])
            if entity is portfolio_module.InvestorTransaction:
                return Rows(
                    [
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
                    ]
                )
            raise AssertionError("Unexpected holdings query for no disclosed portfolio.")

        def get(self, model, _key):
            if model is portfolio_module.DataSource:
                return SimpleNamespace(
                    enabled=True,
                    source_key="amfi_official",
                    is_official=True,
                    source_type="official",
                    base_url="https://www.amfiindia.com",
                )
            if model is portfolio_module.EvidenceRecord:
                return SimpleNamespace(
                    evidence_id=1,
                    verification_status="verified",
                    canonical_url="https://www.amfiindia.com/disclosures",
                    retrieved_at=datetime(2026, 6, 30, tzinfo=UTC),
                )
            return None

        def scalar(self, query):
            entity = query.column_descriptions[0]["entity"]
            if entity is portfolio_module.NavReconciliation:
                return SimpleNamespace(
                    status="single_source",
                    canonical_nav=Decimal("20"),
                    nav_date=date(2026, 11, 25),
                    canonical_source="amfi",
                    evaluated_at=datetime(2026, 6, 30, tzinfo=UTC),
                )
            assert entity is portfolio_module.PortfolioSnapshot
            return None

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
    ).astimezone(UTC)
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
                cutoff_values = [value for value in params.values() if isinstance(value, datetime)]
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


def test_exposure_math():
    as_of = date(2026, 6, 30)
    snapshot = SimpleNamespace(
        snapshot_id=4,
        source_key="amfi_official",
        evidence_id=1,
        status="complete",
        effective_date=date(2026, 6, 1),
    )
    nav = SimpleNamespace(
        status="matched",
        canonical_nav=Decimal("20"),
        nav_date=date(2026, 6, 29),
        canonical_source="amfi",
        evaluated_at=datetime(2026, 6, 30, tzinfo=UTC),
    )
    holding = SimpleNamespace(
        isin="INE000A",
        security_key="INE000A",
        security_name="Example Bank",
        asset_class="equity",
        sector="Banks",
        weight_pct=Decimal("40"),
    )
    debt_holding = SimpleNamespace(
        isin=None,
        security_key="DEBT-1",
        security_name="Government Securities",
        asset_class="debt",
        sector="Government Bonds",
        weight_pct=Decimal("60"),
    )

    class Rows:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class Session:
        def scalars(self, query):
            entity = query.column_descriptions[0]["entity"]
            if entity is portfolio_module.MutualFundScheme:
                return Rows([SimpleNamespace(scheme_code=201, scheme_name="As-of Test Fund")])
            if entity is portfolio_module.InvestorTransaction:
                assert as_of in query.compile().params.values()
                transaction = SimpleNamespace(
                    transaction_type="purchase",
                    units=Decimal("10"),
                    transaction_date=date(2026, 1, 1),
                    transaction_id=1,
                )
                return Rows([transaction])
            if entity is portfolio_module.PortfolioHolding:
                return Rows([holding, debt_holding])
            raise AssertionError(entity)

        def get(self, model, _key):
            if model is portfolio_module.DataSource:
                return SimpleNamespace(
                    enabled=True,
                    source_key="amfi_official",
                    is_official=True,
                    source_type="official",
                    base_url="https://www.amfiindia.com",
                )
            if model is portfolio_module.EvidenceRecord:
                return SimpleNamespace(
                    evidence_id=1,
                    verification_status="verified",
                    canonical_url="https://www.amfiindia.com/disclosures",
                    retrieved_at=datetime(2026, 6, 30, tzinfo=UTC),
                )
            return None

        def scalar(self, query):
            entity = query.column_descriptions[0]["entity"]
            assert as_of in query.compile().params.values()
            if entity is portfolio_module.NavReconciliation:
                assert "status in" not in str(query).lower()
                return nav
            if entity is portfolio_module.PortfolioSnapshot:
                return snapshot
            raise AssertionError(entity)

    result = actual_portfolio_exposure(Session(), [201], as_of)
    assert result["as_of_date"] == as_of
    assert result["total_valued_portfolio_inr"] == Decimal("200")
    assert result["valued_funds"][0]["units"] == Decimal("10")
    assert result["valued_funds"][0]["market_value_inr"] == Decimal("200")
    assert result["valued_funds"][0]["nav_date"] == date(2026, 6, 29)
    assert result["equity_exposure"][0]["actual_exposure_inr"] == Decimal("80")
    assert result["equity_exposure"][0]["actual_portfolio_weight_pct"] == Decimal("40")
    assert result["sector_exposure"][0]["exposure_inr"] == Decimal("80")
    assert result["coverage"]["lookthrough_coverage_pct"] == Decimal("100")


def test_actual_exposure_refuses_latest_conflicted_nav_instead_of_older_accepted_row():
    as_of = date(2026, 6, 30)

    class Rows:
        def all(self):
            return [SimpleNamespace(scheme_code=202, scheme_name="Conflict Fund")]

    class TxnRows:
        def all(self):
            return [
                SimpleNamespace(
                    transaction_type="purchase",
                    units=Decimal("5"),
                    transaction_date=date(2026, 1, 1),
                    transaction_id=1,
                )
            ]

    class Session:
        def scalars(self, query):
            entity = query.column_descriptions[0]["entity"]
            if entity is portfolio_module.MutualFundScheme:
                return Rows()
            if entity is portfolio_module.InvestorTransaction:
                return TxnRows()
            raise AssertionError("Conflicted NAV must prevent holdings queries.")

        def scalar(self, query):
            assert query.column_descriptions[0]["entity"] is portfolio_module.NavReconciliation
            assert as_of in query.compile().params.values()
            assert "status in" not in str(query).lower()
            return SimpleNamespace(
                status="conflict",
                nav_date=date(2026, 6, 29),
                canonical_source="amfi",
                evaluated_at=datetime(2026, 6, 30, tzinfo=UTC),
                canonical_nav=Decimal("100"),
            )

    result = actual_portfolio_exposure(Session(), [202], as_of)
    assert result["total_valued_portfolio_inr"] == Decimal("0")
    assert result["valued_funds"] == []
    assert "falling back" in result["excluded_funds"][0]["reason"]
    assert result["data_quality_warnings"][0]["type"] == "nav_conflict"


def test_actual_exposure_filters_future_transactions_and_selects_historical_holdings():
    as_of = date(2026, 6, 30)
    transactions = [
        SimpleNamespace(
            transaction_type="purchase",
            units=Decimal("10"),
            transaction_date=date(2026, 1, 1),
            transaction_id=1,
        ),
        SimpleNamespace(
            transaction_type="purchase",
            units=Decimal("100"),
            transaction_date=date(2026, 7, 1),
            transaction_id=2,
        ),
        SimpleNamespace(
            transaction_type="redemption",
            units=Decimal("3"),
            transaction_date=date(2026, 7, 2),
            transaction_id=3,
        ),
    ]
    snapshot = SimpleNamespace(
        snapshot_id=5,
        source_key="amfi_official",
        evidence_id=1,
        status="complete",
        effective_date=date(2026, 6, 1),
    )
    nav = SimpleNamespace(
        status="single_source",
        canonical_nav=Decimal("10"),
        nav_date=date(2026, 6, 29),
        canonical_source="amfi",
        evaluated_at=datetime(2026, 6, 30, tzinfo=UTC),
    )
    holding = SimpleNamespace(
        isin="INE002B",
        security_key="INE002B",
        security_name="Example Co",
        asset_class="equity",
        sector="IT",
        weight_pct=Decimal("25"),
    )

    class Rows:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class Session:
        def scalars(self, query):
            entity = query.column_descriptions[0]["entity"]
            if entity is portfolio_module.MutualFundScheme:
                return Rows([SimpleNamespace(scheme_code=203, scheme_name="Future Row Fund")])
            if entity is portfolio_module.InvestorTransaction:
                assert as_of in query.compile().params.values()
                return Rows([row for row in transactions if row.transaction_date <= as_of])
            if entity is portfolio_module.PortfolioHolding:
                return Rows([holding])
            raise AssertionError(entity)

        def get(self, model, _key):
            if model is portfolio_module.DataSource:
                return SimpleNamespace(
                    enabled=True,
                    source_key="amfi_official",
                    is_official=True,
                    source_type="official",
                    base_url="https://www.amfiindia.com",
                )
            if model is portfolio_module.EvidenceRecord:
                return SimpleNamespace(
                    evidence_id=1,
                    verification_status="verified",
                    canonical_url="https://www.amfiindia.com/disclosures",
                    retrieved_at=datetime(2026, 6, 30, tzinfo=UTC),
                )
            return None

        def scalar(self, query):
            entity = query.column_descriptions[0]["entity"]
            assert as_of in query.compile().params.values()
            if entity is portfolio_module.NavReconciliation:
                return nav
            if entity is portfolio_module.PortfolioSnapshot:
                return snapshot
            raise AssertionError(entity)

    result = actual_portfolio_exposure(Session(), [203], as_of)
    assert result["valued_funds"][0]["units"] == Decimal("10")
    assert result["total_valued_portfolio_inr"] == Decimal("100")
    assert result["equity_exposure"][0]["actual_exposure_inr"] == Decimal("25")
    assert result["equity_exposure"][0]["fund_exposures"][0]["holdings_as_of"] == date(2026, 6, 1)


def test_actual_exposure_marks_partial_disclosure_as_incomplete_coverage():
    as_of = date(2026, 6, 30)
    snapshot = SimpleNamespace(
        snapshot_id=6,
        source_key="amfi_official",
        evidence_id=1,
        status="partial",
        effective_date=date(2026, 5, 31),
    )
    holding = SimpleNamespace(
        isin="INE003C",
        security_key="INE003C",
        security_name="Partial Co",
        asset_class="equity",
        sector="Health",
        weight_pct=Decimal("50"),
    )

    class Rows:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class Session:
        def scalars(self, query):
            entity = query.column_descriptions[0]["entity"]
            if entity is portfolio_module.MutualFundScheme:
                return Rows(
                    [SimpleNamespace(scheme_code=204, scheme_name="Partial Disclosure Fund")]
                )
            if entity is portfolio_module.InvestorTransaction:
                return Rows(
                    [
                        SimpleNamespace(
                            transaction_type="purchase",
                            units=Decimal("4"),
                            transaction_date=date(2026, 1, 1),
                            transaction_id=1,
                        )
                    ]
                )
            if entity is portfolio_module.PortfolioHolding:
                return Rows([holding])
            raise AssertionError(entity)

        def get(self, model, _key):
            if model is portfolio_module.DataSource:
                return SimpleNamespace(
                    enabled=True,
                    source_key="amfi_official",
                    is_official=True,
                    source_type="official",
                    base_url="https://www.amfiindia.com",
                )
            if model is portfolio_module.EvidenceRecord:
                return SimpleNamespace(
                    evidence_id=1,
                    verification_status="verified",
                    canonical_url="https://www.amfiindia.com/disclosures",
                    retrieved_at=datetime(2026, 6, 30, tzinfo=UTC),
                )
            return None

        def scalar(self, query):
            entity = query.column_descriptions[0]["entity"]
            if entity is portfolio_module.NavReconciliation:
                return SimpleNamespace(
                    status="matched",
                    canonical_nav=Decimal("25"),
                    nav_date=date(2026, 6, 29),
                    canonical_source="amfi",
                    evaluated_at=datetime(2026, 6, 30, tzinfo=UTC),
                )
            if entity is portfolio_module.PortfolioSnapshot:
                assert as_of in query.compile().params.values()
                return snapshot
            raise AssertionError(entity)

    result = actual_portfolio_exposure(Session(), [204], as_of)
    assert result["total_valued_portfolio_inr"] == Decimal("100")
    assert result["equity_exposure"][0]["actual_exposure_inr"] == Decimal("50")
    assert result["coverage"]["lookthrough_coverage_pct"] == Decimal("0")
    assert result["coverage"]["is_complete"] is False
    assert result["data_quality_warnings"][0]["type"] == "partial_holdings"


def test_complete_snapshot_with_missing_weights_is_not_full_lookthrough():
    holdings = [
        SimpleNamespace(weight_pct=Decimal("70")),
        SimpleNamespace(weight_pct=None),
        SimpleNamespace(weight_pct=Decimal("20")),
    ]
    missing, total, complete = _holding_weight_coverage(holdings)
    assert missing == 1
    assert total == Decimal("90")
    assert complete is False


def test_complete_snapshot_requires_approximately_full_weight_total():
    holdings = [
        SimpleNamespace(weight_pct=Decimal("50")),
        SimpleNamespace(weight_pct=Decimal("50")),
    ]
    missing, total, complete = _holding_weight_coverage(holdings)
    assert missing == 0
    assert total == Decimal("100")
    assert complete is True


@pytest.mark.parametrize(
    ("snapshot_status", "evidence_status", "weights", "expected_coverage"),
    [
        ("complete", "verified", [Decimal("70"), None, Decimal("20")], Decimal("0")),
        ("complete", "unverified", [Decimal("100")], Decimal("0")),
        ("partial", "verified", [Decimal("100")], Decimal("0")),
        ("complete", "verified", [Decimal("100")], Decimal("100")),
    ],
)
def test_actual_exposure_coverage_requires_complete_weighted_verified_disclosure(
    snapshot_status, evidence_status, weights, expected_coverage
):
    as_of = date(2026, 6, 30)
    snapshot = SimpleNamespace(
        snapshot_id=99,
        source_key="amfi_official",
        evidence_id=99,
        status=snapshot_status,
        effective_date=date(2026, 5, 31),
    )
    holdings = [
        SimpleNamespace(
            isin=f"INE000{index}A",
            security_key=f"INE000{index}A",
            security_name=f"Coverage Holding {index}",
            asset_class="equity",
            sector="Financials",
            weight_pct=weight,
        )
        for index, weight in enumerate(weights)
    ]

    class Rows:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class Session:
        def scalars(self, query):
            entity = query.column_descriptions[0]["entity"]
            if entity is portfolio_module.MutualFundScheme:
                return Rows([SimpleNamespace(scheme_code=299, scheme_name="Coverage Fund")])
            if entity is portfolio_module.InvestorTransaction:
                return Rows([
                    SimpleNamespace(
                        transaction_type="purchase",
                        units=Decimal("4"),
                        transaction_date=date(2026, 1, 1),
                        transaction_id=1,
                    )
                ])
            if entity is portfolio_module.PortfolioHolding:
                return Rows(holdings)
            raise AssertionError(entity)

        def get(self, model, _key):
            if model is portfolio_module.DataSource:
                return SimpleNamespace(
                    enabled=True,
                    source_key="amfi_official",
                    is_official=True,
                    source_type="official",
                    base_url="https://www.amfiindia.com",
                )
            if model is portfolio_module.EvidenceRecord:
                return SimpleNamespace(
                    evidence_id=99,
                    verification_status=evidence_status,
                    canonical_url="https://www.amfiindia.com/disclosures",
                    retrieved_at=datetime(2026, 6, 30, tzinfo=UTC),
                )
            return None

        def scalar(self, query):
            entity = query.column_descriptions[0]["entity"]
            if entity is portfolio_module.NavReconciliation:
                return SimpleNamespace(
                    status="matched",
                    canonical_nav=Decimal("25"),
                    nav_date=date(2026, 6, 29),
                    canonical_source="amfi",
                    evaluated_at=datetime(2026, 6, 30, tzinfo=UTC),
                )
            if entity is portfolio_module.PortfolioSnapshot:
                return snapshot
            raise AssertionError(entity)

    result = actual_portfolio_exposure(Session(), [299], as_of)
    assert result["total_valued_portfolio_inr"] == Decimal("100")
    assert result["coverage"]["lookthrough_coverage_pct"] == expected_coverage
    assert result["coverage"]["lookthrough_eligible_fund_count"] == int(
        expected_coverage == Decimal("100")
    )
    assert result["coverage"]["lookthrough_incomplete_fund_count"] == int(
        expected_coverage == Decimal("0")
    )
    assert result["coverage"]["disclosed_weight_pct_by_fund"]["299"] == sum(
        (weight for weight in weights if weight is not None), Decimal("0")
    )
    assert bool(result["equity_exposure"]) is True
    assert result["coverage"]["is_complete"] is (
        snapshot_status == "complete"
        and evidence_status == "verified"
        and weights == [Decimal("100")]
    )
