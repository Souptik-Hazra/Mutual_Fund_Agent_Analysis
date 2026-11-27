"""Tests for conservative scheme-name metadata classification."""

import pytest

from mutual_fund_agent_analysis.data.services.scheme_metadata_sync import classify_scheme_name


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("HDFC Mid Cap Fund - Regular Plan - Growth Option", ("regular", "growth")),
        ("HDFC Mid Cap Fund - Direct Plan - IDCW Option", ("direct", None)),
        ("ABC Fund - Direct Plan - IDCW Reinvestment", ("direct", "idcw_reinvestment")),
        ("ABC Fund - Regular Plan - IDCW Payout", ("regular", "idcw_payout")),
        ("ABC Fund", (None, None)),
    ],
)
def test_classify_scheme_name_uses_only_explicit_labels(name, expected):
    assert classify_scheme_name(name) == expected
