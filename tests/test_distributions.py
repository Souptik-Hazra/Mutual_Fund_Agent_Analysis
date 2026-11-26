from datetime import date
from decimal import Decimal

from fastapi import HTTPException

import pytest

from mutual_fund_agent_analysis.analytics.distributions import reinvested_distribution_index
from mutual_fund_agent_analysis.api.routes.financial import (
    _metadata_observation_is_current,
    _validate_distribution_revision_chain,
)
from mutual_fund_agent_analysis.api.schemas.financial import (
    DistributionObservationCreate,
    SchemeMetadataObservationCreate,
)


def test_reinvested_distribution_uses_ex_date_nav():
    points = reinvested_distribution_index(
        [
            (date(2024, 1, 1), Decimal("100")),
            (date(2024, 1, 2), Decimal("98")),
            (date(2024, 1, 3), Decimal("99")),
        ],
        {date(2024, 1, 2): Decimal("3")},
    )
    assert points[0].total_return_index == Decimal("100")
    assert points[1].nav_index == Decimal("98")
    assert points[1].total_return_index == Decimal("101")
    expected = Decimal("101") * Decimal("99") / Decimal("98")
    assert abs(points[2].total_return_index - expected) < Decimal("1e-25")


def test_distribution_events_on_same_ex_date_are_aggregated():
    points = reinvested_distribution_index(
        [
            (date(2024, 1, 1), Decimal("100")),
            (date(2024, 1, 2), Decimal("98")),
        ],
        {date(2024, 1, 2): Decimal("1") + Decimal("2")},
    )
    assert points[-1].total_return_index == Decimal("101")


def test_distribution_ex_date_must_have_a_nav_observation():
    with pytest.raises(ValueError, match="ex-date"):
        reinvested_distribution_index(
            [
                (date(2024, 1, 1), Decimal("100")),
                (date(2024, 1, 3), Decimal("99")),
            ],
            {date(2024, 1, 2): Decimal("1")},
        )


def test_nav_dates_must_be_unique_and_ascending():
    with pytest.raises(ValueError, match="unique, ascending"):
        reinvested_distribution_index(
            [
                (date(2024, 1, 2), Decimal("100")),
                (date(2024, 1, 1), Decimal("99")),
            ],
            {},
        )


def test_invalid_metadata_date_range_is_rejected():
    with pytest.raises(ValueError, match="valid_to"):
        SchemeMetadataObservationCreate(
            source_key="amc_official",
            source_url="https://amc.example/scheme",
            valid_from=date(2024, 2, 1),
            valid_to=date(2024, 1, 1),
        )


def test_distribution_dates_are_validated():
    with pytest.raises(ValueError, match="record_date"):
        DistributionObservationCreate(
            source_key="amc_official",
            external_id="notice-1",
            source_url="https://amc.example/idcw/notice-1",
            ex_date=date(2024, 2, 2),
            record_date=date(2024, 2, 1),
            amount_per_unit=Decimal("1.25"),
            option_type="idcw_payout",
        )


def test_payout_index_accumulates_cash_without_reinvestment():
    from mutual_fund_agent_analysis.analytics.distributions import payout_distribution_index

    navs = [
        (date(2024, 1, 1), Decimal("100")),
        (date(2024, 1, 2), Decimal("98")),
        (date(2024, 1, 3), Decimal("99")),
    ]
    payouts = payout_distribution_index(navs, {date(2024, 1, 2): Decimal("3")})
    reinvested = reinvested_distribution_index(navs, {date(2024, 1, 2): Decimal("3")})
    assert payouts[1].total_return_index == Decimal("101")
    assert payouts[2].total_return_index == Decimal("102")
    assert reinvested[2].total_return_index > payouts[2].total_return_index


def test_zero_distribution_payout_index_matches_nav_index():
    from mutual_fund_agent_analysis.analytics.distributions import payout_distribution_index

    points = payout_distribution_index(
        [
            (date(2024, 1, 1), Decimal("100")),
            (date(2024, 1, 2), Decimal("105")),
        ],
        {},
    )
    assert points[-1].total_return_index == points[-1].nav_index


def test_historical_and_future_scheme_metadata_do_not_change_current_projection():
    today = date(2026, 11, 26)
    assert not _metadata_observation_is_current(date(2024, 1, 1), date(2025, 12, 31), today)
    assert not _metadata_observation_is_current(date(2027, 1, 1), None, today)
    assert _metadata_observation_is_current(date(2026, 1, 1), None, today)


def test_distribution_revision_must_supersede_latest_active_revision():
    latest = type(
        "Distribution",
        (),
        {"distribution_id": 10, "revision": 1, "status": "active"},
    )()
    with pytest.raises(HTTPException) as exc:
        _validate_distribution_revision_chain(None, latest, 2)
    assert exc.value.status_code == 409

    _validate_distribution_revision_chain(latest, latest, 2)
    with pytest.raises(HTTPException) as exc:
        _validate_distribution_revision_chain(latest, latest, 3)
    assert exc.value.status_code == 422
