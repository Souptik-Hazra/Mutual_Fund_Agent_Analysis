"""Tests for category, cross-fund and underlying-security intelligence contracts."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from mutual_fund_agent_analysis.analytics import fund_intelligence
from mutual_fund_agent_analysis.analytics.security_intelligence import security_profile
from mutual_fund_agent_analysis.api.routes.fund_intelligence import (
    FundCompareRequest,
    MarketObservationRequest,
    _latest_market_observation,
    fund_equity_status,
    router,
)


def test_fund_intelligence_routes_are_registered():
    paths = {route.path for route in router.routes if hasattr(route, "path")}
    assert "/fund-intelligence/schemes/{scheme_code}/category" in paths
    assert "/fund-intelligence/compare" in paths
    assert "/fund-intelligence/schemes/{scheme_code}/equity-status" in paths
    assert "/fund-intelligence/securities/{security_key}/market-status" in paths
    assert "/fund-intelligence/market-observations" in paths


def test_fund_compare_rejects_boolean_scheme_codes():
    with pytest.raises(ValidationError):
        FundCompareRequest(scheme_codes=[True, 2])


def test_market_observation_requires_timezone_aware_timestamp():
    with pytest.raises(ValidationError, match="timezone"):
        MarketObservationRequest(
            security_key="INE009A01021",
            security_name="Example Limited",
            source_key="market_provider",
            observed_at=datetime(2026, 11, 25, 10, 0),
            last_price=Decimal("100"),
        )


def test_market_observation_rejects_future_timestamp():
    with pytest.raises(ValidationError, match="future"):
        MarketObservationRequest(
            security_key="INE009A01021",
            security_name="Example Limited",
            source_key="market_provider",
            observed_at=datetime.now(UTC) + timedelta(minutes=1),
            last_price=Decimal("100"),
        )


def test_market_observation_rejects_non_positive_price():
    with pytest.raises(ValidationError):
        MarketObservationRequest(
            security_key="INE009A01021",
            security_name="Example Limited",
            source_key="market_provider",
            observed_at=datetime.now(UTC),
            last_price=Decimal("0"),
        )


def test_category_analysis_uses_exact_category_and_option_cohort(monkeypatch):
    selected = type(
        "Scheme",
        (),
        {
            "scheme_code": 1,
            "scheme_category": "Large Cap",
            "scheme_type": None,
            "plan_type": "direct",
            "option_type": "growth",
        },
    )()
    peers = [
        type(
            "Peer",
            (),
            {
                "scheme_code": 1,
                "scheme_name": "Selected",
                "fund_house": "AMC A",
                "scheme_category": "Large Cap",
            },
        )(),
        type(
            "Peer",
            (),
            {
                "scheme_code": 2,
                "scheme_name": "Peer",
                "fund_house": "AMC B",
                "scheme_category": "Large Cap",
            },
        )(),
    ]

    class Rows:
        def all(self):
            return peers

    class Session:
        statement = None

        def get(self, _model, _key):
            return selected

        def scalars(self, statement):
            self.statement = statement
            return Rows()

        def execute(self, _statement):
            class Bounds:
                @staticmethod
                def all():
                    return [
                        (1, date(2025, 1, 1), date(2026, 1, 1)),
                        (2, date(2025, 1, 1), date(2026, 1, 1)),
                    ]

            return Bounds()

    def fake_analyze(_session, code, **_kwargs):
        return type(
            "Report",
            (),
            {
                "cagr": Decimal("0.12") if code == 1 else Decimal("0.10"),
                "absolute_return": Decimal("0.25"),
                "risk": type(
                    "Risk",
                    (),
                    {
                        "annualized_volatility": Decimal("0.15"),
                        "sharpe_ratio": Decimal("0.8") if code == 1 else Decimal("0.7"),
                    },
                )(),
                "drawdown": type("Drawdown", (), {"maximum_drawdown": Decimal("-0.10")})(),
                "benchmark": None,
                "observation_count": 250,
                "start_date": datetime(2025, 1, 1).date(),
                "end_date": datetime(2026, 1, 1).date(),
                "base100_series": (
                    (datetime(2025, 1, 1).date(), Decimal("100")),
                    (datetime(2026, 1, 1).date(), Decimal("112")),
                ),
                "return_basis": "growth_nav_total_return",
                "distribution_coverage_status": "not_required",
                "benchmark_unavailable_reason": None,
            },
        )()

    monkeypatch.setattr(fund_intelligence, "analyze_fund", fake_analyze)
    session = Session()
    result = fund_intelligence.analyze_category_peers(session, 1)
    assert "mutual_fund_schemes.scheme_type IS NULL" in str(
        session.statement.compile(compile_kwargs={"literal_binds": True})
    )
    assert result["peer_count"] == 2
    assert result["selected_fund"]["cagr_rank"] == 1
    assert result["selected_fund"]["sharpe_ratio_rank"] == 1
    limited = fund_intelligence.analyze_category_peers(Session(), 1, max_peers=1)
    assert limited["cohort_truncated"] is True
    assert limited["peer_count"] == 1


def test_category_rank_assigns_equal_metrics_the_same_rank(monkeypatch):
    selected = SimpleNamespace(
        scheme_code=1,
        scheme_category="Large Cap",
        scheme_type="Open Ended",
        plan_type="direct",
        option_type="growth",
    )
    peers = [
        SimpleNamespace(
            scheme_code=code,
            scheme_name=f"Fund {code}",
            fund_house="AMC",
            scheme_category="Large Cap",
        )
        for code in (1, 2)
    ]

    class Rows:
        def all(self):
            return peers

    class Session:
        def get(self, _model, _key):
            return selected

        def scalars(self, _statement):
            return Rows()

        def execute(self, _statement):
            class Bounds:
                @staticmethod
                def all():
                    return [
                        (1, date(2025, 1, 1), date(2026, 1, 1)),
                        (2, date(2025, 1, 1), date(2026, 1, 1)),
                    ]

            return Bounds()

    def tied_report(_session, _code, **_kwargs):
        return SimpleNamespace(
            cagr=Decimal("0.10"),
            absolute_return=Decimal("0.10"),
            risk=SimpleNamespace(
                annualized_volatility=Decimal("0.10"),
                sharpe_ratio=Decimal("0.50"),
            ),
            drawdown=SimpleNamespace(maximum_drawdown=Decimal("-0.10")),
            benchmark=None,
            benchmark_unavailable_reason=None,
            return_basis="growth_nav_total_return",
            distribution_coverage_status="not_required",
            observation_count=2,
            start_date=date(2025, 1, 1),
            end_date=date(2026, 1, 1),
            base100_series=((date(2025, 1, 1), Decimal("100")), (date(2026, 1, 1), Decimal("110"))),
        )

    monkeypatch.setattr(fund_intelligence, "analyze_fund", tied_report)
    result = fund_intelligence.analyze_category_peers(Session(), 1)
    assert {row["cagr_rank"] for row in result["peers"]} == {1}
    assert {row["sharpe_ratio_rank"] for row in result["peers"]} == {1}


def test_multi_fund_equity_overlap_uses_isin_and_equal_fund_weights():
    from types import SimpleNamespace

    snapshots = {
        1: SimpleNamespace(
            snapshot_id=11,
            effective_date=datetime(2026, 10, 31).date(),
            status="complete",
        ),
        2: SimpleNamespace(
            snapshot_id=22,
            effective_date=datetime(2026, 9, 30).date(),
            status="partial",
        ),
    }
    schemes = [
        SimpleNamespace(scheme_code=1, scheme_name="Fund A"),
        SimpleNamespace(scheme_code=2, scheme_name="Fund B"),
    ]
    holdings = {
        11: [
            SimpleNamespace(
                security_key="ALPHA",
                isin="INE000A01001",
                security_name="Alpha Ltd",
                weight_pct=Decimal("5"),
            ),
            SimpleNamespace(
                security_key="BETA",
                isin="INE000B01001",
                security_name="Beta Ltd",
                weight_pct=Decimal("4"),
            ),
        ],
        22: [
            SimpleNamespace(
                security_key="ALPHA-ALT",
                isin="INE000A01001",
                security_name="Alpha Limited",
                weight_pct=Decimal("3"),
            )
        ],
    }

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

        def first(self):
            return self.rows[0] if self.rows else None

    class Session:
        def __init__(self):
            self.calls = 0

        def get(self, model, _key):
            if model.__name__ == "DataSource":
                return SimpleNamespace(
                    display_name="AMC Disclosures",
                    enabled=True,
                    is_official=True,
                    source_type="official",
                    base_url="https://amc.example",
                )
            if model.__name__ == "EvidenceRecord":
                return SimpleNamespace(
                    canonical_url="https://amc.example/portfolio.pdf",
                    verification_status="verified",
                    retrieved_at=datetime(2026, 11, 1, tzinfo=UTC),
                )
            return None

        def scalars(self, _statement):
            self.calls += 1
            if self.calls == 1:
                return Result(schemes)
            if self.calls in {2, 4}:
                code = 1 if self.calls == 2 else 2
                return Result([snapshots[code]])
            return Result(holdings[11] if self.calls == 3 else holdings[22])

    result = fund_intelligence.compare_disclosed_equity(Session(), [1, 2])
    pair = result["pairwise_overlap"][0]
    assert pair["common_security_count"] == 1
    assert pair["overlap_pct"] == Decimal("3")
    assert pair["overlap_is_lower_bound"] is True
    assert pair["disclosure_status_b"] == "partial"
    assert result["has_partial_disclosures"] is True
    assert result["aggregate_exposure_is_incomplete"] is True
    alpha = next(
        row for row in result["aggregated_equity_exposure"] if row["security_key"] == "INE000A01001"
    )
    assert alpha["equal_weight_exposure_pct"] == Decimal("4")
    assert alpha["funds_present"] == 2


def test_category_ranking_excludes_peer_outside_common_observation_window(monkeypatch):
    from types import SimpleNamespace

    selected = SimpleNamespace(
        scheme_code=1,
        scheme_category="Large Cap",
        scheme_type="Open Ended",
        plan_type="direct",
        option_type="growth",
    )
    peers = [
        SimpleNamespace(
            scheme_code=1, scheme_name="Selected", fund_house="AMC A", scheme_category="Large Cap"
        ),
        SimpleNamespace(
            scheme_code=2,
            scheme_name="Short history",
            fund_house="AMC B",
            scheme_category="Large Cap",
        ),
    ]

    class Rows:
        def all(self):
            return peers

    class Session:
        def get(self, _model, _key):
            return selected

        def scalars(self, _statement):
            return Rows()

        def execute(self, _statement):
            class Bounds:
                @staticmethod
                def all():
                    return [
                        (1, date(2025, 1, 1), date(2026, 1, 1)),
                        (2, date(2024, 1, 1), date(2026, 1, 1)),
                    ]

            return Bounds()

    def report(code, start, end):
        return SimpleNamespace(
            cagr=Decimal("0.1"),
            absolute_return=Decimal("0.1"),
            risk=SimpleNamespace(annualized_volatility=Decimal("0.1"), sharpe_ratio=Decimal("0.5")),
            drawdown=SimpleNamespace(maximum_drawdown=Decimal("-0.1")),
            benchmark=None,
            benchmark_unavailable_reason=None,
            return_basis="growth_nav_total_return",
            distribution_coverage_status="not_required",
            observation_count=2,
            start_date=start,
            end_date=end,
            base100_series=((start, Decimal("100")), (end, Decimal("110"))),
        )

    def fake_analyze(_session, code, start_date=None, end_date=None, **_kwargs):
        if code == 1:
            return report(1, date(2025, 1, 1), date(2026, 1, 1))
        return report(2, date(2024, 1, 1), date(2026, 1, 1))

    monkeypatch.setattr(fund_intelligence, "analyze_fund", fake_analyze)
    result = fund_intelligence.analyze_category_peers(Session(), 1)
    assert result["peer_count"] == 1
    assert result["excluded_peer_count"] == 1
    assert result["excluded_peers"][0]["scheme_code"] == 2
    assert "common window" in result["excluded_peers"][0]["reason"]


def test_security_profile_keeps_latest_fundamentals_and_events_outside_quote_history():
    observed = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    quote = SimpleNamespace(
        security_key="INE009A01021",
        isin="INE009A01021",
        security_name="Example Limited",
        symbol="EXAMPLE",
        exchange="NSE",
        observed_at=observed,
        last_price=Decimal("150"),
        change_pct=Decimal("1.5"),
        day_high=Decimal("152"),
        day_low=Decimal("148"),
        volume=1000,
        market_status="trading",
        retrieved_at=observed,
        source_key="quote_provider",
        source_url="https://provider.example/quote",
        content_hash="quote-hash",
        fundamentals_json={},
        corporate_events_json=[],
    )
    fundamentals = SimpleNamespace(
        fundamentals_as_of=date(2026, 10, 31),
        fundamentals_json={"pe_ratio": Decimal("20")},
        observed_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
        source_key="fundamentals_provider",
        source_url="https://provider.example/fundamentals",
        retrieved_at=observed,
    )
    events = SimpleNamespace(
        corporate_events_json=[{"title": "Board meeting", "status": "scheduled"}],
        observed_at=datetime(2026, 10, 15, 10, 0, tzinfo=UTC),
        source_key="events_provider",
        source_url="https://provider.example/events",
        retrieved_at=observed,
    )

    class Rows:
        def __init__(self, rows):
            self.rows = rows

        def first(self):
            return self.rows[0] if self.rows else None

        def all(self):
            return self.rows

    class Session:
        def __init__(self):
            self.calls = 0

        def scalars(self, _statement):
            self.calls += 1
            return Rows(
                {
                    1: [quote],
                    2: [quote],
                    3: [fundamentals],
                    4: [events],
                    5: [],
                }[self.calls]
            )

    result = security_profile(Session(), "INE009A01021", as_of=date(2026, 11, 30))
    assert result["market"]["last_price"] == Decimal("150")
    assert result["fundamentals"]["metrics"] == {"pe_ratio": Decimal("20")}
    assert result["fundamentals"]["source_key"] == "fundamentals_provider"
    assert result["corporate_events"][0]["source_key"] == "events_provider"


def test_latest_market_observation_applies_historical_as_of_filter():
    class Rows:
        def first(self):
            return None

    class Session:
        statement = None

        def scalars(self, statement):
            self.statement = statement
            return Rows()

    session = Session()
    _latest_market_observation(session, "INE009A01021", as_of=date(2026, 10, 31))
    sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "security_market_observations.observed_at <=" in sql


def test_equity_status_uses_historical_market_observations():
    snapshot = SimpleNamespace(
        snapshot_id=10,
        effective_date=date(2026, 10, 31),
        status="complete",
    )
    holding = SimpleNamespace(
        security_key="INE009A01021",
        isin=None,
        security_name="Example Limited",
        sector="Technology",
        weight_pct=Decimal("5"),
        asset_class="equity",
    )
    observed = datetime(2026, 10, 30, 10, 0, tzinfo=UTC)
    market = SimpleNamespace(
        security_key="INE009A01021",
        isin=None,
        security_name="Example Limited",
        symbol="EXAMPLE",
        exchange="NSE",
        source_key="quote_provider",
        source_url="https://provider.example/quote",
        observed_at=observed,
        retrieved_at=observed,
        fundamentals_as_of=None,
        last_price=Decimal("150"),
        change_pct=Decimal("1.5"),
        day_high=Decimal("152"),
        day_low=Decimal("148"),
        volume=1000,
        market_status="trading",
        fundamentals_json={},
        corporate_events_json=[],
    )

    class Rows:
        def __init__(self, rows):
            self.rows = rows

        def first(self):
            return self.rows[0] if self.rows else None

        def all(self):
            return self.rows

    class Session:
        def __init__(self):
            self.calls = 0
            self.statements = []

        def scalars(self, statement):
            self.calls += 1
            self.statements.append(statement)
            return Rows({1: [snapshot], 2: [holding], 3: [market]}[self.calls])

    session = Session()
    result = fund_equity_status(10001, session, as_of=date(2026, 10, 31))
    market_query = str(session.statements[2].compile(compile_kwargs={"literal_binds": True}))
    assert "security_market_observations.observed_at <=" in market_query
    assert result["market_data_as_of"] == date(2026, 10, 31)
    assert result["items"][0]["market_data"]["observed_at"] == observed
