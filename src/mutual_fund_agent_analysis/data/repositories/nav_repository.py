"""Idempotent PostgreSQL upserts for scheme metadata and NAV observations."""
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.data.providers.mfapi import MFAPINavResponse
from mutual_fund_agent_analysis.models import MutualFundScheme, NavObservation


def upsert_nav_response(
    session: Session,
    response: MFAPINavResponse,
    source: str = "mfapi",
) -> int:
    """Upsert scheme metadata and NAV points without duplicating observations."""
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
    scheme_statement = scheme_statement.on_conflict_do_update(
        index_elements=[MutualFundScheme.scheme_code],
        set_={key: value for key, value in scheme_values.items() if key != "scheme_code"},
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
            index_elements=[NavObservation.scheme_code, NavObservation.nav_date],
            set_={
                "nav": nav_statement.excluded.nav,
                "source": nav_statement.excluded.source,
                "fetched_at": nav_statement.excluded.fetched_at,
            },
        )
        session.execute(nav_statement)
        processed += len(batch)
    return processed
