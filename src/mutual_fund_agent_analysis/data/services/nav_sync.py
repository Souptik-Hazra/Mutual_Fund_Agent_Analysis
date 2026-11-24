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
    source: str = "mfapi",
) -> int:
    """Fetch a scheme's NAV history and upsert it atomically.

    A savepoint is used when the caller already owns a transaction, so this
    service does not commit or invalidate the caller's surrounding unit of work.
    """
    owns_client = client is None
    provider = client or MFAPIClient()
    try:
        response = provider.get_nav_history(scheme_code, start_date, end_date)
    finally:
        if owns_client:
            provider.close()

    transaction = session.begin_nested() if session.in_transaction() else session.begin()
    with transaction:
        return upsert_nav_response(session, response, source=source)
