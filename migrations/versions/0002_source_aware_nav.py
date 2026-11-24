"""Include provider in the NAV observation primary key.

Revision ID: 0002_source_aware_nav
Revises: 0001_initial_market_data
Create Date: 2026-11-25
"""

from alembic import op

revision = "0002_source_aware_nav"
down_revision = "0001_initial_market_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Allow multiple providers to report a NAV for the same scheme/date."""
    op.drop_constraint("nav_observations_pkey", "nav_observations", type_="primary")
    op.create_primary_key(
        "pk_nav_observations",
        "nav_observations",
        ["scheme_code", "nav_date", "source"],
    )


def downgrade() -> None:
    """Restore the original scheme/date primary key."""
    op.drop_constraint("pk_nav_observations", "nav_observations", type_="primary")
    op.create_primary_key(
        "nav_observations_pkey",
        "nav_observations",
        ["scheme_code", "nav_date"],
    )
