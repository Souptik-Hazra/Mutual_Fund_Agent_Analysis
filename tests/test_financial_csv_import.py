from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from mutual_fund_agent_analysis.cli.import_financial_csv import (
    _validate_source_policy,
    parse_distribution_row,
    parse_metadata_row,
    read_csv_rows,
)
from mutual_fund_agent_analysis.models import DataSource


def test_parse_scheme_metadata_csv_row_keeps_verification_unverified_by_default():
    row = parse_metadata_row(
        {
            "valid_from": "2026-10-01",
            "plan_type": "direct",
            "option_type": "growth",
            "lifecycle_type": "open_ended",
            "expense_ratio": "0.32",
            "expense_ratio_effective_date": "2026-10-01",
            "metadata_json": '{"amc_notice":"notice-1"}',
        },
        source_key="amc",
        source_url="https://amc.example/scheme",
    )
    assert row.valid_from == date(2026, 10, 1)
    assert row.plan_type == "direct"
    assert row.option_type == "growth"
    assert row.expense_ratio == Decimal("0.32")
    assert row.verification_status == "unverified"
    assert row.metadata == {"amc_notice": "notice-1"}


def test_metadata_parser_rejects_invalid_json_and_missing_expense_effective_date():
    with pytest.raises(ValueError, match="JSON"):
        parse_metadata_row(
            {"metadata_json": "[1,2]"},
            source_key="amc",
            source_url="https://amc.example/scheme",
        )
    with pytest.raises(ValidationError):
        parse_metadata_row(
            {"expense_ratio": "0.5"},
            source_key="amc",
            source_url="https://amc.example/scheme",
        )


def test_parse_distribution_csv_row_validates_dates_amount_and_revision():
    row = parse_distribution_row(
        {
            "external_id": "dividend-notice-2026-10",
            "revision": "2",
            "supersedes_distribution_id": "41",
            "ex_date": "2026-10-20",
            "record_date": "2026-10-21",
            "payment_date": "2026-10-27",
            "amount_per_unit": "1.25000000",
            "option_type": "idcw_payout",
        },
        source_key="amc",
        source_url="https://amc.example/distributions/notice-42",
    )
    assert row.external_id == "dividend-notice-2026-10"
    assert row.revision == 2
    assert row.supersedes_distribution_id == 41
    assert row.amount_per_unit == Decimal("1.25000000")
    assert row.verification_status == "unverified"


def test_verified_import_requires_official_enabled_source_and_matching_host():
    source = DataSource(
        source_key="amc",
        display_name="AMC",
        source_type="official",
        authority_tier=1,
        is_official=True,
        enabled=True,
        base_url="https://www.amc.example",
    )
    _validate_source_policy(source, "https://www.amc.example/notice", "verified")
    with pytest.raises(ValueError, match="does not match"):
        _validate_source_policy(
            source, "https://attacker.example/notice", "verified"
        )
    source.enabled = False
    with pytest.raises(ValueError, match="disabled"):
        _validate_source_policy(
            source, "https://www.amc.example/notice", "unverified"
        )


def test_csv_reader_accepts_utf8_bom_and_rejects_missing_file(tmp_path):
    path = tmp_path / "metadata.csv"
    path.write_text(
        "\ufeffscheme_code,plan_type\n1001,direct\n",
        encoding="utf-8",
    )
    assert read_csv_rows(path) == [{"scheme_code": "1001", "plan_type": "direct"}]
    with pytest.raises(ValueError, match="does not exist"):
        read_csv_rows(tmp_path / "missing.csv")
