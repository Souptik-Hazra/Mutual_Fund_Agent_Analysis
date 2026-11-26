"""Regression tests for IDCW-aware fund and benchmark return bases."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from mutual_fund_agent_analysis.analytics import service
from mutual_fund_agent_analysis.models.financial import DistributionCoverageAttestation
from mutual_fund_agent_analysis.models.intelligence import DataSource
from mutual_fund_agent_analysis.models.scheme import MutualFundScheme


NAVS = [
    service.PricePoint(date(2024, 1, 1), Decimal("100")),
    service.PricePoint(date(2024, 1, 2), Decimal("98")),
    service.PricePoint(date(2024, 1, 3), Decimal("99")),
]


class DistributionSession:
    def __init__(self, option_type="idcw_reinvestment", attestation=True, distribution=True):
        self.scheme = SimpleNamespace(scheme_code=77, option_type=option_type)
        self.attestation = (
            SimpleNamespace(
                scheme_code=77,
                source_key="amc_official",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 3),
                coverage_complete=True,
                verification_status="verified",
            )
            if attestation else None
        )
        self.distribution = (
            SimpleNamespace(
                scheme_code=77,
                source_key="amc_official",
                option_type=option_type,
                ex_date=date(2024, 1, 2),
                amount_per_unit=Decimal("3"),
                status="active",
                verification_status="verified",
            )
            if distribution else None
        )

    def get(self, model, key):
        if model is MutualFundScheme:
            return self.scheme
        if model is DataSource:
            return SimpleNamespace(enabled=True, is_official=True)
        return None

    def scalars(self, statement):
        sql = str(statement)
        if "distribution_coverage_attestations" in sql:
            rows = [self.attestation] if self.attestation else []
        elif "distribution_observations" in sql:
            rows = [self.distribution] if self.distribution else []
        else:
            rows = []

        class Result:
            def all(self):
                return rows

        return Result()


def test_verified_idcw_reinvestment_uses_known_answer_total_return_series(monkeypatch):
    monkeypatch.setattr(service, "load_fund_prices", lambda *_args, **_kwargs: (NAVS, ()))
    points, conflicts, basis, coverage, reason = service.load_fund_return_prices(
        DistributionSession(), 77
    )
    expected_final = Decimal("101") * Decimal("99") / Decimal("98")
    assert points[0].value == Decimal("100")
    assert points[1].value == Decimal("101")
    assert abs(points[2].value - expected_final) < Decimal("1e-25")
    assert conflicts == ()
    assert basis == "idcw_reinvested_total_return"
    assert coverage == "verified_complete"
    assert reason is None


def test_idcw_without_official_coverage_falls_back_to_nav_and_marks_incomplete(monkeypatch):
    monkeypatch.setattr(service, "load_fund_prices", lambda *_args, **_kwargs: (NAVS, ()))
    points, _, basis, coverage, reason = service.load_fund_return_prices(
        DistributionSession(attestation=False), 77
    )
    assert points == NAVS
    assert basis == "nav_only_excludes_idcw"
    assert coverage == "incomplete"
    assert "No verified" in reason


def test_idcw_nav_only_does_not_calculate_benchmark_relative_metrics(monkeypatch):
    monkeypatch.setattr(
        service,
        "load_fund_return_prices",
        lambda *_args, **_kwargs: (
            NAVS, (), "nav_only_excludes_idcw", "incomplete", "Official coverage is missing."
        ),
    )

    def unexpected_benchmark_load(*_args, **_kwargs):
        pytest.fail("Benchmark observations must not be loaded for unverified IDCW NAV-only returns.")

    monkeypatch.setattr(service, "load_benchmark_prices", unexpected_benchmark_load)
    report = service.analyze_fund(
        SimpleNamespace(), 77, benchmark_code="NIFTY TRI",
        start_date=NAVS[0].date, end_date=NAVS[-1].date,
    )
    assert report.benchmark is None
    assert report.benchmark_code is None
    assert report.benchmark_return_basis is None
    assert report.return_basis == "nav_only_excludes_idcw"
    assert report.distribution_coverage_status == "incomplete"
    assert "Official coverage is missing" in report.benchmark_unavailable_reason


def test_growth_scheme_uses_nav_series_against_tri(monkeypatch):
    monkeypatch.setattr(
        service,
        "load_fund_return_prices",
        lambda *_args, **_kwargs: (
            NAVS, (), "growth_nav_total_return", "not_required", None
        ),
    )
    benchmark = [
        service.PricePoint(date(2024, 1, 1), Decimal("100")),
        service.PricePoint(date(2024, 1, 2), Decimal("99")),
        service.PricePoint(date(2024, 1, 3), Decimal("100")),
    ]
    monkeypatch.setattr(service, "load_benchmark_prices", lambda *_args, **_kwargs: benchmark)
    report = service.analyze_fund(
        SimpleNamespace(), 77, benchmark_code="NIFTY TRI",
        start_date=NAVS[0].date, end_date=NAVS[-1].date,
    )
    assert report.return_basis == "growth_nav_total_return"
    assert report.benchmark_return_basis == "tri"
    assert report.benchmark is not None


def test_mixed_growth_and_idcw_comparison_is_rejected_before_ranking():
    class Session:
        def scalars(self, _statement):
            class Result:
                def all(self):
                    return [
                        SimpleNamespace(scheme_code=1, option_type="growth"),
                        SimpleNamespace(scheme_code=2, option_type="idcw_reinvestment"),
                    ]
            return Result()

    with pytest.raises(ValueError, match="Mixed Growth and IDCW"):
        service.compare_funds(Session(), [1, 2])
