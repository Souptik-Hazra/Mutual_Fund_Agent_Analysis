"""Persist versioned security market observations.

Revision ID: 0011_security_market_obs
Revises: 0010_market_event_revisions
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_security_market_obs"
down_revision = "0010_market_event_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_market_observations",
        sa.Column(
            "observation_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(),
            primary_key=True,
        ),
        sa.Column("security_key", sa.String(160), nullable=False),
        sa.Column("isin", sa.String(20)),
        sa.Column("security_name", sa.String(300), nullable=False),
        sa.Column("symbol", sa.String(40)),
        sa.Column("exchange", sa.String(12)),
        sa.Column(
            "source_key",
            sa.String(60),
            sa.ForeignKey("data_sources.source_key", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fundamentals_as_of", sa.Date()),
        sa.Column("last_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("change_pct", sa.Numeric(12, 6)),
        sa.Column("day_high", sa.Numeric(20, 6)),
        sa.Column("day_low", sa.Numeric(20, 6)),
        sa.Column("volume", sa.BigInteger()),
        sa.Column("market_status", sa.String(12), nullable=False, server_default="unknown"),
        sa.Column(
            "fundamentals",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "corporate_events",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column(
            "retrieved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("last_price > 0", name="ck_security_market_price_positive"),
        sa.CheckConstraint(
            "change_pct IS NULL OR change_pct >= -100",
            name="ck_security_market_change_floor",
        ),
        sa.CheckConstraint(
            "market_status IN ('trading', 'halted', 'closed', 'unknown')",
            name="ck_security_market_status",
        ),
        sa.UniqueConstraint(
            "source_key",
            "security_key",
            "observed_at",
            "content_hash",
            name="uq_security_market_observation_version",
        ),
    )
    op.create_index(
        "ix_security_market_latest",
        "security_market_observations",
        ["security_key", "observed_at"],
    )
    op.create_index(
        "ix_security_market_isin", "security_market_observations", ["isin", "observed_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_security_market_isin", table_name="security_market_observations")
    op.drop_index("ix_security_market_latest", table_name="security_market_observations")
    op.drop_table("security_market_observations")
