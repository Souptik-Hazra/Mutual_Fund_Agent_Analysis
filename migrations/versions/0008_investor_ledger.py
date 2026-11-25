"""Add the personal investor transaction ledger."""

from alembic import op

revision = "0008_investor_ledger"
down_revision = "0007_research_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import mutual_fund_agent_analysis.models  # noqa: F401
    from mutual_fund_agent_analysis.database.base import Base

    Base.metadata.create_all(
        bind=op.get_bind(),
        tables=[Base.metadata.tables["investor_transactions"]],
        checkfirst=True,
    )


def downgrade() -> None:
    import mutual_fund_agent_analysis.models  # noqa: F401
    from mutual_fund_agent_analysis.database.base import Base

    Base.metadata.drop_all(
        bind=op.get_bind(),
        tables=[Base.metadata.tables["investor_transactions"]],
        checkfirst=True,
    )
