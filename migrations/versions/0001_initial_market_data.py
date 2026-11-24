"""Create mutual fund scheme and NAV observation tables.

Revision ID: 0001_initial_market_data
Revises:
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

revision = "0001_initial_market_data"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mutual_fund_schemes",
        Column("scheme_code", BigInteger(), primary_key=True),
        Column("scheme_name", String(length=500), nullable=False),
        Column("fund_house", String(length=250)),
        Column("scheme_type", String(length=120)),
        Column("scheme_category", String(length=250)),
        Column("isin_growth", String(length=12)),
        Column("isin_div_reinvestment", String(length=12)),
        Column("source", String(length=40), nullable=False),
        Column(
            "source_updated_at",
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
        Column(
            "created_at",
            DateTime(timezone=True),
            server_default=func.now(),
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
        Column("scheme_code", BigInteger(), nullable=False),
        Column("nav_date", Date(), nullable=False),
        Column("nav", Numeric(18, 8), nullable=False),
        Column("source", String(length=40), nullable=False),
        Column(
            "fetched_at",
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
        CheckConstraint("nav > 0", name="ck_nav_observations_positive_nav"),
        ForeignKeyConstraint(
            ["scheme_code"],
            ["mutual_fund_schemes.scheme_code"],
            ondelete="CASCADE",
        ),
        PrimaryKeyConstraint("scheme_code", "nav_date"),
    )


def downgrade() -> None:
    op.drop_table("nav_observations")
    op.drop_index("ix_mutual_fund_schemes_isin_div_reinvestment", table_name="mutual_fund_schemes")
    op.drop_index("ix_mutual_fund_schemes_isin_growth", table_name="mutual_fund_schemes")
    op.drop_index("ix_mutual_fund_schemes_scheme_name", table_name="mutual_fund_schemes")
    op.drop_table("mutual_fund_schemes")
