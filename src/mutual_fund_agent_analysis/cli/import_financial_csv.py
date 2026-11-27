"""Idempotent CSV importers for source-attributed scheme metadata and IDCW records."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.api.schemas.financial import (
    DistributionObservationCreate,
    SchemeMetadataObservationCreate,
)
from mutual_fund_agent_analysis.database.session import get_session_factory
from mutual_fund_agent_analysis.models import (
    DataSource,
    DistributionObservation,
    MutualFundScheme,
    SchemeMetadataObservation,
)

logger = logging.getLogger(__name__)
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_ROWS = 100_000


def _json_object(value: Any, field_name: str) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{field_name} must contain valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name} must contain a JSON object.")
    return parsed


def _source_url(row: dict[str, Any], fallback: str | None) -> str:
    value = row.get("source_url") or fallback
    if not value:
        raise ValueError("Provide source_url in every row or pass --source-url.")
    return str(value).strip()


def _validate_source_policy(
    source: DataSource,
    source_url: str,
    verification_status: str,
) -> None:
    if not source.enabled:
        raise ValueError(f"Source '{source.source_key}' is disabled.")
    parsed = urlparse(source_url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("Evidence source_url must be a valid HTTP(S) URL.")
    if verification_status == "verified":
        if not source.is_official:
            raise ValueError("Only a registered official source can import verified records.")
        if not source.base_url:
            raise ValueError("Verified imports require a registered source base_url.")
    if source.base_url:
        registered_host = (urlparse(source.base_url).hostname or "").lower()
        actual_host = parsed.hostname.lower()
        if not registered_host:
            raise ValueError("Registered source base_url is invalid.")
        if actual_host != registered_host and not actual_host.endswith("." + registered_host):
            raise ValueError("Evidence URL host does not match the registered source host.")


def _content_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def parse_metadata_row(
    row: dict[str, Any],
    *,
    source_key: str,
    source_url: str | None = None,
    verification_status: str = "unverified",
) -> SchemeMetadataObservationCreate:
    """Validate a row without inferring plan, option, or lifecycle classifications."""
    payload = {
        "source_key": source_key,
        "source_url": _source_url(row, source_url),
        "valid_from": row.get("valid_from") or None,
        "valid_to": row.get("valid_to") or None,
        "plan_type": row.get("plan_type") or None,
        "option_type": row.get("option_type") or None,
        "lifecycle_type": row.get("lifecycle_type") or None,
        "expense_ratio": row.get("expense_ratio") or None,
        "expense_ratio_effective_date": row.get("expense_ratio_effective_date") or None,
        "benchmark_code": row.get("benchmark_code") or None,
        "launch_date": row.get("launch_date") or None,
        "closure_date": row.get("closure_date") or None,
        "verification_status": verification_status,
        "verification_note": row.get("verification_note") or None,
        "metadata": _json_object(row.get("metadata_json"), "metadata_json"),
    }
    return SchemeMetadataObservationCreate.model_validate(payload)


def parse_distribution_row(
    row: dict[str, Any],
    *,
    source_key: str,
    source_url: str | None = None,
    verification_status: str = "unverified",
) -> DistributionObservationCreate:
    """Validate one IDCW distribution declaration or correction."""
    payload = {
        "source_key": source_key,
        "external_id": row.get("external_id") or row.get("notice_id"),
        "revision": row.get("revision") or 1,
        "supersedes_distribution_id": row.get("supersedes_distribution_id") or None,
        "source_url": _source_url(row, source_url),
        "ex_date": row.get("ex_date"),
        "record_date": row.get("record_date") or None,
        "payment_date": row.get("payment_date") or None,
        "amount_per_unit": row.get("amount_per_unit"),
        "option_type": row.get("option_type"),
        "status": row.get("status") or "active",
        "verification_status": verification_status,
        "published_at": row.get("published_at") or None,
        "metadata": _json_object(row.get("metadata_json"), "metadata_json"),
    }
    return DistributionObservationCreate.model_validate(payload)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read bounded UTF-8 CSV with BOM support."""
    if not path.is_file():
        raise ValueError(f"CSV file does not exist: {path}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("CSV file exceeds the 20 MB import limit.")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError("CSV must include a header row.")
        rows = list(reader)
    if not rows:
        raise ValueError("CSV contains no data rows.")
    if len(rows) > MAX_ROWS:
        raise ValueError(f"CSV exceeds the {MAX_ROWS:,} row import limit.")
    return rows


def import_scheme_metadata_rows(
    session: Session,
    rows: list[dict[str, Any]],
    *,
    source_key: str,
    source_url: str | None = None,
    verification_status: str = "unverified",
) -> dict[str, Any]:
    source = session.get(DataSource, source_key)
    if source is None:
        raise ValueError(f"Source '{source_key}' is not registered.")
    if verification_status not in {"unverified", "verified"}:
        raise ValueError("CLI imports support only unverified or verified status.")
    counts = {"imported": 0, "skipped": 0, "failed": 0}
    errors: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=2):
        try:
            record = parse_metadata_row(
                row,
                source_key=source_key,
                source_url=source_url,
                verification_status=verification_status,
            )
            evidence_url = str(record.source_url)
            _validate_source_policy(source, evidence_url, verification_status)
            scheme_code = int(row.get("scheme_code") or 0)
            if scheme_code <= 0:
                raise ValueError("scheme_code must be a positive integer.")
            scheme = session.get(MutualFundScheme, scheme_code)
            if scheme is None:
                raise ValueError(f"Unknown local scheme_code: {scheme_code}.")
            payload_hash = _content_hash(record.model_dump(mode="json"))
            existing = session.scalar(
                select(SchemeMetadataObservation).where(
                    SchemeMetadataObservation.scheme_code == scheme_code,
                    SchemeMetadataObservation.source_key == source_key,
                    SchemeMetadataObservation.content_hash == payload_hash,
                )
            )
            if existing is not None:
                counts["skipped"] += 1
                continue
            with session.begin_nested():
                observation = SchemeMetadataObservation(
                    scheme_code=scheme_code,
                    source_key=source_key,
                    source_url=evidence_url,
                    content_hash=payload_hash,
                    **record.model_dump(exclude={"source_key", "source_url", "metadata"}),
                    metadata_json=record.metadata,
                )
                session.add(observation)
                if verification_status == "verified":
                    for field_name in (
                        "plan_type",
                        "option_type",
                        "lifecycle_type",
                        "launch_date",
                        "closure_date",
                    ):
                        value = getattr(record, field_name)
                        if value is not None:
                            setattr(scheme, field_name, value)
                    if record.expense_ratio is not None:
                        scheme.effective_expense_ratio = record.expense_ratio
                        scheme.expense_ratio_effective_date = record.expense_ratio_effective_date
                        scheme.expense_ratio_source_key = source_key

                    # Verified official-source metadata may enrich these
                    # canonical descriptive fields. Ignore absent/non-string
                    # values and preserve already-populated values.
                    for field_name in (
                        "fund_house",
                        "scheme_type",
                        "scheme_category",
                        "isin_growth",
                        "isin_div_reinvestment",
                    ):
                        value = record.metadata.get(field_name)
                        if isinstance(value, str) and value.strip():
                            if getattr(scheme, field_name) is None:
                                setattr(scheme, field_name, value.strip())
                session.flush()
            counts["imported"] += 1
        except (ValueError, ValidationError) as exc:
            counts["failed"] += 1
            errors.append({"row": row_number, "error": str(exc)})
    session.commit()
    return {"source_key": source_key, "counts": counts, "errors": errors}


def import_distribution_rows(
    session: Session,
    rows: list[dict[str, Any]],
    *,
    source_key: str,
    source_url: str | None = None,
    verification_status: str = "unverified",
) -> dict[str, Any]:
    source = session.get(DataSource, source_key)
    if source is None:
        raise ValueError(f"Source '{source_key}' is not registered.")
    if verification_status not in {"unverified", "verified"}:
        raise ValueError("CLI imports support only unverified or verified status.")
    counts = {"imported": 0, "skipped": 0, "failed": 0}
    errors: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=2):
        try:
            record = parse_distribution_row(
                row,
                source_key=source_key,
                source_url=source_url,
                verification_status=verification_status,
            )
            evidence_url = str(record.source_url)
            _validate_source_policy(source, evidence_url, verification_status)
            scheme_code = int(row.get("scheme_code") or 0)
            if scheme_code <= 0:
                raise ValueError("scheme_code must be a positive integer.")
            if session.get(MutualFundScheme, scheme_code) is None:
                raise ValueError(f"Unknown local scheme_code: {scheme_code}.")
            payload_hash = _content_hash(record.model_dump(mode="json"))
            existing = session.scalar(
                select(DistributionObservation).where(
                    DistributionObservation.scheme_code == scheme_code,
                    DistributionObservation.source_key == source_key,
                    DistributionObservation.external_id == record.external_id,
                    DistributionObservation.revision == record.revision,
                )
            )
            if existing is not None:
                if existing.content_hash != payload_hash:
                    raise ValueError(
                        "This distribution revision exists with different content; "
                        "increase revision and set supersedes_distribution_id."
                    )
                counts["skipped"] += 1
                continue
            previous = None
            if record.supersedes_distribution_id is not None:
                previous = session.get(DistributionObservation, record.supersedes_distribution_id)
                if (
                    previous is None
                    or previous.scheme_code != scheme_code
                    or previous.source_key != source_key
                    or previous.external_id != record.external_id
                    or previous.revision >= record.revision
                    or previous.status != "active"
                ):
                    raise ValueError("Distribution correction chain is invalid.")
            with session.begin_nested():
                observation = DistributionObservation(
                    scheme_code=scheme_code,
                    source_key=source_key,
                    external_id=record.external_id,
                    source_url=evidence_url,
                    content_hash=payload_hash,
                    **record.model_dump(
                        exclude={
                            "source_key",
                            "external_id",
                            "source_url",
                            "metadata",
                        }
                    ),
                    metadata_json=record.metadata,
                )
                if previous is not None:
                    previous.status = "revised"
                session.add(observation)
                session.flush()
            counts["imported"] += 1
        except (ValueError, ValidationError) as exc:
            counts["failed"] += 1
            errors.append({"row": row_number, "error": str(exc)})
    session.commit()
    return {
        "source_key": source_key,
        "counts": counts,
        "errors": errors,
        "coverage_attestation_created": False,
        "coverage_note": (
            "CSV ingestion never establishes completeness. Add a separate verified official-source "
            "coverage attestation only after checking the full requested date interval."
        ),
    }


def _common_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--source-key", required=True)
    parser.add_argument("--source-url")
    parser.add_argument(
        "--verification-status",
        choices=("unverified", "verified"),
        default="unverified",
        help="Defaults to unverified; verified requires an enabled official source.",
    )
    return parser


def _run_import(kind: str) -> None:
    parser = _common_parser(
        "Import scheme metadata CSV." if kind == "metadata" else "Import IDCW distribution CSV."
    )
    args = parser.parse_args()
    rows = read_csv_rows(args.csv_path)
    with get_session_factory()() as session:
        report = (
            import_scheme_metadata_rows(
                session,
                rows,
                source_key=args.source_key,
                source_url=args.source_url,
                verification_status=args.verification_status,
            )
            if kind == "metadata"
            else import_distribution_rows(
                session,
                rows,
                source_key=args.source_key,
                source_url=args.source_url,
                verification_status=args.verification_status,
            )
        )
    print(json.dumps(report, indent=2, default=str))
    if report["counts"]["failed"]:
        raise SystemExit(1)


def import_scheme_metadata_main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _run_import("metadata")


def import_idcw_distributions_main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _run_import("distribution")
