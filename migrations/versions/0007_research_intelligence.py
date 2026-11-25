"""Persist portfolio, event, social, and document intelligence."""
from alembic import op
from sqlalchemy import text

revision = "0007_research_intelligence"
down_revision = "0006_common_intelligence_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import mutual_fund_agent_analysis.models  # noqa: F401
    from mutual_fund_agent_analysis.database.base import Base
    names = (
        "portfolio_snapshots",
        "portfolio_holdings",
        "market_events",
        "social_posts",
        "research_documents",
        "document_chunks",
    )
    Base.metadata.create_all(
        bind=op.get_bind(),
        tables=[Base.metadata.tables[name] for name in names],
        checkfirst=True,
    )
    op.get_bind().execute(text("""
        INSERT INTO data_sources (
            source_key, display_name, source_type, authority_tier, is_official,
            base_url, attribution_required, enabled, metadata
        ) VALUES (
            'amc_disclosures', 'AMC Portfolio and Scheme Disclosures', 'official',
            1, true, NULL, false, true,
            '{"domain":"portfolio_disclosure","role":"primary_scheme_disclosure"}'::jsonb
        ) ON CONFLICT (source_key) DO NOTHING
    """))


def downgrade() -> None:
    from mutual_fund_agent_analysis.database.base import Base
    import mutual_fund_agent_analysis.models  # noqa: F401
    names = (
        "document_chunks",
        "research_documents",
        "social_posts",
        "market_events",
        "portfolio_holdings",
        "portfolio_snapshots",
    )
    Base.metadata.drop_all(
        bind=op.get_bind(),
        tables=[Base.metadata.tables[name] for name in names],
        checkfirst=True,
    )
