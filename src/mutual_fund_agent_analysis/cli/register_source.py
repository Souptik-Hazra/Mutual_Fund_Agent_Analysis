"""Register or update one local research/data source with explicit authority settings."""

from __future__ import annotations

import argparse
import json
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.database.session import get_session_factory
from mutual_fund_agent_analysis.models import DataSource

SOURCE_TYPES = ("official", "provider", "media", "social", "document", "internal")


def _validate_http_url(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{field_name} must be an HTTP(S) base URL without credentials or query.")
    return value.rstrip("/") + "/"


def register_data_source(
    session: Session,
    *,
    source_key: str,
    display_name: str,
    source_type: str,
    authority_tier: int,
    is_official: bool,
    enabled: bool,
    base_url: str,
    terms_url: str | None = None,
    attribution_required: bool = False,
    metadata: dict[str, Any] | None = None,
) -> DataSource:
    """Create or update source registry metadata; caller explicitly supplies authority flags."""
    key = source_key.strip().lower()
    name = display_name.strip()
    if not key or len(key) > 60 or any(not (char.isalnum() or char in "_-") for char in key):
        raise ValueError("source_key must contain 1–60 lowercase letters, digits, '_' or '-'.")
    if not name or len(name) > 160:
        raise ValueError("display_name must contain 1–160 characters.")
    if source_type not in SOURCE_TYPES:
        raise ValueError("Unsupported source_type.")
    if isinstance(authority_tier, bool) or not 1 <= authority_tier <= 5:
        raise ValueError("authority_tier must be an integer from 1 to 5.")
    if is_official and source_type != "official":
        raise ValueError("An official source must use source_type='official'.")
    clean_base_url = _validate_http_url(base_url, "base_url")
    clean_terms_url = _validate_http_url(terms_url, "terms_url")
    metadata_value = metadata or {}
    if not isinstance(metadata_value, dict):
        raise ValueError("metadata must be a JSON object.")

    source = session.get(DataSource, key)
    if source is None:
        source = DataSource(
            source_key=key,
            display_name=name,
            source_type=source_type,
            authority_tier=authority_tier,
            is_official=is_official,
            base_url=clean_base_url,
            terms_url=clean_terms_url,
            attribution_required=attribution_required,
            enabled=enabled,
            metadata_json=metadata_value,
        )
        session.add(source)
    else:
        source.display_name = name
        source.source_type = source_type
        source.authority_tier = authority_tier
        source.is_official = is_official
        source.base_url = clean_base_url
        source.terms_url = clean_terms_url
        source.attribution_required = attribution_required
        source.enabled = enabled
        source.metadata_json = metadata_value

    session.commit()
    session.refresh(source)
    return source


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Register/update one official or third-party data source."
    )
    parser.add_argument("source_key")
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--source-type", choices=SOURCE_TYPES, required=True)
    parser.add_argument("--authority-tier", type=int, choices=range(1, 6), required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--terms-url")
    official = parser.add_mutually_exclusive_group(required=True)
    official.add_argument("--official", dest="is_official", action="store_true")
    official.add_argument("--not-official", dest="is_official", action="store_false")
    enabled = parser.add_mutually_exclusive_group(required=True)
    enabled.add_argument("--enabled", dest="enabled", action="store_true")
    enabled.add_argument("--disabled", dest="enabled", action="store_false")
    parser.add_argument("--attribution-required", action="store_true")
    parser.add_argument(
        "--metadata-json",
        default="{}",
        help="Optional JSON object describing domain, licence/terms decision, or ingestion role.",
    )
    args = parser.parse_args()

    try:
        metadata = json.loads(args.metadata_json)
    except json.JSONDecodeError as exc:
        parser.error(f"--metadata-json is invalid JSON: {exc}")
    if not isinstance(metadata, dict):
        parser.error("--metadata-json must be a JSON object.")

    with get_session_factory()() as session:
        source = register_data_source(
            session,
            source_key=args.source_key,
            display_name=args.display_name,
            source_type=args.source_type,
            authority_tier=args.authority_tier,
            is_official=args.is_official,
            enabled=args.enabled,
            base_url=args.base_url,
            terms_url=args.terms_url,
            attribution_required=args.attribution_required,
            metadata=metadata,
        )
    print(
        json.dumps(
            {
                "source_key": source.source_key,
                "display_name": source.display_name,
                "source_type": source.source_type,
                "authority_tier": source.authority_tier,
                "is_official": source.is_official,
                "enabled": source.enabled,
                "base_url": source.base_url,
                "terms_url": source.terms_url,
                "attribution_required": source.attribution_required,
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
