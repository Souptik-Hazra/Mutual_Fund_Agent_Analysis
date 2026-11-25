"""Contract tests for the MFAPI adapter."""

from datetime import date
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from mutual_fund_agent_analysis.data.providers.mfapi import MFAPIClient, MFAPINavPoint


def test_scheme_search_validates_provider_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/mf/search"
        assert request.url.params["q"] == "HDFC"
        return httpx.Response(
            200,
            json=[{"schemeCode": 125497, "schemeName": "HDFC Top 100 Fund - Direct Plan - Growth"}],
        )

    with MFAPIClient(transport=httpx.MockTransport(handler)) as client:
        results = client.search_schemes(" HDFC ")

    assert len(results) == 1
    assert results[0].scheme_code == 125497


def test_nav_history_parses_provider_date_and_decimal() -> None:
    payload = {
        "meta": {
            "scheme_code": 125497,
            "scheme_name": "HDFC Top 100 Fund - Direct Plan - Growth",
            "fund_house": "HDFC Mutual Fund",
        },
        "data": [{"date": "26-10-2024", "nav": "892.45600"}],
        "status": "SUCCESS",
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with MFAPIClient(transport=httpx.MockTransport(handler)) as client:
        response = client.get_nav_history(125497)

    assert response.data[0].date == date(2024, 10, 26)
    assert response.data[0].nav == Decimal("892.45600")
    assert response.raw_payload is not None
    assert response.raw_payload["data"][0]["nav"] == "892.45600"
    assert "raw_payload" not in response.model_dump()


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "not-a-number"])
def test_nav_point_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValidationError):
        MFAPINavPoint.model_validate({"date": "26-10-2024", "nav": value})


def test_nav_history_rejects_scheme_code_mismatch() -> None:
    payload = {
        "meta": {"scheme_code": 999, "scheme_name": "Different scheme"},
        "data": [{"date": "26-10-2024", "nav": "10.0"}],
        "status": "SUCCESS",
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with MFAPIClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="does not match"):
            client.get_nav_history(125497)


def test_rate_limit_respects_retry_after_header(monkeypatch) -> None:
    import mutual_fund_agent_analysis.data.providers.mfapi as mfapi_module

    sleeps: list[float] = []
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0.25"})
        return httpx.Response(200, json=[])

    monkeypatch.setattr(mfapi_module.time, "sleep", sleeps.append)
    with MFAPIClient(transport=httpx.MockTransport(handler)) as client:
        assert client.search_schemes("HDFC") == []

    assert calls == 2
    assert sleeps == [0.25]
