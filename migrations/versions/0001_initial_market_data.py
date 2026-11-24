"""Create mutual fund scheme and NAV observation tables.

Revision ID: 0001_initial_market_data
Revises:
Create Date: 2026-11-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_market_data"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mutual_fund_schemes",
        sa.Column("scheme_code", sa.BigInteger(), primary_key=True),
        sa.Column("scheme_name", sa.String(length=500), nullable=False),
        sa.Column("fund_house", sa.String(length=250)),
        sa.Column("scheme_type", sa.String(length=120)),
        sa.Column("scheme_category", sa.String(length=250)),
        sa.Column("isin_growth", sa.String(length=12)),
        sa.Column("isin_div_reinvestment", sa.String(length=12)),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column(
            "source_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_mutual_fund_schemes_scheme_name", "mutual_fund_schemes", ["scheme_name"])
    op.create_index("ix_mutual_fund_schemes_isin_growth", "mutual_fund_schemes", ["isin_growth"])
    op.create_index(
        "ix_mutual_fund_schemes_isin_div_reinvestment",
        "mutual_fund_schemes",
        ["isin_div_reinvestment"],
    )
    op.create_table(
        "nav_observations",
        sa.Column("scheme_code", sa.BigInteger(), nullable=False),
        sa.Column("nav_date", sa.Date(), nullable=False),
        sa.Column("nav", sa.Numeric(18, 8), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("nav > 0", name="ck_nav_observations_positive_nav"),
        sa.ForeignKeyConstraint(
            ["scheme_code"],
            ["mutual_fund_schemes.scheme_code"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("scheme_code", "nav_date"),
    )


def downgrade() -> None:
    op.drop_table("nav_observations")
    op.drop_index("ix_mutual_fund_schemes_isin_div_reinvestment", table_name="mutual_fund_schemes")
    op.drop_index("ix_mutual_fund_schemes_isin_growth", table_name="mutual_fund_schemes")
    op.drop_index("ix_mutual_fund_schemes_scheme_name", table_name="mutual_fund_schemes")
    op.drop_table("mutual_fund_schemes")
