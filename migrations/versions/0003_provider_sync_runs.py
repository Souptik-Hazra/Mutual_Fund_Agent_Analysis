"""Persist raw provider responses for NAV ingestion auditability.

Revision ID: 0003_provider_sync_runs
Revises: 0002_source_aware_nav
Create Date: 2026-11-25
"""

from alembic import op
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Identity,
    Integer,
    PrimaryKeyConstraint,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003_provider_sync_runs"
down_revision = "0002_source_aware_nav"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create an append-only audit table for successful provider fetches."""
    op.create_table(
        "provider_sync_runs",
        Column("id", BigInteger(), Identity(), nullable=False),
        Column("scheme_code", BigInteger(), nullable=False),
        Column("source", String(length=40), nullable=False),
        Column("fetched_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        Column("observation_count", Integer(), nullable=False),
        Column("response_payload", JSONB(), nullable=False),
        ForeignKeyConstraint(
            ["scheme_code"],
            ["mutual_fund_schemes.scheme_code"],
            ondelete="CASCADE",
        ),
        PrimaryKeyConstraint("id", name="pk_provider_sync_runs"),
    )
    op.create_index(
        "ix_provider_sync_runs_scheme_source_fetched",
        "provider_sync_runs",
        ["scheme_code", "source", "fetched_at"],
    )


def downgrade() -> None:
    """Remove provider response audit history."""
    op.drop_index(
        "ix_provider_sync_runs_scheme_source_fetched",
        table_name="provider_sync_runs",
    )
    op.drop_table("provider_sync_runs")
