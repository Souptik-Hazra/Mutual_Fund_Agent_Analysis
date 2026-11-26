"""Tests for the fund explorer and analysis API contracts."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from mutual_fund_agent_analysis.api.routes import funds
from mutual_fund_agent_analysis.database.session import get_db
from mutual_fund_agent_analysis.main import create_app


def _override_db(session):
    def dependency():
        yield session

    app = create_app()
    app.dependency_overrides[get_db] = dependency
    return app


def test_list_schemes_filters_and_paginates() -> None:
    session = Mock()
    session.scalar.return_value = 1
    session.scalars.return_value.all.return_value = [
        SimpleNamespace(
            scheme_code=123,
            scheme_name="Example Direct Growth",
            fund_house="Example AMC",
            scheme_type="Open Ended",
            scheme_category="Equity",
            isin_growth="INF000000001",
            isin_div_reinvestment=None,
        )
    ]
    response = TestClient(_override_db(session)).get(
        "/api/v1/schemes?q=Example&plan=direct&option=growth&limit=10&offset=0"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["scheme_code"] == 123
    assert body["items"][0]["scheme_name"] == "Example Direct Growth"


def test_scheme_discovery_uses_validated_provider_response(monkeypatch) -> None:
    class StubClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def search_schemes(self, query):
            assert query == "HDFC"
            return [SimpleNamespace(scheme_code=100, scheme_name="HDFC Example Fund")]

    monkeypatch.setattr(funds, "MFAPIClient", StubClient)
    response = TestClient(create_app()).get("/api/v1/schemes/discover?q=HDFC")
    assert response.status_code == 200
    assert response.json()["items"] == [{"scheme_code": 100, "scheme_name": "HDFC Example Fund"}]


def test_scheme_detail_includes_latest_reconciliation() -> None:
    session = Mock()
    session.get.return_value = SimpleNamespace(
        scheme_code=100,
        scheme_name="Example Fund",
        fund_house="Example AMC",
        scheme_type="Open Ended",
        scheme_category="Equity",
        isin_growth="INF000000001",
        isin_div_reinvestment=None,
    )
    session.scalars.return_value.first.return_value = SimpleNamespace(
        canonical_nav=Decimal("42.25"),
        nav_date=date(2026, 11, 25),
        status="matched",
        canonical_source="amfi",
    )
    response = TestClient(_override_db(session)).get("/api/v1/schemes/100")
    assert response.status_code == 200
    assert response.json()["latest_nav"] == "42.25"
    assert response.json()["reconciliation_status"] == "matched"


def test_scheme_detail_returns_404_when_not_ingested() -> None:
    session = Mock()
    session.get.return_value = None
    response = TestClient(_override_db(session)).get("/api/v1/schemes/100")
    assert response.status_code == 404


def test_comparison_request_rejects_duplicate_scheme_codes() -> None:
    response = TestClient(_override_db(Mock())).post(
        "/api/v1/schemes/compare", json={"scheme_codes": [100, 100]}
    )
    assert response.status_code == 422


def test_comparison_request_rejects_more_than_five_schemes() -> None:
    response = TestClient(_override_db(Mock())).post(
        "/api/v1/schemes/compare", json={"scheme_codes": [1, 2, 3, 4, 5, 6]}
    )
    assert response.status_code == 422


def test_comparison_request_rejects_reversed_date_range() -> None:
    response = TestClient(_override_db(Mock())).post(
        "/api/v1/schemes/compare",
        json={
            "scheme_codes": [100, 200],
            "start_date": "2025-01-01",
            "end_date": "2024-01-01",
        },
    )
    assert response.status_code == 422


def test_comparison_uses_exact_shared_dates(monkeypatch) -> None:
    from mutual_fund_agent_analysis.analytics import service as analytics_service
    from mutual_fund_agent_analysis.analytics.service import compare_funds

    session = Mock()
    session.scalars.return_value.all.return_value = [
        SimpleNamespace(scheme_code=100, option_type="growth"),
        SimpleNamespace(scheme_code=200, option_type="growth"),
    ]
    points = {
        100: [
            analytics_service.PricePoint(date(2024, 1, 1), Decimal("100")),
            analytics_service.PricePoint(date(2024, 1, 2), Decimal("110")),
            analytics_service.PricePoint(date(2024, 1, 3), Decimal("121")),
        ],
        200: [
            analytics_service.PricePoint(date(2024, 1, 1), Decimal("50")),
            analytics_service.PricePoint(date(2024, 1, 3), Decimal("55")),
            analytics_service.PricePoint(date(2024, 1, 4), Decimal("60")),
        ],
    }
    monkeypatch.setattr(
        analytics_service,
        "load_fund_return_prices",
        lambda _session, code, *_args, **_kwargs: (
            points[code], (), "growth_nav_total_return", "not_required", None
        ),
    )
    result = compare_funds(session, [100, 200])
    assert result.observation_count == 2
    assert result.start_date == date(2024, 1, 1)
    assert result.end_date == date(2024, 1, 3)
    assert [fund.observation_count for fund in result.funds] == [2, 2]
    assert [fund.absolute_return for fund in result.funds] == [
        Decimal("0.21"),
        Decimal("0.1"),
    ]
    assert result.comparability_warnings == ()


def test_single_fund_endpoint_serializes_analytics_report(monkeypatch) -> None:
    from mutual_fund_agent_analysis.analytics.coverage import ReturnCoverage
    from mutual_fund_agent_analysis.analytics.drawdown import DrawdownMetrics
    from mutual_fund_agent_analysis.analytics.risk import RiskMetrics
    from mutual_fund_agent_analysis.analytics.service import FundAnalyticsReport

    coverage = ReturnCoverage(
        observation_count=1,
        median_interval_days=None,
        maximum_interval_days=None,
        long_gap_count=0,
        estimated_coverage_ratio=None,
        inferred_frequency="insufficient",
    )
    report = FundAnalyticsReport(
        scheme_code=100,
        observation_count=2,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 2),
        absolute_return=Decimal("0.1"),
        cagr=Decimal("1"),
        rolling_returns=(),
        calendar_year_returns=(),
        risk=RiskMetrics(1, None, None, None, None, coverage),
        drawdown=DrawdownMetrics(
            Decimal("0"), date(2024, 1, 1), date(2024, 1, 1), None, 0, None, 0
        ),
        benchmark=None,
        annual_risk_free_rate=Decimal("0"),
        periods_per_year=252,
        benchmark_code=None,
        benchmark_source=None,
        nav_conflict_dates=(),
        calendar_year_as_of_date=None,
    )
    monkeypatch.setattr(funds, "analyze_fund", lambda *args, **kwargs: report)
    response = TestClient(_override_db(Mock())).get("/api/v1/schemes/100/analytics")
    assert response.status_code == 200
    assert response.json()["absolute_return"] == "0.1"
    assert response.json()["observation_count"] == 2


def test_comparison_rejects_growth_and_idcw_option_mismatch(monkeypatch):
    from mutual_fund_agent_analysis.analytics import service as analytics_service

    session = Mock()
    session.scalars.return_value.all.return_value = [
        SimpleNamespace(scheme_code=100, option_type="growth"),
        SimpleNamespace(scheme_code=200, option_type="idcw_payout"),
    ]
    monkeypatch.setattr(
        analytics_service,
        "load_fund_prices",
        lambda *_args, **_kwargs: (
            [
                analytics_service.PricePoint(date(2024, 1, 1), Decimal("100")),
                analytics_service.PricePoint(date(2024, 1, 2), Decimal("101")),
            ],
            (),
        ),
    )
    with pytest.raises(ValueError, match="like-for-like scheme options"):
        analytics_service.compare_funds(session, [100, 200])


def test_idcw_same_option_comparison_warns_nav_only_distributions_excluded(monkeypatch):
    from mutual_fund_agent_analysis.analytics import service as analytics_service

    session = Mock()
    session.scalars.return_value.all.return_value = [
        SimpleNamespace(scheme_code=100, option_type="idcw_reinvestment"),
        SimpleNamespace(scheme_code=200, option_type="idcw_reinvestment"),
    ]
    points = [
        analytics_service.PricePoint(date(2024, 1, 1), Decimal("100")),
        analytics_service.PricePoint(date(2024, 1, 2), Decimal("101")),
    ]
    monkeypatch.setattr(
        analytics_service,
        "load_fund_return_prices",
        lambda _session, _code, *_args, **_kwargs: (
            points, (), "nav_only_excludes_idcw", "incomplete", "No official coverage."
        ),
    )
    result = analytics_service.compare_funds(session, [100, 200])
    assert result.comparability_warnings
    assert "NAV-only" in result.comparability_warnings[0]
    assert "exclude IDCW distributions" in result.comparability_warnings[0]
