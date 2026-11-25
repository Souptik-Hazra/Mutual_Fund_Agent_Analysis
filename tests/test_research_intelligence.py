from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from mutual_fund_agent_analysis.api.schemas.research import (
    EventInput,
    HoldingInput,
    PortfolioImportRequest,
    SocialPostInput,
)
from mutual_fund_agent_analysis.data.providers.rss import fetch_feed
from mutual_fund_agent_analysis.data.services.research_intelligence import split_document


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
            holdings=[{
                "security_key": "INE123A01016",
                "security_name": "Example Ltd",
                "asset_class": "equity",
            }],
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
