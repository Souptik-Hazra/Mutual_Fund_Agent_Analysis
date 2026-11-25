"""CLI entry point for syncing one scheme's NAV history.

Examples:
    mfa-sync-nav 125497 --provider mfapi --start-date 2020-01-01
    mfa-sync-nav 125497 --provider amfi --start-date 2024-01-01
"""

import argparse
import logging
from datetime import date

from mutual_fund_agent_analysis.data.providers.amfi import AMFIClient
from mutual_fund_agent_analysis.data.providers.mfapi import MFAPIClient
from mutual_fund_agent_analysis.data.services.nav_sync import sync_scheme_nav
from mutual_fund_agent_analysis.database.session import get_session_factory

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync historical NAV for one mutual fund scheme.")
    parser.add_argument("scheme_code", type=int, help="AMFI scheme code")
    parser.add_argument("--provider", choices=("mfapi", "amfi"), default="mfapi")
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    provider_type = AMFIClient if args.provider == "amfi" else MFAPIClient
    with provider_type() as provider:
        session = get_session_factory()()
        try:
            count = sync_scheme_nav(
                session,
                args.scheme_code,
                start_date=args.start_date,
                end_date=args.end_date,
                client=provider,
            )
            session.commit()
            logger.info(
                "Processed %s NAV observations for scheme %s from %s",
                count,
                args.scheme_code,
                args.provider,
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


if __name__ == "__main__":
    main()
