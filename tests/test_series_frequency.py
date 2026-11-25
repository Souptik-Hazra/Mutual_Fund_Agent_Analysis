from datetime import date
from decimal import Decimal

import pytest

from mutual_fund_agent_analysis.analytics.series import (
    FREQUENCY_PERIODS_PER_YEAR,
    PricePoint,
    period_returns,
    resample_prices,
)


def points(*items: tuple[str, str]) -> list[PricePoint]:
    return [PricePoint(date.fromisoformat(day), Decimal(value)) for day, value in items]


def test_daily_frequency_preserves_all_real_observations():
    source = points(
        ("2024-01-01", "100"),
        ("2024-01-02", "101"),
        ("2024-01-03", "99"),
    )
    assert resample_prices(source, "daily") == source


def test_weekly_frequency_selects_last_available_nav_without_filling():
    source = points(
        ("2024-01-01", "100"),
        ("2024-01-03", "101"),
        ("2024-01-05", "102"),
        ("2024-01-08", "103"),
        ("2024-01-10", "104"),
    )
    sampled = resample_prices(source, "weekly")
    assert [point.date.isoformat() for point in sampled] == [
        "2024-01-01",
        "2024-01-05",
        "2024-01-10",
    ]
    assert period_returns(sampled)[0].start_date == date(2024, 1, 1)


def test_monthly_frequency_keeps_first_base_and_month_end_observations():
    source = points(
        ("2024-01-02", "100"),
        ("2024-01-31", "102"),
        ("2024-02-28", "104"),
        ("2024-03-28", "106"),
    )
    sampled = resample_prices(source, "monthly")
    assert [point.date.isoformat() for point in sampled] == [
        "2024-01-02",
        "2024-01-31",
        "2024-02-28",
        "2024-03-28",
    ]


@pytest.mark.parametrize(
    ("frequency", "expected"),
    [
        (
            "quarterly",
            ["2024-01-02", "2024-03-28", "2024-04-01", "2024-12-31", "2025-01-02"],
        ),
        ("yearly", ["2024-01-02", "2024-12-31", "2025-01-02"]),
    ],
)
def test_longer_periods_use_last_observed_date(frequency, expected):
    source = points(
        ("2024-01-02", "100"),
        ("2024-03-28", "101"),
        ("2024-04-01", "102"),
        ("2024-12-31", "103"),
        ("2025-01-02", "104"),
    )
    sampled = resample_prices(source, frequency)
    assert [point.date.isoformat() for point in sampled] == expected


def test_frequency_annualisation_mapping_is_explicit():
    assert FREQUENCY_PERIODS_PER_YEAR == {
        "daily": 252,
        "weekly": 52,
        "monthly": 12,
        "quarterly": 4,
        "yearly": 1,
    }


def test_unknown_frequency_is_rejected():
    with pytest.raises(ValueError, match="frequency"):
        resample_prices(points(("2024-01-01", "100"), ("2024-01-02", "101")), "hourly")
