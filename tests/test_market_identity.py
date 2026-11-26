"""Exact-identity tests for Twelve Data quote ingestion."""

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from mutual_fund_agent_analysis.api.routes.market_data import (
    QuoteSyncRequest,
    _resolve_security_identity,
)
from mutual_fund_agent_analysis.data.providers.twelvedata import TwelveDataClient
from mutual_fund_agent_analysis.models.intelligence import DataSource, ResearchEntity

ISIN = "INE009A01021"


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeHTTPClient:
    def __init__(self, payload):
        self.payload = payload

    def get(self, _url, params):
        self.params = params
        return FakeResponse(self.payload)

    def close(self):
        return None


def quote_payload(**overrides):
    payload = {
        "symbol": "INFY",
        "exchange": "NSE",
        "datetime": "2026-11-25 10:00:00+05:30",
        "close": "1500.25",
        "percent_change": "1.2",
        "is_market_open": True,
    }
    payload.update(overrides)
    return payload


def test_quote_request_requires_security_key_to_match_exact_isin_or_symbol():
    with pytest.raises(ValidationError, match="must exactly match"):
        QuoteSyncRequest(
            security_key="INFOSYS",
            security_name="Infosys Limited",
            symbol="INFY",
            exchange="NSE",
            isin=ISIN,
        )


def test_quote_request_normalizes_exchange_symbol_and_isin():
    request = QuoteSyncRequest(
        security_key=ISIN.lower(),
        security_name="Infosys Limited",
        symbol="infy",
        exchange="nse",
        isin=ISIN.lower(),
    )
    assert request.security_key == ISIN
    assert request.symbol == "INFY"
    assert request.exchange == "NSE"
    assert request.isin == ISIN


def test_quote_parser_accepts_exact_symbol_and_exchange():
    client = TwelveDataClient("test-key", client=FakeHTTPClient(quote_payload()))
    quote = client.get_quote("INFY", "NSE")
    assert quote.symbol == "INFY"
    assert quote.exchange == "NSE"
    assert quote.price.as_tuple().digits == (1, 5, 0, 0, 2, 5)


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"symbol": "TCS"}, "different symbol"),
        ({"exchange": "BSE"}, "different exchange"),
        ({"symbol": ""}, "omitted the returned symbol"),
        ({"exchange": ""}, "omitted the returned exchange"),
    ],
)
def test_quote_parser_rejects_mismatched_or_missing_identity(overrides, message):
    client = TwelveDataClient("test-key", client=FakeHTTPClient(quote_payload(**overrides)))
    with pytest.raises(ValueError, match=message):
        client.get_quote("INFY", "NSE")


def test_security_identity_requires_unique_official_isin_and_exchange_symbol_mappings():
    entity = SimpleNamespace(
        entity_id=44, entity_type="company", status="active", canonical_name="Infosys Limited"
    )
    isin_mapping = SimpleNamespace(entity_id=44, source_key="official_registry")
    symbol_mapping = SimpleNamespace(entity_id=44, source_key="official_registry")

    class Rows:
        def __init__(self, values):
            self.values = values

        def all(self):
            return self.values

    class Session:
        def __init__(self, isin_rows=None, symbol_rows=None, official=True):
            self.results = [
                isin_rows if isin_rows is not None else [isin_mapping],
                symbol_rows if symbol_rows is not None else [symbol_mapping],
            ]
            self.official = official

        def scalars(self, _statement):
            return Rows(self.results.pop(0))

        def get(self, model, _key):
            if model is ResearchEntity:
                return entity
            if model is DataSource:
                return SimpleNamespace(
                    enabled=True, is_official=self.official, source_type="official"
                )
            return None

    request = QuoteSyncRequest(
        security_key=ISIN,
        security_name="Infosys Limited",
        symbol="INFY",
        exchange="NSE",
        isin=ISIN,
    )
    assert _resolve_security_identity(Session(), request, date(2026, 11, 25)) is entity


def test_security_identity_rejects_missing_isin_mapping():
    class Rows:
        def all(self):
            return []

    class Session:
        def scalars(self, _statement):
            return Rows()

    request = QuoteSyncRequest(
        security_key=ISIN,
        security_name="Infosys Limited",
        symbol="INFY",
        exchange="NSE",
        isin=ISIN,
    )
    with pytest.raises(HTTPException) as error:
        _resolve_security_identity(Session(), request, date(2026, 11, 25))
    assert error.value.status_code == 422


def test_security_identity_rejects_ambiguous_isin_mapping():
    class Rows:
        def all(self):
            return [SimpleNamespace(entity_id=1), SimpleNamespace(entity_id=2)]

    class Session:
        def scalars(self, _statement):
            return Rows()

    request = QuoteSyncRequest(
        security_key=ISIN,
        security_name="Infosys Limited",
        symbol="INFY",
        exchange="NSE",
        isin=ISIN,
    )
    with pytest.raises(HTTPException) as error:
        _resolve_security_identity(Session(), request, date(2026, 11, 25))
    assert error.value.status_code == 409


def test_security_identity_rejects_unofficial_mapping_provenance():
    entity = SimpleNamespace(
        entity_id=44, entity_type="company", status="active", canonical_name="Infosys Limited"
    )
    isin_mapping = SimpleNamespace(entity_id=44, source_key="unofficial")

    class Rows:
        def all(self):
            return [isin_mapping]

    class Session:
        def scalars(self, _statement):
            return Rows()

        def get(self, model, _key):
            if model is ResearchEntity:
                return entity
            if model is DataSource:
                return SimpleNamespace(enabled=True, is_official=False, source_type="provider")
            return None

    request = QuoteSyncRequest(
        security_key=ISIN,
        security_name="Infosys Limited",
        symbol="INFY",
        exchange="NSE",
        isin=ISIN,
    )
    with pytest.raises(HTTPException) as error:
        _resolve_security_identity(Session(), request, date(2026, 11, 25))
    assert error.value.status_code == 422


def test_security_identity_rejects_exchange_symbol_mapped_to_another_entity():
    entity = SimpleNamespace(
        entity_id=44, entity_type="company", status="active", canonical_name="Infosys Limited"
    )
    isin_mapping = SimpleNamespace(entity_id=44, source_key="official_registry")
    other_entity_symbol = SimpleNamespace(entity_id=99, source_key="official_registry")

    class Rows:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class Session:
        def __init__(self):
            self.calls = 0

        def scalars(self, _statement):
            self.calls += 1
            return Rows([isin_mapping] if self.calls == 1 else [other_entity_symbol])

        def get(self, model, _key):
            if model is ResearchEntity:
                return entity
            if model is DataSource:
                return SimpleNamespace(enabled=True, is_official=True, source_type="official")
            return None

    request = QuoteSyncRequest(
        security_key=ISIN,
        security_name="Infosys Limited",
        symbol="INFY",
        exchange="NSE",
        isin=ISIN,
    )
    with pytest.raises(HTTPException) as error:
        _resolve_security_identity(Session(), request, date(2026, 11, 25))
    assert error.value.status_code == 409
