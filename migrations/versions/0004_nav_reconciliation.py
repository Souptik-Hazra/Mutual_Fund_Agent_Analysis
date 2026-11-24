"""Persist deterministic cross-provider NAV reconciliation.

Revision ID: 0004_nav_reconciliation
Revises: 0003_provider_sync_runs
Create Date: 2026-11-25
"""

from alembic import op
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Numeric,
    PrimaryKeyConstraint,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004_nav_reconciliation"
down_revision = "0003_provider_sync_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nav_reconciliations",
        Column("scheme_code", BigInteger(), nullable=False),
        Column("nav_date", Date(), nullable=False),
        Column("source_values", JSONB(), nullable=False),
        Column("canonical_nav", Numeric(18, 8), nullable=False),
        Column("canonical_source", String(length=40), nullable=False),
        Column("absolute_difference", Numeric(18, 8)),
        Column("relative_difference", Numeric(20, 12)),
        Column("status", String(length=20), nullable=False),
        Column("tolerance", Numeric(18, 8), nullable=False),
        Column("evaluated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        CheckConstraint(
            "status IN ('single_source', 'matched', 'conflict')",
            name="ck_nav_reconciliations_status",
        ),
        ForeignKeyConstraint(
            ["scheme_code"],
            ["mutual_fund_schemes.scheme_code"],
            ondelete="CASCADE",
        ),
        PrimaryKeyConstraint("scheme_code", "nav_date", name="pk_nav_reconciliations"),
    )


def downgrade() -> None:
    op.drop_table("nav_reconciliations")
