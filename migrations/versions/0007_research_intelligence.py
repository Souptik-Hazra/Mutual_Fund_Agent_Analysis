"""Persist portfolio, event, social, and document intelligence."""
from alembic import op

revision = "0007_research_intelligence"
down_revision = "0006_common_intelligence_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from mutual_fund_agent_analysis.database.base import Base
    import mutual_fund_agent_analysis.models  # noqa: F401
    names = (
        "portfolio_snapshots",
        "portfolio_holdings",
        "market_events",
        "social_posts",
        "research_documents",
        "document_chunks",
    )
    op.get_bind()
    Base.metadata.create_all(
        bind=op.get_bind(),
        tables=[Base.metadata.tables[name] for name in names],
        checkfirst=True,
    )


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
