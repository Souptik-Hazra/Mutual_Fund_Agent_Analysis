"""Contract tests for the AMFI historical NAV adapter."""

from datetime import date, datetime
from decimal import Decimal

import httpx
import pytest

from mutual_fund_agent_analysis.data.providers.amfi import AMFIClient

HISTORY_ROW = (
    "125497;HDFC Top 100 Fund - Direct Plan - Growth;"
    "INF179K01BE2;-;892.4560;0;0;26-Oct-2024"
)


def test_amfi_history_parses_historical_eight_column_layout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/DownloadNAVHistoryReport_Po.aspx")
        assert request.url.params["tp"] == "1"
        assert request.url.params["frmdt"] == "26-Oct-2024"
        return httpx.Response(200, text=HISTORY_ROW)

    with AMFIClient(transport=httpx.MockTransport(handler)) as client:
        response = client.get_nav_history(125497, date(2024, 10, 26), date(2024, 10, 26))

    assert response.meta.scheme_code == 125497
    assert response.meta.scheme_name.startswith("HDFC Top 100")
    assert response.data[0].date == date(2024, 10, 26)
    assert response.data[0].nav == Decimal("892.4560")
    assert response.raw_payload["provider"] == "amfi"
    assert HISTORY_ROW in response.raw_payload["raw_text"]


def test_amfi_history_parses_legacy_six_column_layout() -> None:
    report = (
        "Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;"
        "Scheme Name;Net Asset Value;Date\n"
        "125497;INF179K01BE2;-;HDFC Top 100 Fund;892.4560;26-Oct-2024"
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=report)

    with AMFIClient(transport=httpx.MockTransport(handler)) as client:
        response = client.get_nav_history(125497, date(2024, 10, 26), date(2024, 10, 26))

    assert response.meta.scheme_name == "HDFC Top 100 Fund"
    assert response.data[0].nav == Decimal("892.4560")


def test_amfi_skips_zero_nav_and_non_data_lines() -> None:
    report = (
        "Open Ended Schemes(Equity)\n"
        "HDFC Mutual Fund\n"
        "125497;HDFC Fund;ISIN;-;0.0000;0;0;26-Oct-2024\n"
        "125497;HDFC Fund;ISIN;-;10.2500;0;0;27-Oct-2024"
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=report)

    with AMFIClient(transport=httpx.MockTransport(handler)) as client:
        response = client.get_nav_history(125497, date(2024, 10, 26), date(2024, 10, 27))

    assert len(response.data) == 1
    assert response.data[0].nav == Decimal("10.2500")


def test_amfi_rejects_duplicate_dates() -> None:
    report = f"{HISTORY_ROW}\n{HISTORY_ROW}"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=report)

    with AMFIClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="duplicate NAV date"):
            client.get_nav_history(125497, date(2024, 10, 26), date(2024, 10, 26))


def test_amfi_chunks_long_date_ranges() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        chunk_date = datetime.strptime(request.url.params["frmdt"], "%d-%b-%Y").date()
        row = (
            "125497;HDFC Test Fund;ISIN;-;10.2500;0;0;"
            f"{chunk_date.strftime('%d-%b-%Y')}"
        )
        return httpx.Response(200, text=row)

    with AMFIClient(transport=httpx.MockTransport(handler), chunk_days=10) as client:
        response = client.get_nav_history(125497, date(2024, 10, 1), date(2024, 10, 20))

    assert len(requests) == 2
    assert len(response.data) == 2
