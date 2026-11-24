"""NAV synchronization orchestration."""
from datetime import date

from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.data.providers.mfapi import MFAPIClient
from mutual_fund_agent_analysis.data.repositories.nav_repository import upsert_nav_response


def sync_scheme_nav(
    session: Session,
    scheme_code: int,
    start_date: date | None = None,
    end_date: date | None = None,
    client: MFAPIClient | None = None,
) -> int:
    """Fetch a scheme's NAV history, validate it, then atomically upsert it."""
    owns_client = client is None
    provider = client or MFAPIClient()
    try:
        response = provider.get_nav_history(scheme_code, start_date, end_date)
    finally:
        if owns_client:
            provider.close()

    with session.begin():
        return upsert_nav_response(session, response)
