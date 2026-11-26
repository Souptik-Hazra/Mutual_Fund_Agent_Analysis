"""Populate the local searchable scheme catalogue from MFAPI."""

import argparse
import logging

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from mutual_fund_agent_analysis.data.providers.mfapi import MFAPIClient
from mutual_fund_agent_analysis.database.session import get_session_factory
from mutual_fund_agent_analysis.models import MutualFundScheme

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import the MFAPI scheme directory into the local database."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh the catalogue even when schemes already exist.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    session = get_session_factory()()
    try:
        existing = session.scalar(select(func.count()).select_from(MutualFundScheme)) or 0
        if existing >= 30000 and not args.force:
            logger.info("Scheme catalogue already contains %s schemes; skipping import.", existing)
            return

        imported = 0
        page_size = 1000
        with MFAPIClient() as client:
            offset = 0
            while True:
                page = client.list_schemes(limit=page_size, offset=offset)
                if not page:
                    break
                now_values = [
                    {
                        "scheme_code": item.scheme_code,
                        "scheme_name": item.scheme_name,
                        "isin_growth": item.isin_growth,
                        "isin_div_reinvestment": item.isin_div_reinvestment,
                        "source": "mfapi",
                    }
                    for item in page
                ]
                statement = insert(MutualFundScheme).values(now_values)
                statement = statement.on_conflict_do_update(
                    index_elements=[MutualFundScheme.scheme_code],
                    set_={
                        "scheme_name": statement.excluded.scheme_name,
                        "isin_growth": func.coalesce(
                            statement.excluded.isin_growth, MutualFundScheme.isin_growth
                        ),
                        "isin_div_reinvestment": func.coalesce(
                            statement.excluded.isin_div_reinvestment,
                            MutualFundScheme.isin_div_reinvestment,
                        ),
                        "source": "mfapi",
                        "source_updated_at": func.now(),
                    },
                )
                session.execute(statement)
                imported += len(page)
                offset += len(page)
                logger.info("Imported %s scheme records...", imported)
                if len(page) < page_size:
                    break

        session.commit()
        logger.info("Scheme catalogue ready: %s records processed.", imported)
    except Exception:
        session.rollback()
        logger.exception("Scheme catalogue import failed.")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
