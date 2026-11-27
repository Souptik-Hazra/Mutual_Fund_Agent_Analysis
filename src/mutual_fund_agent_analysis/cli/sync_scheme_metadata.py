"""Synchronize source-attributed scheme metadata independently of NAV history."""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path
from urllib.parse import urlencode

from sqlalchemy import func, select

from mutual_fund_agent_analysis.data.providers.mfapi import MFAPIClient
from mutual_fund_agent_analysis.data.services.scheme_metadata_sync import persist_catalogue_metadata
from mutual_fund_agent_analysis.database.session import get_session_factory
from mutual_fund_agent_analysis.models import MutualFundScheme, SchemeMetadataObservation

logger = logging.getLogger(__name__)
CHECKPOINT = Path("data/cache/scheme_metadata_offset.txt")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync scheme-name metadata and history from MFAPI without fetching NAV histories."
    )
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--start-offset", type=int)
    parser.add_argument("--max-pages", type=int, help="Optional page limit for controlled runs.")
    parser.add_argument("--reset-checkpoint", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.page_size <= 1000:
        parser.error("--page-size must be between 1 and 1000.")
    if args.max_pages is not None and args.max_pages < 1:
        parser.error("--max-pages must be positive.")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    if args.reset_checkpoint:
        CHECKPOINT.unlink(missing_ok=True)
    offset = args.start_offset if args.start_offset is not None else (
        int(CHECKPOINT.read_text().strip()) if CHECKPOINT.exists() else 0
    )
    if offset < 0:
        parser.error("Offset cannot be negative.")

    pages = 0
    imported = 0
    skipped = 0
    with get_session_factory()() as session, MFAPIClient() as client:
        while args.max_pages is None or pages < args.max_pages:
            page = client.list_schemes(limit=args.page_size, offset=offset)
            if not page:
                CHECKPOINT.unlink(missing_ok=True)
                break
            source_url = "https://api.mfapi.in/mf?" + urlencode(
                {"limit": args.page_size, "offset": offset}
            )
            try:
                for item in page:
                    if persist_catalogue_metadata(session, item, source_url=source_url):
                        imported += 1
                    else:
                        skipped += 1
                session.commit()
            except Exception:
                session.rollback()
                logger.exception("Metadata page failed at offset %s; checkpoint retained.", offset)
                raise
            offset += len(page)
            pages += 1
            CHECKPOINT.write_text(str(offset), encoding="utf-8")
            logger.info(
                "Pages=%s offset=%s new_observations=%s duplicates=%s",
                pages, offset, imported, skipped,
            )
            if len(page) < args.page_size:
                CHECKPOINT.unlink(missing_ok=True)
                break
            time.sleep(1.0)

        total_schemes = session.scalar(select(func.count()).select_from(MutualFundScheme)) or 0
        observed_schemes = session.scalar(
            select(func.count(func.distinct(SchemeMetadataObservation.scheme_code)))
        ) or 0
        logger.info(
            "Metadata sync complete for this run: pages=%s new=%s duplicates=%s "
            "catalogue_schemes=%s schemes_with_metadata_history=%s next_offset=%s",
            pages, imported, skipped, total_schemes, observed_schemes, offset,
        )


if __name__ == "__main__":
    main()
