import asyncio
import io
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mutual_fund_agent_analysis.api.routes import research as research_routes
from mutual_fund_agent_analysis.api.routes.market_data import (
    _validate_registered_source_url,
)
from mutual_fund_agent_analysis.api.schemas.research import (
    EventInput,
    HoldingInput,
    PortfolioImportRequest,
    SocialPostInput,
)
from mutual_fund_agent_analysis.data.providers.rss import fetch_feed
from mutual_fund_agent_analysis.data.providers.twelvedata import TwelveDataClient
from mutual_fund_agent_analysis.data.services.research_intelligence import (
    _portfolio_content_hash,
    portfolio_payload,
    source_social_retention_days,
    split_document,
)
from mutual_fund_agent_analysis.database.base import Base
from mutual_fund_agent_analysis.models import DataSource, DocumentChunk, ResearchDocument


def test_document_split_preserves_page_markers_and_overlap():
    text = "[Page 1]\n" + ("alpha " * 350) + "\n[Page 2]\n" + ("beta " * 350)
    chunks = split_document(text, chunk_size=500, overlap=80)
    assert len(chunks) > 2
    assert any("[Page 1]" in chunk for chunk in chunks)
    assert any("[Page 2]" in chunk for chunk in chunks)


def test_portfolio_import_rejects_duplicate_security_asset_class():
    holding = HoldingInput(
        security_key="INE123A01016",
        isin="INE123A01016",
        security_name="Example Ltd",
        asset_class="equity",
        weight_pct=Decimal("4.5"),
    )
    with pytest.raises(ValidationError):
        PortfolioImportRequest(
            scheme_code=100,
            source_key="amc_disclosures",
            effective_date=date(2026, 10, 31),
            content_hash="a" * 64,
            holdings=[holding, holding],
        )


def test_portfolio_import_requires_effective_date_and_content_hash():
    with pytest.raises(ValidationError):
        PortfolioImportRequest(
            scheme_code=100,
            source_key="amc_disclosures",
            content_hash="bad",
            holdings=[
                {
                    "security_key": "INE123A01016",
                    "security_name": "Example Ltd",
                    "asset_class": "equity",
                }
            ],
        )


def test_social_post_requires_retention_expiry():
    with pytest.raises(ValidationError):
        SocialPostInput(
            source_key="reddit",
            external_id="abc123",
            content_hash="a" * 64,
        )


def test_event_status_is_explicit_and_validated():
    event = EventInput(
        source_key="nse",
        title="Quarterly results announced",
        event_type="results",
        status="reported",
        published_at=datetime(2026, 11, 1, tzinfo=UTC),
    )
    assert event.status == "reported"
    with pytest.raises(ValidationError):
        EventInput(source_key="nse", title="Test event", status="confirmed-ish")


def test_rss_adapter_rejects_non_allowlisted_host_before_network_call():
    with pytest.raises(ValueError, match="registered source host"):
        fetch_feed("https://example.com/feed.xml", "www.nseindia.com")


def test_social_retention_uses_source_override_and_global_fallback():
    source = DataSource(
        source_key="reddit",
        display_name="Reddit",
        source_type="social",
        authority_tier=5,
        is_official=False,
        enabled=False,
        terms_url="https://terms.example/reddit",
        metadata_json={
            "retention_days": 12,
            "terms_reviewed": True,
            "access_confirmed": True,
            "reviewed_at": "2026-11-25",
        },
    )
    assert source_social_retention_days(source, 30) == 12

    source.metadata_json = {}
    assert source_social_retention_days(source, 30) == 30

    source.metadata_json = ["invalid"]
    with pytest.raises(ValueError, match="JSON object"):
        source_social_retention_days(source, 30)


@pytest.mark.parametrize("value", [0, -1, 366, True, 12.5, "12"])
def test_social_retention_rejects_invalid_source_override(value):
    source = DataSource(
        source_key="x",
        display_name="X",
        source_type="social",
        authority_tier=5,
        is_official=False,
        enabled=False,
        metadata_json={"retention_days": value},
    )
    with pytest.raises(ValueError, match="retention_days"):
        source_social_retention_days(source, 30)


def test_social_retention_rejects_invalid_global_fallback():
    source = DataSource(
        source_key="reddit",
        display_name="Reddit",
        source_type="social",
        authority_tier=5,
        is_official=False,
        enabled=False,
        metadata_json={},
    )
    with pytest.raises(ValueError, match="Default social retention"):
        source_social_retention_days(source, 0)


def test_social_collection_applies_source_specific_expiry(monkeypatch):
    from types import SimpleNamespace

    source = DataSource(
        source_key="reddit",
        display_name="Reddit",
        source_type="social",
        authority_tier=5,
        is_official=False,
        enabled=True,
        terms_url="https://terms.example/reddit",
        metadata_json={
            "retention_days": 12,
            "terms_reviewed": True,
            "access_confirmed": True,
            "reviewed_at": "2026-11-25",
        },
    )

    class StubSession:
        def get(self, _model, _key):
            return source

    captured = []
    monkeypatch.setattr(
        research_routes,
        "search_reddit",
        lambda _query, _limit: [
            {
                "external_id": "retention-route-test",
                "text_excerpt": "A public market discussion",
                "published_at": datetime.now(UTC),
                "engagement_count": 1,
                "metadata": {},
            }
        ],
    )
    monkeypatch.setattr(
        research_routes,
        "create_social_post",
        lambda _session, payload: captured.append(payload),
    )
    monkeypatch.setattr(
        research_routes,
        "get_settings",
        lambda: SimpleNamespace(social_retention_days=30),
    )

    result = research_routes.collect_social_posts(
        source="reddit", q="mutual funds", session=StubSession(), limit=1
    )
    remaining = captured[0].expires_at - datetime.now(UTC)
    assert result["persisted"] == 1
    assert timedelta(days=12) - timedelta(seconds=2) < remaining <= timedelta(days=12)


def test_standard_portfolio_disclosure_headers_are_normalized_without_guessing_asset_class():
    from mutual_fund_agent_analysis.api.routes.research import _normalize_portfolio_row

    row = _normalize_portfolio_row(
        {
            "ISIN": "INE123A01016",
            "Name of Instrument": "Example Ltd",
            "Industry": "Banks",
            "% to NAV": "2.50",
            "Mkt Value (Rs in Lakhs)": "12.75",
        }
    )
    assert row["isin"] == "INE123A01016"
    assert row["security_name"] == "Example Ltd"
    assert row["sector"] == "Banks"
    assert row["%_to_nav"] == "2.50"
    assert row["market_value_source_unit"] == "INR lakhs"
    assert row["market_value"] == Decimal("1275000.00")
    assert "asset_class" not in row


def test_portfolio_kind_column_is_used_only_as_an_explicit_asset_class():
    from mutual_fund_agent_analysis.api.routes.research import _normalize_portfolio_row

    assert _normalize_portfolio_row({"Kind": "debt"})["asset_class"] == "debt"


def test_pdf_extraction_rejects_malformed_and_encrypted_documents():
    import fitz

    from mutual_fund_agent_analysis.data.services.research_intelligence import extract_pdf_text

    with pytest.raises(ValueError, match="malformed"):
        extract_pdf_text(b"not a PDF document")

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "A protected financial document.")
    encrypted = document.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="secret",
    )
    document.close()
    with pytest.raises(ValueError, match="Password-protected"):
        extract_pdf_text(encrypted)


def test_event_revision_archiver_preserves_prior_source_state():
    from types import SimpleNamespace

    from mutual_fund_agent_analysis.data.services.research_intelligence import (
        archive_market_event_revision,
    )

    event = SimpleNamespace(
        event_id=7,
        source_key="exchange",
        external_id="notice-42",
        evidence_id=None,
        related_entity_id=9,
        title="Original disclosure",
        summary="Initial summary",
        event_type="results",
        status="reported",
        event_date=date(2026, 10, 1),
        published_at=datetime(2026, 10, 1, tzinfo=UTC),
        canonical_url="https://exchange.example/notice-42",
        confidence=Decimal("0.5"),
        metadata_json={"revision": "original"},
    )

    class StubSession:
        def __init__(self):
            self.added = []

        def scalar(self, _statement):
            return 1

        def add(self, value):
            self.added.append(value)

        def flush(self):
            return None

    session = StubSession()
    revision = archive_market_event_revision(session, event, reason="source_correction")
    assert revision.revision_number == 2
    assert revision.revision_reason == "source_correction"
    assert revision.snapshot["title"] == "Original disclosure"
    assert revision.snapshot["status"] == "reported"
    assert revision.snapshot["event_date"] == "2026-10-01"
    assert session.added == [revision]


def test_portfolio_metrics_require_complete_weights_before_hhi_is_reported():
    from types import SimpleNamespace

    snapshot = SimpleNamespace(
        snapshot_id=3,
        scheme_code=100,
        source_key="amc_disclosures",
        effective_date=date(2026, 10, 31),
        published_at=datetime(2026, 11, 5, tzinfo=UTC),
        status="complete",
        content_hash="a" * 64,
        total_market_value=Decimal("1000000"),
        document_url="https://amc.example/portfolio.csv",
    )
    rows = [
        SimpleNamespace(
            weight_pct=Decimal("60"),
            asset_class="equity",
            sector="Banks",
            security_key="INE1",
            security_name="Bank One",
            isin="INE000000001",
            quantity=Decimal("10"),
            market_value=Decimal("600000"),
            currency="INR",
        ),
        SimpleNamespace(
            weight_pct=Decimal("40"),
            asset_class="equity",
            sector="Technology",
            security_key="INE2",
            security_name="Tech Two",
            isin="INE000000002",
            quantity=Decimal("20"),
            market_value=Decimal("400000"),
            currency="INR",
        ),
    ]

    class StubSession:
        def scalars(self, _statement):
            return SimpleNamespace(all=lambda: rows)

    result = portfolio_payload(StubSession(), snapshot)
    assert result["weight_coverage_pct"] == Decimal("100")
    assert result["hhi_0_to_1"] == Decimal("0.52")
    assert result["hhi_coverage_sufficient"] is True
    assert result["sector_allocation"][0]["sector"] == "Banks"

    rows[1].weight_pct = None
    incomplete = portfolio_payload(StubSession(), snapshot)
    assert incomplete["weight_coverage_pct"] == Decimal("60")
    assert incomplete["hhi_0_to_1"] is None
    assert incomplete["hhi_coverage_sufficient"] is False


def test_rss_adapter_rejects_entity_declarations_and_non_https_links(monkeypatch):
    import httpx

    class FakeResponse:
        status_code = 200
        headers = {"content-length": "100"}

        def raise_for_status(self):
            return None

        def iter_bytes(self):
            yield b'<!DOCTYPE feed [<!ENTITY x "expanded">]><rss><channel/></rss>'

    class FakeStream:
        def __enter__(self):
            return FakeResponse()

        def __exit__(self, *_args):
            return None

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def stream(self, *_args, **_kwargs):
            return FakeStream()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    with pytest.raises(ValueError, match="entity declarations"):
        fetch_feed("https://www.nseindia.com/feed.xml", "www.nseindia.com")


def test_social_source_requires_source_specific_evaluated_sentiment_model():
    from mutual_fund_agent_analysis.data.services.research_intelligence import create_social_post

    source = DataSource(
        source_key="reddit",
        display_name="Reddit",
        source_type="social",
        authority_tier=5,
        is_official=False,
        enabled=True,
        terms_url="https://www.redditinc.com/policies",
        metadata_json={
            "retention_days": 30,
            "terms_reviewed": True,
            "access_confirmed": True,
            "reviewed_at": "2026-11-25",
            "evaluated_sentiment_models": [],
        },
    )

    class StubSession:
        def __init__(self):
            self.added = []

        def get(self, model, _key):
            return source if model is DataSource else None

        def scalar(self, _statement):
            return None

        def add(self, row):
            self.added.append(row)

    payload = SocialPostInput(
        source_key="reddit",
        external_id="post-1",
        content_hash="a" * 64,
        published_at=datetime.now(UTC),
        sentiment_label="positive",
        sentiment_score=Decimal("0.7"),
        sentiment_model="unreviewed-model",
        expires_at=datetime.now(UTC) + __import__("datetime").timedelta(days=1),
    )
    with pytest.raises(ValueError, match="not registered as evaluated"):
        create_social_post(StubSession(), payload)


def test_social_post_persistence_discards_excerpt_and_provider_text_metadata(monkeypatch):
    from types import SimpleNamespace

    from mutual_fund_agent_analysis.data.services.research_intelligence import create_social_post

    source = DataSource(
        source_key="reddit",
        display_name="Reddit",
        source_type="social",
        authority_tier=5,
        is_official=False,
        enabled=True,
        terms_url="https://terms.example/reddit",
        metadata_json={
            "retention_days": 30,
            "terms_reviewed": True,
            "access_confirmed": True,
            "reviewed_at": "2026-11-25",
        },
    )
    monkeypatch.setattr(
        "mutual_fund_agent_analysis.core.config.get_settings",
        lambda: SimpleNamespace(social_retention_days=30),
    )

    class StubSession:
        def __init__(self):
            self.added = []

        def get(self, model, _key):
            return source if model is DataSource else None

        def scalar(self, _statement):
            return None

        def add(self, row):
            self.added.append(row)

        def commit(self):
            return None

        def refresh(self, _row):
            return None

    session = StubSession()
    payload = SocialPostInput(
        source_key="reddit",
        external_id="post-2",
        content_hash="b" * 64,
        text_excerpt="Do not persist this post text",
        expires_at=datetime.now(UTC) + __import__("datetime").timedelta(days=2),
        metadata={
            "subreddit": "investing",
            "text": "raw text",
            "content": "raw body",
            "nested": {"body": "raw nested body"},
        },
    )
    row = create_social_post(session, payload)
    assert row.text_excerpt is None
    assert row.metadata_json == {"subreddit": "investing"}


def test_rss_entity_resolution_requires_one_unique_exact_company_alias():
    from types import SimpleNamespace

    from mutual_fund_agent_analysis.data.services.research_intelligence import (
        _resolve_rss_entity_exact,
    )

    entity = SimpleNamespace(entity_id=42)
    alias = SimpleNamespace(normalized_alias="example industries")

    class StubResult:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class StubSession:
        def __init__(self, rows):
            self.rows = rows

        def execute(self, _statement):
            return StubResult(self.rows)

    assert (
        _resolve_rss_entity_exact(
            StubSession([(alias, entity)]),
            "nse",
            "Example Industries announces quarterly results",
            date(2026, 11, 1),
        )
        == 42
    )
    assert (
        _resolve_rss_entity_exact(
            StubSession([(alias, entity)]),
            "nse",
            "Example Industries Ltd competitor results",
            None,
        )
        is None
    )

    other = SimpleNamespace(entity_id=43)
    assert (
        _resolve_rss_entity_exact(
            StubSession([(alias, entity), (alias, other)]),
            "nse",
            "Example Industries announces quarterly results",
            date(2026, 11, 1),
        )
        is None
    )


def test_rss_event_date_is_not_inferred_from_publication_date():
    from xml.etree import ElementTree

    from mutual_fund_agent_analysis.data.providers.rss import _parse_event_date

    no_effective_date = ElementTree.fromstring(
        "<item><pubDate>Tue, 25 Nov 2026 10:00:00 GMT</pubDate></item>"
    )
    explicit_event_date = ElementTree.fromstring(
        "<item><eventDate>2026-11-20</eventDate>"
        "<pubDate>Tue, 25 Nov 2026 10:00:00 GMT</pubDate></item>"
    )
    assert _parse_event_date(no_effective_date) is None
    assert _parse_event_date(explicit_event_date) == date(2026, 11, 20)


def test_security_observation_source_url_must_match_registered_https_host():
    source = SimpleNamespace(base_url="https://nseindia.com")
    assert (
        _validate_registered_source_url(source, "https://www.nseindia.com/api/filings")
        == "https://www.nseindia.com/api/filings"
    )
    assert (
        _validate_registered_source_url(source, "https://feeds.nseindia.com/announcements")
        == "https://feeds.nseindia.com/announcements"
    )
    for candidate in (
        "http://www.nseindia.com/filings",
        "https://nseindia.com.attacker.example/filings",
        "https://attacker.example/nse/filings",
        "https://nseindia.com:8443/filings",
    ):
        with pytest.raises(HTTPException):
            _validate_registered_source_url(source, candidate)


def test_twelve_data_http_errors_do_not_expose_api_key():
    api_key = "sensitive-test-api-key"

    def reject_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, request=request)

    client = TwelveDataClient(
        api_key,
        client=httpx.Client(transport=httpx.MockTransport(reject_request)),
    )
    try:
        with pytest.raises(ValueError) as error:
            client.get_quote("INFY", "NSE")
        assert api_key not in str(error.value)
        assert "provider details were withheld" in str(error.value)
    finally:
        client.close()


def test_portfolio_upload_rejects_more_than_5000_rows_before_persistence():
    csv_content = "security_key,security_name,asset_class\n" + "".join(
        f"INE{i:09d},Example {i},equity\n" for i in range(5001)
    )
    upload = UploadFile(
        filename="holdings.csv",
        file=io.BytesIO(csv_content.encode("utf-8")),
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            research_routes.import_portfolio_file(
                session=None,
                file=upload,
                scheme_code=100,
                effective_date=date(2026, 11, 25),
            )
        )
    assert error.value.status_code == 413


def test_portfolio_upload_rejects_xlsx_with_rows_beyond_bounded_scan():
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["security_key", "security_name", "asset_class"])
    sheet.cell(row=6000, column=1, value="INE000000001")
    content = io.BytesIO()
    workbook.save(content)
    workbook.close()
    upload = UploadFile(filename="sparse.xlsx", file=io.BytesIO(content.getvalue()))

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            research_routes.import_portfolio_file(
                session=None,
                file=upload,
                scheme_code=100,
                effective_date=date(2026, 11, 25),
            )
        )

    assert error.value.status_code == 413


def test_lexical_retrieval_ranks_term_frequency_before_candidate_limit(monkeypatch):
    from mutual_fund_agent_analysis.data.services import document_vectors
    from mutual_fund_agent_analysis.data.services.research_intelligence import search_documents

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    session.add(
        DataSource(
            source_key="test_source",
            display_name="Test source",
            source_type="internal",
            authority_tier=5,
            is_official=False,
            enabled=True,
        )
    )
    session.flush()

    for index in range(205):
        text = " ".join(["bank"] * 20) if index == 0 else "bank "
        document = ResearchDocument(
            source_key="test_source",
            title="Older high-relevance document" if index == 0 else f"Document {index}",
            media_type="text/plain",
            content_hash=f"{index:064x}",
            extracted_text=text,
            page_count=1,
        )
        session.add(document)
        session.flush()
        session.add(
            DocumentChunk(
                document_id=document.document_id,
                chunk_index=0,
                chunk_text=text,
                token_estimate=max(1, len(text) // 4),
                metadata_json={},
            )
        )
    session.commit()
    monkeypatch.setattr(document_vectors, "search_chunks", lambda *args, **kwargs: None)

    try:
        result = search_documents(session, "bank", None, limit=1)
        assert result["results"][0]["title"] == "Older high-relevance document"
    finally:
        session.close()
        engine.dispose()


def test_historical_event_route_serializes_selected_revision(monkeypatch):
    from mutual_fund_agent_analysis.api.routes import research as routes

    as_of = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    current_event = SimpleNamespace(event_id=77)
    prior_snapshot = {
        "source_key": "nse",
        "external_id": "notice-77",
        "evidence_id": None,
        "related_entity_id": None,
        "title": "Original title",
        "summary": "Original summary",
        "event_type": "results",
        "status": "reported",
        "event_date": "2026-10-29",
        "published_at": "2026-10-22T12:00:00+00:00",
        "canonical_url": "https://www.nseindia.com/notice/77",
        "confidence": "0.5",
        "metadata": {"revision": 1},
        "evidence": None,
    }

    class SessionStub:
        def scalars(self, _statement):
            return SimpleNamespace(all=lambda: [current_event])

        def get(self, model, _key):
            if model is routes.DataSource:
                return SimpleNamespace(
                    source_type="exchange",
                    authority_tier=1,
                    is_official=True,
                    attribution_required=True,
                )
            return None

    monkeypatch.setattr(
        routes,
        "_event_state_as_of",
        lambda _session, _event, _as_of: prior_snapshot,
    )
    result = routes.list_events(
        session=SessionStub(),
        status_filter=None,
        event_type=None,
        source_key=None,
        entity_id=None,
        as_of=as_of,
        limit=50,
        offset=0,
    )

    assert result["count"] == 1
    assert result["total_count"] == 1
    assert result["items"][0]["title"] == "Original title"
    assert result["items"][0]["status"] == "reported"
    assert result["items"][0]["event_date"] == "2026-10-29"
    assert result["as_of"] == as_of.isoformat()


def test_event_as_of_requires_timezone_aware_datetime():
    from datetime import datetime

    from fastapi import HTTPException

    from mutual_fund_agent_analysis.api.routes.research import list_events

    with pytest.raises(HTTPException) as error:
        list_events(session=None, as_of=datetime(2026, 11, 1, 12, 0))
    assert error.value.status_code == 422


def test_document_delete_does_not_remove_lexical_records_when_vector_cleanup_fails(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(research_routes, "delete_document_chunks", lambda _document_id: False)

    class SessionStub:
        def __init__(self):
            self.deleted = False
            self.committed = False

        def get(self, _model, _key):
            return SimpleNamespace(document_id=100)

        def execute(self, _statement):
            raise AssertionError("Lexical chunks must not be deleted before vector cleanup.")

        def delete(self, _document):
            self.deleted = True

        def commit(self):
            self.committed = True

    session = SessionStub()
    with pytest.raises(HTTPException) as error:
        research_routes.delete_research_document(100, session)

    assert error.value.status_code == 503
    assert session.deleted is False
    assert session.committed is False


def test_document_delete_removes_vectors_before_lexical_records(monkeypatch):
    order = []
    monkeypatch.setattr(
        research_routes,
        "delete_document_chunks",
        lambda _document_id: order.append("vectors") or True,
    )

    class SessionStub:
        def get(self, _model, _key):
            return SimpleNamespace(document_id=101)

        def execute(self, _statement):
            order.append("lexical_chunks")

        def delete(self, _document):
            order.append("document")

        def commit(self):
            order.append("commit")

    result = research_routes.delete_research_document(101, SessionStub())
    assert result["deleted"] is True
    assert order == ["vectors", "lexical_chunks", "document", "commit"]

def test_portfolio_content_hash_ignores_caller_hash_and_holding_order():
    first = HoldingInput(
        security_key="INE000A01001",
        isin="INE000A01001",
        security_name="Alpha Ltd",
        weight_pct=Decimal("60"),
    )
    second = HoldingInput(
        security_key="INE000B01001",
        isin="INE000B01001",
        security_name="Beta Ltd",
        weight_pct=Decimal("40"),
    )
    common = {
        "scheme_code": 100,
        "source_key": "amc_disclosures",
        "effective_date": date(2026, 10, 31),
    }
    left = PortfolioImportRequest(**common, content_hash="a" * 64, holdings=[first, second])
    right = PortfolioImportRequest(**common, content_hash="b" * 64, holdings=[second, first])
    assert _portfolio_content_hash(left) == _portfolio_content_hash(right)


def test_portfolio_import_accepts_server_generated_content_hash():
    payload = PortfolioImportRequest(
        scheme_code=100,
        source_key="amc_disclosures",
        effective_date=date(2026, 10, 31),
        holdings=[
            {
                "security_key": "INE123A01016",
                "security_name": "Example Ltd",
                "asset_class": "equity",
                "weight_pct": "100",
            }
        ],
    )
    assert payload.content_hash is None
    assert len(_portfolio_content_hash(payload)) == 64
