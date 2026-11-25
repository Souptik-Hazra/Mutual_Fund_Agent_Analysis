"""CLI entry point for historical benchmark TRI ingestion.

Example:
    mfa-sync-benchmark "NIFTY 50" --start-date 2020-01-01 --end-date 2026-11-25
"""

import argparse
import logging
from datetime import date

from mutual_fund_agent_analysis.data.providers.niftyindices import NiftyIndicesClient
from mutual_fund_agent_analysis.data.services.benchmark_sync import sync_benchmark_history
from mutual_fund_agent_analysis.database.session import get_session_factory

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync historical Nifty benchmark TRI/NTR.")
    parser.add_argument("benchmark_code", help="Canonical Nifty Indices name, e.g. NIFTY 50")
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    with NiftyIndicesClient() as provider:
        session = get_session_factory()()
        try:
            count = sync_benchmark_history(
                session,
                args.benchmark_code,
                args.start_date,
                args.end_date,
                client=provider,
            )
            session.commit()
            logger.info("Processed %s TRI observations for %s", count, args.benchmark_code)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


if __name__ == "__main__":
    main()
