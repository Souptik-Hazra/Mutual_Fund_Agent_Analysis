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
