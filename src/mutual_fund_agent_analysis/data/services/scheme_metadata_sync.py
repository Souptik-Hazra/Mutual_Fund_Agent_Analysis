"""Independent, source-attributed scheme metadata synchronization from MFAPI catalogue."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.data.providers.mfapi import MFAPIScheme
from mutual_fund_agent_analysis.models import DataSource, MutualFundScheme, SchemeMetadataObservation


def classify_scheme_name(name: str) -> tuple[str | None, str | None]:
    """Extract only explicit plan/option labels; never guess missing classifications."""
    normalized = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    plan = "direct" if re.search(r"\bdirect plan\b", normalized) else (
        "regular" if re.search(r"\bregular plan\b", normalized) else None
    )
    option = None
    if re.search(r"\bgrowth\b", normalized):
        option = "growth"
    elif re.search(r"\bidcw\b.*\breinvestment\b|\breinvestment\b.*\bidcw\b", normalized):
        option = "idcw_reinvestment"
    elif re.search(r"\bidcw\b.*\bpayout\b|\bpayout\b.*\bidcw\b", normalized):
        option = "idcw_payout"
    elif re.search(r"\bdividend\b.*\breinvestment\b|\breinvestment\b.*\bdividend\b", normalized):
        option = "idcw_reinvestment"
    elif re.search(r"\bdividend\b.*\bpayout\b|\bpayout\b.*\bdividend\b", normalized):
        option = "idcw_payout"
    return plan, option


def persist_catalogue_metadata(
    session: Session,
    item: MFAPIScheme,
    *,
    source_url: str,
    observed_at: datetime | None = None,
) -> bool:
    """Persist a catalogue snapshot idempotently and safely enrich explicit master fields."""
    source = session.get(DataSource, "mfapi")
    if source is None or not source.enabled:
        raise ValueError("The MFAPI source must be registered and enabled.")
    scheme = session.get(MutualFundScheme, item.scheme_code)
    if scheme is None:
        scheme = MutualFundScheme(
            scheme_code=item.scheme_code,
            scheme_name=item.scheme_name,
            source="mfapi",
        )
        session.add(scheme)
        session.flush()

    plan_type, option_type = classify_scheme_name(item.scheme_name)
    raw = {
        "scheme_code": item.scheme_code,
        "scheme_name": item.scheme_name,
        "isin_growth": item.isin_growth,
        "isin_div_reinvestment": item.isin_div_reinvestment,
    }
    digest = hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    existing = session.execute(
        insert(SchemeMetadataObservation)
        .values(
            scheme_code=item.scheme_code,
            source_key="mfapi",
            source_url=source_url,
            content_hash=digest,
            observed_at=observed_at or datetime.now(UTC),
            plan_type=plan_type,
            option_type=option_type,
            verification_status="unverified",
            verification_note="Classification parsed from explicit MFAPI scheme-name labels; unverified.",
            metadata_json=raw,
        )
        .on_conflict_do_nothing(
            constraint="uq_scheme_metadata_source_hash"
        )
        .returning(SchemeMetadataObservation.metadata_id)
    ).scalar_one_or_none()

    scheme.scheme_name = item.scheme_name
    scheme.isin_growth = item.isin_growth or scheme.isin_growth
    scheme.isin_div_reinvestment = item.isin_div_reinvestment or scheme.isin_div_reinvestment
    scheme.plan_type = plan_type or scheme.plan_type
    scheme.option_type = option_type or scheme.option_type
    scheme.source_updated_at = observed_at or datetime.now(UTC)
    return existing is not None
