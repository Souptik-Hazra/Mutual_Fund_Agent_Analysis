"""Offline validation of public-provider audit metrics and gated quote probes."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from pydantic import SecretStr

from mutual_fund_agent_analysis.cli import audit_local


def test_provider_quality_counts_duplicates_order_and_out_of_window_dates():
    points = [
        SimpleNamespace(date=date(2026, 1, 2)),
        SimpleNamespace(date=date(2026, 1, 1)),
        SimpleNamespace(date=date(2026, 1, 1)),
        SimpleNamespace(date=date(2025, 12, 31)),
    ]
    result = audit_local._observation_quality(points, date(2026, 1, 1), date(2026, 1, 2))
    assert result == {
        "duplicate_date_count": 1,
        "out_of_order_pair_count": 2,
        "out_of_window_count": 1,
    }


def test_nav_reconciliation_reports_provider_gaps_and_conflicts():
    result = audit_local._reconcile_nav(
        {"2026-01-01": "10.0000", "2026-01-02": "11.0000"},
        {"2026-01-01": "10.0000", "2026-01-03": "12.0000"},
    )
    assert result["matched_date_count"] == 1
    assert result["mfapi_only_date_count"] == 1
    assert result["amfi_only_date_count"] == 1
    assert result["conflict_count"] == 0


def test_nav_reconciliation_flags_values_outside_decimal_tolerance():
    result = audit_local._reconcile_nav(
        {"2026-01-01": "10.0000"},
        {"2026-01-01": "10.0100"},
    )
    assert result["conflict_count"] == 1
    assert Decimal(result["conflicts"][0]["absolute_difference"]) == Decimal("0.0100")


def test_twelve_data_probe_is_blocked_without_api_key(monkeypatch):
    monkeypatch.setattr(
        audit_local,
        "get_settings",
        lambda: SimpleNamespace(
            twelve_data_api_key=None,
            twelve_data_exchange_access_confirmed=True,
        ),
    )
    result = audit_local.probe_twelve_data("INFY", "NSE")
    assert result["status"] == "blocked"
    assert "API key" in result["reason"]


def test_twelve_data_probe_requires_explicit_exchange_access_confirmation(monkeypatch):
    monkeypatch.setattr(
        audit_local,
        "get_settings",
        lambda: SimpleNamespace(
            twelve_data_api_key=SecretStr("test-secret"),
            twelve_data_exchange_access_confirmed=False,
        ),
    )
    result = audit_local.probe_twelve_data("INFY", "NSE")
    assert result["status"] == "blocked"
    assert "access" in result["reason"]


def test_twelve_data_probe_reports_only_the_requested_quote_scope(monkeypatch):
    class StubClient:
        def __init__(self, _api_key):
            self.closed = False

        def get_quote(self, symbol, exchange):
            assert (symbol, exchange) == ("INFY", "NSE")
            return SimpleNamespace(
                symbol="INFY",
                exchange="NSE",
                observed_at=SimpleNamespace(isoformat=lambda: "2026-11-26T10:00:00+00:00"),
                price=Decimal("1500.25"),
                change_pct=Decimal("1.2"),
                market_status="trading",
            )

        def close(self):
            self.closed = True

    monkeypatch.setattr(
        audit_local,
        "get_settings",
        lambda: SimpleNamespace(
            twelve_data_api_key=SecretStr("test-secret"),
            twelve_data_exchange_access_confirmed=True,
        ),
    )
    monkeypatch.setattr(audit_local, "TwelveDataClient", StubClient)
    result = audit_local.probe_twelve_data(" infy ", " nse ")
    assert result["status"] == "success"
    assert result["coverage_scope"] == "single quote endpoint only"
    assert "No historical price" in result["limitations"][1]
