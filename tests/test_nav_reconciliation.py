"""Tests for deterministic cross-provider NAV reconciliation."""

from decimal import Decimal

import pytest

from mutual_fund_agent_analysis.data.services.nav_reconciliation import (
    NAV_RECONCILIATION_TOLERANCE,
    build_reconciliation,
)


def test_amfi_is_canonical_when_both_sources_are_present() -> None:
    result = build_reconciliation({"mfapi": Decimal("10.12345"), "amfi": Decimal("10.1234")})
    assert result["canonical_source"] == "amfi"
    assert result["canonical_nav"] == Decimal("10.1234")
    assert result["status"] == "matched"
    assert result["absolute_difference"] == Decimal("0.00005")


def test_conflicting_navs_are_flagged_without_discarding_either_value() -> None:
    result = build_reconciliation({"mfapi": Decimal("10.50"), "amfi": Decimal("10.25")})
    assert result["status"] == "conflict"
    assert result["canonical_source"] == "amfi"
    assert result["source_values"] == {"amfi": "10.25", "mfapi": "10.50"}
    assert result["absolute_difference"] == Decimal("0.25")


def test_single_provider_is_marked_single_source() -> None:
    result = build_reconciliation({"mfapi": Decimal("10.25")})
    assert result["status"] == "single_source"
    assert result["canonical_source"] == "mfapi"
    assert result["absolute_difference"] is None


@pytest.mark.parametrize(
    "values",
    [{}, {"amfi": Decimal("0")}, {"mfapi": Decimal("NaN")}],
)
def test_invalid_reconciliation_values_are_rejected(values) -> None:
    with pytest.raises(ValueError):
        build_reconciliation(values)


def test_default_tolerance_is_explicit() -> None:
    assert NAV_RECONCILIATION_TOLERANCE == Decimal("0.0001")
