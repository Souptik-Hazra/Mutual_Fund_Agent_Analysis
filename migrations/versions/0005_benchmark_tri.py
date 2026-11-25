"""Add benchmark index master and source-specific TRI observations.

Revision ID: 0005_benchmark_tri
Revises: 0004_nav_reconciliation
Create Date: 2026-11-25
"""

from alembic import op
from sqlalchemy import (
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

revision = "0005_benchmark_tri"
down_revision = "0004_nav_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "benchmark_indices",
        Column("benchmark_code", String(length=80), nullable=False),
        Column("benchmark_name", String(length=160), nullable=False),
        Column("provider", String(length=40), nullable=False),
        Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        PrimaryKeyConstraint("benchmark_code", name="pk_benchmark_indices"),
    )
    op.create_table(
        "benchmark_observations",
        Column("benchmark_code", String(length=80), nullable=False),
        Column("observation_date", Date(), nullable=False),
        Column("source", String(length=40), nullable=False),
        Column("tri_value", Numeric(20, 8), nullable=False),
        Column("ntr_value", Numeric(20, 8)),
        Column("fetched_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        Column("raw_metadata", __import__("sqlalchemy").dialects.postgresql.JSONB()),
        CheckConstraint("tri_value > 0", name="ck_benchmark_observations_positive_tri"),
        CheckConstraint(
            "ntr_value IS NULL OR ntr_value > 0",
            name="ck_benchmark_observations_positive_ntr",
        ),
        ForeignKeyConstraint(
            ["benchmark_code"],
            ["benchmark_indices.benchmark_code"],
            ondelete="CASCADE",
        ),
        PrimaryKeyConstraint(
            "benchmark_code",
            "observation_date",
            "source",
            name="pk_benchmark_observations",
        ),
    )
    op.create_index(
        "ix_benchmark_observations_date",
        "benchmark_observations",
        ["observation_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_benchmark_observations_date", table_name="benchmark_observations")
    op.drop_table("benchmark_observations")
    op.drop_table("benchmark_indices")
