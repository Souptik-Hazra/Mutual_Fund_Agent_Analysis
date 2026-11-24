"""Idempotent PostgreSQL upserts for scheme metadata and NAV observations."""

from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.data.providers.mfapi import MFAPINavResponse
from mutual_fund_agent_analysis.models import MutualFundScheme, NavObservation


def upsert_nav_response(
    session: Session,
    response: MFAPINavResponse,
    source: str = "mfapi",
) -> int:
    """Upsert scheme metadata and source-specific NAV observations."""
    metadata = response.meta
    scheme_values = {
        "scheme_code": metadata.scheme_code,
        "scheme_name": metadata.scheme_name,
        "fund_house": metadata.fund_house,
        "scheme_type": metadata.scheme_type,
        "scheme_category": metadata.scheme_category,
        "isin_growth": metadata.isin_growth,
        "isin_div_reinvestment": metadata.isin_div_reinvestment,
        "source": source,
        "source_updated_at": datetime.now(UTC),
    }
    scheme_statement = insert(MutualFundScheme).values(**scheme_values)
    excluded = scheme_statement.excluded
    scheme_statement = scheme_statement.on_conflict_do_update(
        index_elements=[MutualFundScheme.scheme_code],
        set_={
            "scheme_name": excluded.scheme_name,
            "fund_house": func.coalesce(excluded.fund_house, MutualFundScheme.fund_house),
            "scheme_type": func.coalesce(excluded.scheme_type, MutualFundScheme.scheme_type),
            "scheme_category": func.coalesce(
                excluded.scheme_category, MutualFundScheme.scheme_category
            ),
            "isin_growth": func.coalesce(excluded.isin_growth, MutualFundScheme.isin_growth),
            "isin_div_reinvestment": func.coalesce(
                excluded.isin_div_reinvestment, MutualFundScheme.isin_div_reinvestment
            ),
            "source": excluded.source,
            "source_updated_at": excluded.source_updated_at,
        },
    )
    session.execute(scheme_statement)

    if not response.data:
        return 0

    fetched_at = datetime.now(UTC)
    nav_values = [
        {
            "scheme_code": metadata.scheme_code,
            "nav_date": point.date,
            "nav": point.nav,
            "source": source,
            "fetched_at": fetched_at,
        }
        for point in response.data
    ]
    processed = 0
    for offset in range(0, len(nav_values), 1000):
        batch = nav_values[offset : offset + 1000]
        nav_statement = insert(NavObservation).values(batch)
        nav_statement = nav_statement.on_conflict_do_update(
            index_elements=[
                NavObservation.scheme_code,
                NavObservation.nav_date,
                NavObservation.source,
            ],
            set_={
                "nav": nav_statement.excluded.nav,
                "fetched_at": nav_statement.excluded.fetched_at,
            },
        )
        session.execute(nav_statement)
        processed += len(batch)
    return processed
