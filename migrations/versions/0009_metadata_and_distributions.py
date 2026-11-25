"""Add effective-dated scheme metadata and versioned IDCW records.

Revision ID: 0009_metadata_and_distributions
Revises: 0008_investor_ledger
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_metadata_and_distributions"
down_revision = "0008_investor_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mutual_fund_schemes", sa.Column("lifecycle_type", sa.String(20), nullable=True))
    op.add_column("mutual_fund_schemes", sa.Column("plan_type", sa.String(20), nullable=True))
    op.add_column("mutual_fund_schemes", sa.Column("option_type", sa.String(30), nullable=True))
    op.add_column("mutual_fund_schemes", sa.Column("launch_date", sa.Date(), nullable=True))
    op.add_column("mutual_fund_schemes", sa.Column("closure_date", sa.Date(), nullable=True))
    op.add_column("mutual_fund_schemes", sa.Column("effective_expense_ratio", sa.Numeric(8, 5), nullable=True))
    op.add_column("mutual_fund_schemes", sa.Column("expense_ratio_effective_date", sa.Date(), nullable=True))
    op.add_column("mutual_fund_schemes", sa.Column("expense_ratio_source_key", sa.String(60), nullable=True))
    op.create_foreign_key(
        "fk_scheme_expense_source", "mutual_fund_schemes", "data_sources",
        ["expense_ratio_source_key"], ["source_key"], ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_scheme_lifecycle_type", "mutual_fund_schemes",
        "lifecycle_type IS NULL OR lifecycle_type IN ('open_ended','close_ended','interval','unknown')",
    )
    op.create_check_constraint(
        "ck_scheme_plan_type", "mutual_fund_schemes",
        "plan_type IS NULL OR plan_type IN ('direct','regular','unknown')",
    )
    op.create_check_constraint(
        "ck_scheme_option_type", "mutual_fund_schemes",
        "option_type IS NULL OR option_type IN ('growth','idcw_payout','idcw_reinvestment','idcw_transfer','unknown')",
    )

    op.create_table(
        "scheme_metadata_observations",
        sa.Column("metadata_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("scheme_code", sa.BigInteger(), sa.ForeignKey("mutual_fund_schemes.scheme_code", ondelete="CASCADE"), nullable=False),
        sa.Column("source_key", sa.String(60), sa.ForeignKey("data_sources.source_key", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("plan_type", sa.String(20), nullable=True),
        sa.Column("option_type", sa.String(30), nullable=True),
        sa.Column("lifecycle_type", sa.String(20), nullable=True),
        sa.Column("expense_ratio", sa.Numeric(8, 5), nullable=True),
        sa.Column("expense_ratio_effective_date", sa.Date(), nullable=True),
        sa.Column("benchmark_code", sa.String(80), nullable=True),
        sa.Column("launch_date", sa.Date(), nullable=True),
        sa.Column("closure_date", sa.Date(), nullable=True),
        sa.Column("verification_status", sa.String(20), nullable=False, server_default="unverified"),
        sa.Column("verification_note", sa.String(1000), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("scheme_code", "source_key", "content_hash", name="uq_scheme_metadata_source_hash"),
        sa.CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from", name="ck_scheme_metadata_valid_range"),
        sa.CheckConstraint("plan_type IS NULL OR plan_type IN ('direct','regular','unknown')", name="ck_scheme_metadata_plan"),
        sa.CheckConstraint("option_type IS NULL OR option_type IN ('growth','idcw_payout','idcw_reinvestment','idcw_transfer','unknown')", name="ck_scheme_metadata_option"),
        sa.CheckConstraint("lifecycle_type IS NULL OR lifecycle_type IN ('open_ended','close_ended','interval','unknown')", name="ck_scheme_metadata_lifecycle"),
        sa.CheckConstraint("expense_ratio IS NULL OR expense_ratio BETWEEN 0 AND 100", name="ck_scheme_metadata_expense_ratio"),
        sa.CheckConstraint("verification_status IN ('unverified','verified','disputed','retracted')", name="ck_scheme_metadata_verification"),
    )
    op.create_index("ix_scheme_metadata_effective", "scheme_metadata_observations", ["scheme_code", "valid_from", "valid_to"])

    op.create_table(
        "distribution_observations",
        sa.Column("distribution_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("scheme_code", sa.BigInteger(), sa.ForeignKey("mutual_fund_schemes.scheme_code", ondelete="CASCADE"), nullable=False),
        sa.Column("source_key", sa.String(60), sa.ForeignKey("data_sources.source_key", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("supersedes_distribution_id", sa.BigInteger(), sa.ForeignKey("distribution_observations.distribution_id", ondelete="RESTRICT"), nullable=True),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("record_date", sa.Date(), nullable=True),
        sa.Column("payment_date", sa.Date(), nullable=True),
        sa.Column("amount_per_unit", sa.Numeric(20, 8), nullable=False),
        sa.Column("option_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("verification_status", sa.String(20), nullable=False, server_default="unverified"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("scheme_code", "source_key", "external_id", "revision", name="uq_distribution_source_revision"),
        sa.CheckConstraint("amount_per_unit > 0", name="ck_distribution_amount_positive"),
        sa.CheckConstraint("revision >= 1", name="ck_distribution_revision_positive"),
        sa.CheckConstraint("record_date IS NULL OR record_date >= ex_date", name="ck_distribution_record_date"),
        sa.CheckConstraint("payment_date IS NULL OR record_date IS NULL OR payment_date >= record_date", name="ck_distribution_payment_date"),
        sa.CheckConstraint("option_type IN ('idcw_payout','idcw_reinvestment','idcw_transfer')", name="ck_distribution_option"),
        sa.CheckConstraint("status IN ('active','revised','cancelled')", name="ck_distribution_status"),
        sa.CheckConstraint("verification_status IN ('unverified','verified','disputed','retracted')", name="ck_distribution_verification"),
    )
    op.create_index("ix_distribution_scheme_ex_date", "distribution_observations", ["scheme_code", "ex_date"])

    op.create_table(
        "distribution_coverage_attestations",
        sa.Column("attestation_id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("scheme_code", sa.BigInteger(), sa.ForeignKey("mutual_fund_schemes.scheme_code", ondelete="CASCADE"), nullable=False),
        sa.Column("source_key", sa.String(60), sa.ForeignKey("data_sources.source_key", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("coverage_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verification_status", sa.String(20), nullable=False, server_default="unverified"),
        sa.Column("verification_note", sa.String(1000), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("scheme_code", "source_key", "external_id", "content_hash", name="uq_distribution_coverage_attestation"),
        sa.CheckConstraint("end_date >= start_date", name="ck_distribution_coverage_date_range"),
        sa.CheckConstraint("verification_status IN ('unverified','verified','disputed','retracted')", name="ck_distribution_coverage_verification"),
    )
    op.create_index("ix_distribution_coverage_scheme_dates", "distribution_coverage_attestations", ["scheme_code", "start_date", "end_date"])


def downgrade() -> None:
    op.drop_index("ix_distribution_coverage_scheme_dates", table_name="distribution_coverage_attestations")
    op.drop_table("distribution_coverage_attestations")
    op.drop_index("ix_distribution_scheme_ex_date", table_name="distribution_observations")
    op.drop_table("distribution_observations")
    op.drop_index("ix_scheme_metadata_effective", table_name="scheme_metadata_observations")
    op.drop_table("scheme_metadata_observations")
    op.drop_constraint("ck_scheme_option_type", "mutual_fund_schemes", type_="check")
    op.drop_constraint("ck_scheme_plan_type", "mutual_fund_schemes", type_="check")
    op.drop_constraint("ck_scheme_lifecycle_type", "mutual_fund_schemes", type_="check")
    op.drop_constraint("fk_scheme_expense_source", "mutual_fund_schemes", type_="foreignkey")
    op.drop_column("mutual_fund_schemes", "expense_ratio_source_key")
    op.drop_column("mutual_fund_schemes", "expense_ratio_effective_date")
    op.drop_column("mutual_fund_schemes", "effective_expense_ratio")
    op.drop_column("mutual_fund_schemes", "closure_date")
    op.drop_column("mutual_fund_schemes", "launch_date")
    op.drop_column("mutual_fund_schemes", "option_type")
    op.drop_column("mutual_fund_schemes", "plan_type")
    op.drop_column("mutual_fund_schemes", "lifecycle_type")
