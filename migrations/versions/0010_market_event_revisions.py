"""Add immutable market event revision history.

Revision ID: 0010_market_event_revisions
Revises: 0009_metadata_and_distributions
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_market_event_revisions"
down_revision = "0009_metadata_and_distributions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_event_revisions",
        sa.Column("revision_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "event_id",
            sa.BigInteger(),
            sa.ForeignKey("market_events.event_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("revision_reason", sa.String(80), nullable=False),
        sa.Column(
            "snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "event_id",
            "revision_number",
            name="uq_market_event_revision_number",
        ),
    )
    op.create_index(
        "ix_market_event_revisions_recorded",
        "market_event_revisions",
        ["event_id", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_market_event_revisions_recorded",
        table_name="market_event_revisions",
    )
    op.drop_table("market_event_revisions")
