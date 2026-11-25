from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from mutual_fund_agent_analysis.api.routes import research as research_routes
from mutual_fund_agent_analysis.api.schemas.research import (
    EventInput,
    HoldingInput,
    PortfolioImportRequest,
    SocialPostInput,
)
from mutual_fund_agent_analysis.data.providers.rss import fetch_feed
from mutual_fund_agent_analysis.data.services.research_intelligence import (
    source_social_retention_days,
    split_document,
)
from mutual_fund_agent_analysis.models import DataSource


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
        metadata_json={"retention_days": 12},
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
    from datetime import timedelta
    from types import SimpleNamespace

    source = DataSource(
        source_key="reddit",
        display_name="Reddit",
        source_type="social",
        authority_tier=5,
        is_official=False,
        enabled=True,
        metadata_json={"retention_days": 12},
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
