"""Provider-neutral NAV synchronization orchestration."""

from datetime import date

from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.data.providers.contracts import NavProvider
from mutual_fund_agent_analysis.data.providers.mfapi import MFAPIClient
from mutual_fund_agent_analysis.data.repositories.nav_repository import upsert_nav_response


def sync_scheme_nav(
    session: Session,
    scheme_code: int,
    start_date: date | None = None,
    end_date: date | None = None,
    client: NavProvider | None = None,
    source: str | None = None,
) -> int:
    """Fetch and persist NAV history without taking ownership of caller transactions.

    The source is inferred from the adapter. An explicit override is accepted
    only when it agrees with the adapter, preventing provider mislabelling.
    """
    owns_client = client is None
    provider: NavProvider = client or MFAPIClient()
    provider_source = getattr(provider, "source", "mfapi").strip().lower()
    normalized_source = (source or provider_source).strip().lower()
    if normalized_source != provider_source:
        if owns_client:
            provider.close()
        raise ValueError(
            f"Provider source mismatch: adapter={provider_source!r}, requested={normalized_source!r}."
        )

    try:
        response = provider.get_nav_history(scheme_code, start_date, end_date)
    finally:
        if owns_client:
            provider.close()

    transaction = session.begin_nested() if session.in_transaction() else session.begin()
    with transaction:
        return upsert_nav_response(session, response, source=normalized_source)
