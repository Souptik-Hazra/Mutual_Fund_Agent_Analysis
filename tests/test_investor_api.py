from fastapi.testclient import TestClient
from unittest.mock import Mock

from mutual_fund_agent_analysis.api.routes import funds
from mutual_fund_agent_analysis.database.session import get_db
from mutual_fund_agent_analysis.main import create_app


def _client(session=None):
    app = create_app()

    def dependency():
        yield session

    if session is not None:
        app.dependency_overrides[get_db] = dependency
    return TestClient(app)


def test_investor_routes_are_registered():
    paths = {route.path for route in funds.router.routes if hasattr(route, "path")}
    assert "/schemes/{scheme_code}/sip-simulation" in paths
    assert "/schemes/{scheme_code}/transactions" in paths
    assert "/transactions/{transaction_id}" in paths
    assert "/schemes/{scheme_code}/investor-returns" in paths
    assert "/schemes/{scheme_code}/active-risk" in paths


def test_transaction_contract_requires_units_for_purchase():
    response = _client().post(
        "/api/v1/schemes/100/transactions",
        json={
            "transaction_date": "2024-01-01",
            "transaction_type": "purchase",
            "amount": "1000",
        },
    )
    assert response.status_code == 422


def test_transaction_contract_rejects_units_for_dividend():
    response = _client().post(
        "/api/v1/schemes/100/transactions",
        json={
            "transaction_date": "2024-01-01",
            "transaction_type": "dividend_payout",
            "amount": "10",
            "units": "1",
        },
    )
    assert response.status_code == 422


def test_transaction_contract_rejects_unknown_currency():
    response = _client().post(
        "/api/v1/schemes/100/transactions",
        json={
            "transaction_date": "2024-01-01",
            "transaction_type": "purchase",
            "amount": "1000",
            "units": "10",
            "currency": "USD",
        },
    )
    assert response.status_code == 422


def test_sip_simulation_request_rejects_reversed_dates():
    response = _client().post(
        "/api/v1/schemes/100/sip-simulation",
        json={
            "start_date": "2024-02-01",
            "end_date": "2024-01-01",
            "valuation_date": "2024-03-01",
            "monthly_amount": "1000",
        },
    )
    assert response.status_code == 422


def test_sip_simulation_rejects_zero_amount():
    response = _client().post(
        "/api/v1/schemes/100/sip-simulation",
        json={
            "start_date": "2024-01-01",
            "end_date": "2024-02-01",
            "valuation_date": "2024-03-01",
            "monthly_amount": "0",
        },
    )
    assert response.status_code == 422


def test_transaction_list_rejects_reversed_date_range():
    session = Mock()
    session.get.return_value = object()
    response = _client(session).get(
        "/api/v1/schemes/100/transactions",
        params={"start_date": "2025-01-01", "end_date": "2024-01-01"},
    )
    assert response.status_code == 422
