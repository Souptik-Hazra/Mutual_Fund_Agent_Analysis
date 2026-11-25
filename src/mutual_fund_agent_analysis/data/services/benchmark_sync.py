"""Benchmark TRI ingestion orchestration."""

from datetime import date

from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.data.providers.niftyindices import NiftyIndicesClient
from mutual_fund_agent_analysis.data.repositories.benchmark_repository import (
    upsert_benchmark_response,
)


def sync_benchmark_history(
    session: Session,
    benchmark_code: str,
    start_date: date,
    end_date: date,
    client: NiftyIndicesClient | None = None,
) -> int:
    """Fetch and persist one canonical Nifty benchmark's TRI/NTR history."""
    owns_client = client is None
    provider = client or NiftyIndicesClient()
    try:
        response = provider.get_history(benchmark_code, start_date, end_date)
    finally:
        if owns_client:
            provider.close()

    transaction = session.begin_nested() if session.in_transaction() else session.begin()
    with transaction:
        return upsert_benchmark_response(session, response, source=provider.source)
