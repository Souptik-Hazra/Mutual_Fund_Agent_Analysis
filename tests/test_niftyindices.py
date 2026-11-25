"""Contract tests for Nifty Indices TRI/NTR ingestion."""
import json
from datetime import date
from decimal import Decimal

import httpx
import pytest

from mutual_fund_agent_analysis.data.providers.niftyindices import NiftyIndicesClient


def make_payload():
    return {
        "d": json.dumps(
            [
                {
                    "Index Name": "Nifty 50",
                    "Date": "25 Nov 2026",
                    "TotalReturnsIndex": "35793.78",
                    "NTR_Value": "31169.30",
                },
                {
                    "Index Name": "Nifty 50",
                    "Date": "24 Nov 2026",
                    "TotalReturnsIndex": "35600.00",
                    "NTR_Value": "31000.00",
                },
            ]
        )
    }


def test_niftyindices_tri_request_and_response_parsing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/getTotalReturnIndexString")
        assert request.headers["X-Requested-With"] == "XMLHttpRequest"
        assert request.headers["Referer"].endswith("/reports/historical-data")
        assert request.headers["User-Agent"].startswith("Mozilla/5.0")
        body = json.loads(request.content)
        assert "'name':'NIFTY 50'" in body["cinfo"]
        assert "'startDate':'24-Nov-2026'" in body["cinfo"]
        return httpx.Response(200, json=make_payload())

    with NiftyIndicesClient(transport=httpx.MockTransport(handler)) as client:
        result = client.get_history("NIFTY 50", date(2026, 11, 24), date(2026, 11, 25))

    assert result.benchmark_code == "NIFTY 50"
    assert result.benchmark_name == "Nifty 50"
    assert len(result.data) == 2
    assert result.data[0].date == date(2026, 11, 24)
    assert result.data[0].tri == Decimal("35600.00")
    assert result.data[0].ntr == Decimal("31000.00")
    assert result.raw_payload["provider"] == "niftyindices"


def test_niftyindices_rejects_empty_history() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"d": "[]"})

    with NiftyIndicesClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="No TRI observations"):
            client.get_history("NIFTY 50", date(2026, 11, 24), date(2026, 11, 25))


def test_niftyindices_rejects_duplicate_dates() -> None:
    rows = json.loads(make_payload()["d"])
    rows.append(rows[0])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"d": json.dumps(rows)})

    with NiftyIndicesClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="Duplicate benchmark observation date"):
            client.get_history("NIFTY 50", date(2026, 11, 24), date(2026, 11, 25))


def test_niftyindices_rejects_out_of_range_observation() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=make_payload())

    with NiftyIndicesClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="outside the requested range"):
            client.get_history("NIFTY 50", date(2026, 11, 25), date(2026, 11, 25))


def test_niftyindices_splits_ranges_into_max_365_day_chunks() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)["cinfo"]
        start = body.split("'startDate':'", 1)[1].split("'", 1)[0]
        end = body.split("'endDate':'", 1)[1].split("'", 1)[0]
        start_date = date.fromisoformat(
            __import__("datetime").datetime.strptime(start, "%d-%b-%Y").date().isoformat()
        )
        end_date = __import__("datetime").datetime.strptime(end, "%d-%b-%Y").date()
        assert (end_date - start_date).days <= 364
        requests.append(request)
        row = {
            "Index Name": "Nifty 50",
            "Date": end,
            "TotalReturnsIndex": "100.0",
            "NTR_Value": "90.0",
        }
        return httpx.Response(200, json={"d": json.dumps([row])})

    with NiftyIndicesClient(transport=httpx.MockTransport(handler)) as client:
        result = client.get_history("NIFTY 50", date(2024, 1, 1), date(2025, 1, 1))

    assert len(requests) == 2
    assert len(result.data) == 2
    assert result.raw_payload["request"]["chunk_count"] == 2


def test_niftyindices_retries_transient_server_error(monkeypatch) -> None:
    import mutual_fund_agent_analysis.data.providers.niftyindices as nifty_module

    calls = 0
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=make_payload())

    monkeypatch.setattr(nifty_module.time, "sleep", sleeps.append)
    with NiftyIndicesClient(transport=httpx.MockTransport(handler)) as client:
        result = client.get_history("NIFTY 50", date(2026, 11, 24), date(2026, 11, 25))

    assert len(result.data) == 2
    assert calls == 2
    assert sleeps == [0.5]
