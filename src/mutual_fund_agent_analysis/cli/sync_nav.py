"""CLI entry point for syncing one scheme's NAV history.

Example:
    mfa-sync-nav 125497 --start-date 2020-01-01
"""

import argparse
import logging
from datetime import date

from mutual_fund_agent_analysis.data.services.nav_sync import sync_scheme_nav
from mutual_fund_agent_analysis.database.session import get_session_factory

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync historical NAV for one MFAPI scheme.")
    parser.add_argument("scheme_code", type=int, help="AMFI scheme code")
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    session = get_session_factory()()
    try:
        count = sync_scheme_nav(
            session,
            args.scheme_code,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        logger.info("Processed %s NAV observations for scheme %s", count, args.scheme_code)
    finally:
        session.close()


if __name__ == "__main__":
    main()
