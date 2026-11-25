"""Add effective-dated category benchmark mappings.
Revision ID: 0012_category_benchmarks
Revises: 0011_security_market_obs
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_category_benchmarks"
down_revision = "0011_security_market_obs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "category_benchmark_mappings",
        sa.Column("mapping_id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("scheme_category", sa.String(250), nullable=False),
        sa.Column("scheme_type", sa.String(120)),
        sa.Column("plan_type", sa.String(20)),
        sa.Column("option_type", sa.String(30)),
        sa.Column("benchmark_code", sa.String(80), nullable=False),
        sa.Column("benchmark_source", sa.String(40), nullable=False, server_default="niftyindices"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column(
            "source_key",
            sa.String(60),
            sa.ForeignKey("data_sources.source_key", ondelete="RESTRICT"),
        ),
        sa.Column("rationale", sa.String(1000), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_category_benchmark_date_range",
        ),
        sa.UniqueConstraint(
            "scheme_category",
            "scheme_type",
            "plan_type",
            "option_type",
            "effective_from",
            name="uq_category_benchmark_effective",
        ),
    )
    op.create_index(
        "ix_category_benchmark_lookup",
        "category_benchmark_mappings",
        [
            "scheme_category",
            "scheme_type",
            "plan_type",
            "option_type",
            "effective_from",
            "effective_to",
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_category_benchmark_lookup", table_name="category_benchmark_mappings")
    op.drop_table("category_benchmark_mappings")
