"""Generate a local data-coverage report and optionally probe live providers."""

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.data.providers.amfi import AMFIClient
from mutual_fund_agent_analysis.data.providers.mfapi import MFAPIClient
from mutual_fund_agent_analysis.data.providers.niftyindices import NiftyIndicesClient
from mutual_fund_agent_analysis.data.providers.twelvedata import TwelveDataClient
from mutual_fund_agent_analysis.core.config import get_settings
from mutual_fund_agent_analysis.database.session import get_session_factory
from mutual_fund_agent_analysis.models import (
    BenchmarkObservation,
    DataSource,
    DistributionCoverageAttestation,
    DistributionObservation,
    DocumentChunk,
    MarketEvent,
    MutualFundScheme,
    NavObservation,
    NavReconciliation,
    PortfolioHolding,
    PortfolioSnapshot,
    ProviderSyncRun,
    ResearchDocument,
    SchemeMetadataObservation,
    SocialPost,
)


def _count(session: Session, model: Any) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def build_coverage_report(session: Session) -> dict[str, Any]:
    """Summarize local table coverage without implying data quality from row counts."""
    nav = session.execute(
        select(func.min(NavReconciliation.nav_date), func.max(NavReconciliation.nav_date))
    ).one()
    benchmark = session.execute(
        select(
            func.min(BenchmarkObservation.observation_date),
            func.max(BenchmarkObservation.observation_date),
        )
    ).one()
    sync = session.execute(
        select(func.count(ProviderSyncRun.id), func.max(ProviderSyncRun.fetched_at))
    ).one()
    return {
        "generated_at": date.today().isoformat(),
        "counts": {
            "schemes": _count(session, MutualFundScheme),
            "nav_observations": _count(session, NavObservation),
            "nav_reconciliations": _count(session, NavReconciliation),
            "nav_conflicts": int(
                session.scalar(
                    select(func.count())
                    .select_from(NavReconciliation)
                    .where(NavReconciliation.status == "conflict")
                )
                or 0
            ),
            "benchmark_observations": _count(session, BenchmarkObservation),
            "portfolio_snapshots": _count(session, PortfolioSnapshot),
            "portfolio_holdings": _count(session, PortfolioHolding),
            "market_events": _count(session, MarketEvent),
            "social_posts": _count(session, SocialPost),
            "research_documents": _count(session, ResearchDocument),
            "document_chunks": _count(session, DocumentChunk),
            "registered_sources": _count(session, DataSource),
            "scheme_metadata_observations": _count(session, SchemeMetadataObservation),
            "distribution_observations": _count(session, DistributionObservation),
            "distribution_coverage_attestations": _count(session, DistributionCoverageAttestation),
        },
        "ranges": {
            "reconciled_nav": {
                "first_date": nav[0].isoformat() if nav[0] else None,
                "last_date": nav[1].isoformat() if nav[1] else None,
            },
            "benchmark": {
                "first_date": benchmark[0].isoformat() if benchmark[0] else None,
                "last_date": benchmark[1].isoformat() if benchmark[1] else None,
            },
        },
        "provider_sync": {
            "run_count": int(sync[0] or 0),
            "latest_fetched_at": sync[1].isoformat() if sync[1] else None,
        },
        "migrations": {
            "applied_heads": list(
                session.connection()
                .execute(text("SELECT version_num FROM alembic_version"))
                .scalars()
            )
        },
        "limitations": [
            "Counts and date ranges do not establish source completeness or correctness.",
            (
                "Run with --live and explicit identifiers to verify current provider "
                "access and schemas."
            ),
            "AMC, distribution and source-rights coverage need individual provider verification.",
        ],
    }


def _observation_quality(points: list[Any], start: date, end: date) -> dict[str, Any]:
    dates = [point.date for point in points]
    return {
        "duplicate_date_count": len(dates) - len(set(dates)),
        "out_of_order_pair_count": sum(
            current < previous for previous, current in zip(dates, dates[1:], strict=False)
        ),
        "out_of_window_count": sum(not start <= item <= end for item in dates),
    }


def _reconcile_nav(
    mfapi: dict[str, str], amfi: dict[str, str]
) -> dict[str, Any]:
    from decimal import Decimal

    common = sorted(mfapi.keys() & amfi.keys())
    conflicts = [
        {
            "date": day,
            "mfapi_nav": mfapi[day],
            "amfi_nav": amfi[day],
            "absolute_difference": str(abs(Decimal(mfapi[day]) - Decimal(amfi[day]))),
        }
        for day in common
        if abs(Decimal(mfapi[day]) - Decimal(amfi[day])) > Decimal("0.0001")
    ]
    return {
        "matched_date_count": len(common),
        "mfapi_only_date_count": len(mfapi.keys() - amfi.keys()),
        "amfi_only_date_count": len(amfi.keys() - mfapi.keys()),
        "conflict_count": len(conflicts),
        "conflicts": conflicts[:50],
        "tolerance": "0.0001 NAV units",
    }


def probe_twelve_data(symbol: str, exchange: str) -> dict[str, Any]:
    """Probe only the requested quote endpoint and exact symbol/exchange identity."""
    settings = get_settings()
    if settings.twelve_data_api_key is None:
        return {"status": "blocked", "reason": "Twelve Data API key is not configured."}
    if not settings.twelve_data_exchange_access_confirmed:
        return {
            "status": "blocked",
            "reason": "Exchange access has not been explicitly confirmed in local settings.",
        }
    client = TwelveDataClient(settings.twelve_data_api_key.get_secret_value())
    try:
        quote = client.get_quote(symbol, exchange)
        return {
            "status": "success",
            "requested_symbol": symbol.strip().upper(),
            "requested_exchange": exchange.strip().upper(),
            "returned_symbol": quote.symbol,
            "returned_exchange": quote.exchange,
            "observed_at": quote.observed_at.isoformat(),
            "price": str(quote.price),
            "change_pct": str(quote.change_pct) if quote.change_pct is not None else None,
            "market_status": quote.market_status,
            "coverage_scope": "single quote endpoint only",
            "limitations": [
                "A successful quote does not establish plan-wide exchange entitlement.",
                "No historical price, comprehensive fundamentals, or corporate-action coverage is inferred.",
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "coverage_scope": "single quote endpoint only",
        }
    finally:
        client.close()


def probe_live_sources(
    scheme_code: int,
    benchmark_code: str,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    """Probe each provider independently; failures are recorded, not hidden."""
    outcomes: dict[str, Any] = {}
    operations = {
        "mfapi": lambda: _probe_mfapi(scheme_code, start_date, end_date),
        "amfi": lambda: _probe_amfi(scheme_code, start_date, end_date),
        "niftyindices": lambda: _probe_nifty(benchmark_code, start_date, end_date),
    }
    for name, operation in operations.items():
        try:
            outcomes[name] = {"status": "success", **operation()}
        except Exception as exc:  # noqa: BLE001
            outcomes[name] = {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
    mfapi_data = outcomes.get("mfapi", {}).pop("_nav_by_date", {})
    amfi_data = outcomes.get("amfi", {}).pop("_nav_by_date", {})
    if outcomes.get("mfapi", {}).get("status") == "success" and outcomes.get("amfi", {}).get("status") == "success":
        outcomes["nav_reconciliation"] = _reconcile_nav(mfapi_data, amfi_data)
    return outcomes


def _probe_mfapi(code: int, start: date, end: date) -> dict[str, Any]:
    with MFAPIClient(timeout_seconds=15) as client:
        response = client.get_nav_history(code, start, end)
    return {
        "scheme_code": response.meta.scheme_code,
        "scheme_name": response.meta.scheme_name,
        "observation_count": len(response.data),
        "first_date": response.data[0].date.isoformat() if response.data else None,
        "last_date": response.data[-1].date.isoformat() if response.data else None,
        "quality": _observation_quality(response.data, start, end),
        "_nav_by_date": {point.date.isoformat(): str(point.nav) for point in response.data},
    }


def _probe_amfi(code: int, start: date, end: date) -> dict[str, Any]:
    with AMFIClient(timeout_seconds=20, chunk_days=7, max_attempts=1) as client:
        response = client.get_nav_history(code, start, end)
    return {
        "scheme_code": response.meta.scheme_code,
        "scheme_name": response.meta.scheme_name,
        "observation_count": len(response.data),
        "raw_chunks": (len(response.raw_payload.get("chunks", [])) if response.raw_payload else 0),
        "quality": _observation_quality(response.data, start, end),
        "_nav_by_date": {point.date.isoformat(): str(point.nav) for point in response.data},
    }


def _probe_nifty(code: str, start: date, end: date) -> dict[str, Any]:
    with NiftyIndicesClient(timeout_seconds=20, max_attempts=1, chunk_days=30) as client:
        response = client.get_history(code, start, end)
    return {
        "benchmark_code": response.benchmark_code,
        "benchmark_name": response.benchmark_name,
        "observation_count": len(response.data),
        "first_date": response.data[0].date.isoformat() if response.data else None,
        "last_date": response.data[-1].date.isoformat() if response.data else None,
        "quality": _observation_quality(response.data, start, end),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit local mutual-fund data coverage.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/local-coverage-audit.json"))
    parser.add_argument(
        "--live",
        action="store_true",
        help="Make bounded, read-only provider requests.",
    )
    parser.add_argument("--scheme-code", type=int)
    parser.add_argument("--benchmark-code")
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--twelve-data-symbol")
    parser.add_argument("--twelve-data-exchange")
    args = parser.parse_args()

    if bool(args.twelve_data_symbol) != bool(args.twelve_data_exchange):
        parser.error("--twelve-data-symbol and --twelve-data-exchange must be supplied together.")
    if (args.twelve_data_symbol or args.twelve_data_exchange) and not args.live:
        parser.error("Twelve Data probing requires --live.")

    if args.live:
        required = (args.scheme_code, args.benchmark_code, args.start_date, args.end_date)
        if any(value is None for value in required):
            parser.error(
                "--live requires --scheme-code, --benchmark-code, --start-date and --end-date."
            )
        if args.scheme_code <= 0:
            parser.error("--scheme-code must be positive.")
        if args.start_date > args.end_date:
            parser.error("--start-date cannot be later than --end-date.")
        if (args.end_date - args.start_date).days > 30:
            parser.error("Live audit windows are limited to 31 calendar days.")

    with get_session_factory()() as session:
        report = build_coverage_report(session)
    if args.live:
        report["live_provider_probes"] = probe_live_sources(
            args.scheme_code, args.benchmark_code, args.start_date, args.end_date
        )
        if args.twelve_data_symbol and args.twelve_data_exchange:
            report["live_provider_probes"]["twelvedata"] = probe_twelve_data(
                args.twelve_data_symbol, args.twelve_data_exchange
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
