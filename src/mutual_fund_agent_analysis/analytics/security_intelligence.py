"""Security-level intelligence built from dated provider observations and AMC disclosures."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.models.research import PortfolioHolding, PortfolioSnapshot
from mutual_fund_agent_analysis.models.security import SecurityMarketObservation

FUNDAMENTAL_UNITS = {
    "market_cap": "provider currency; magnitude is not normalized",
    "pe_ratio": "multiple",
    "pb_ratio": "multiple",
    "roe_pct": "percent",
    "debt_to_equity": "multiple",
    "dividend_yield_pct": "percent",
    "eps": "provider currency per share",
    "book_value": "provider currency per share",
    "revenue": "provider currency; magnitude is not normalized",
    "net_profit": "provider currency; magnitude is not normalized",
    "total_debt": "provider currency; magnitude is not normalized",
    "total_equity": "provider currency; magnitude is not normalized",
    "operating_margin_pct": "percent",
    "profit_margin_pct": "percent",
    "revenue_growth_pct": "percent",
    "profit_growth_pct": "percent",
    "promoter_pledge_pct": "percent of promoter holding",
}


def security_profile(
    session: Session,
    security_key: str,
    *,
    as_of: date | None = None,
    scheme_codes: list[int] | None = None,
    history_limit: int = 100,
    history_type: str = "quotes",
) -> dict[str, Any]:
    """Return independent, source-attributed quote, fundamentals and event timelines."""
    key = security_key.strip().upper()
    if len(key) < 2:
        raise ValueError("security_key must contain at least two characters.")
    if not 1 <= history_limit <= 500:
        raise ValueError("history_limit must be between 1 and 500.")
    if history_type not in {"quotes", "fundamentals", "events", "all"}:
        raise ValueError("history_type must be quotes, fundamentals, events, or all.")

    observation_filter = or_(
        SecurityMarketObservation.security_key == key,
        SecurityMarketObservation.isin == key,
    )
    base_statement = select(SecurityMarketObservation).where(observation_filter)
    if as_of:
        cutoff = datetime.combine(as_of, time.max, tzinfo=UTC)
        base_statement = base_statement.where(SecurityMarketObservation.observed_at <= cutoff)

    ordering = (
        SecurityMarketObservation.observed_at.desc(),
        SecurityMarketObservation.observation_id.desc(),
    )
    latest = session.scalars(base_statement.order_by(*ordering).limit(1)).first()
    history_statement = base_statement
    if history_type == "fundamentals":
        history_statement = history_statement.where(SecurityMarketObservation.fundamentals_json != {})
    elif history_type == "events":
        history_statement = history_statement.where(SecurityMarketObservation.corporate_events_json != [])
    elif history_type == "quotes":
        history_statement = history_statement.where(SecurityMarketObservation.last_price.is_not(None))
    observations = session.scalars(
        history_statement.order_by(*ordering).limit(history_limit)
    ).all()

    # Quote-only syncs are frequent. Do not let them evict the latest dated
    # fundamentals or event payload from the bounded quote-history window.
    fundamentals_observation = session.scalars(
        base_statement.where(SecurityMarketObservation.fundamentals_json != {})
        .order_by(*ordering)
        .limit(1)
    ).first()
    event_observation = session.scalars(
        base_statement.where(SecurityMarketObservation.corporate_events_json != [])
        .order_by(*ordering)
        .limit(1)
    ).first()

    snapshot_statement = select(PortfolioSnapshot).where(
        PortfolioSnapshot.effective_date <= (as_of or date.max),
        PortfolioSnapshot.status.in_(["complete", "partial"]),
    )
    if scheme_codes:
        snapshot_statement = snapshot_statement.where(
            PortfolioSnapshot.scheme_code.in_(scheme_codes)
        )
    snapshots = session.scalars(
        snapshot_statement.order_by(
            PortfolioSnapshot.scheme_code,
            PortfolioSnapshot.effective_date.desc(),
            PortfolioSnapshot.snapshot_id.desc(),
        )
    ).all()
    latest_by_scheme: dict[int, PortfolioSnapshot] = {}
    for snapshot in snapshots:
        latest_by_scheme.setdefault(snapshot.scheme_code, snapshot)

    positions: list[dict[str, Any]] = []
    if latest_by_scheme:
        holdings = session.scalars(
            select(PortfolioHolding).where(
                PortfolioHolding.snapshot_id.in_(
                    [snapshot.snapshot_id for snapshot in latest_by_scheme.values()]
                ),
                or_(PortfolioHolding.security_key == key, PortfolioHolding.isin == key),
            )
        ).all()
        positions = [
            {
                "scheme_code": latest_by_scheme[row.snapshot_id].scheme_code,
                "snapshot_id": row.snapshot_id,
                "effective_date": latest_by_scheme[row.snapshot_id].effective_date,
                "security_name": row.security_name,
                "asset_class": row.asset_class,
                "sector": row.sector,
                "weight_pct": row.weight_pct,
                "market_value": row.market_value,
                "quantity": row.quantity,
            }
            for row in holdings
        ]

    corporate_events = (
        [
            {
                **event,
                "source_key": event.get("source_key") or event_observation.source_key,
                "canonical_url": event.get("source_url") or event_observation.source_url,
                "retrieved_at": event_observation.retrieved_at,
                "verification_status": event.get("verification_status") or "unverified",
            }
            for event in (event_observation.corporate_events_json or [])
            if isinstance(event, dict)
        ]
        if event_observation
        else []
    )

    freshness_reference_date = as_of or date.today()
    freshness_reference_time = (
        datetime.combine(freshness_reference_date, time.max, tzinfo=UTC)
        if as_of
        else datetime.now(UTC)
    )
    quote_age_hours = (
        max(
            0.0,
            (freshness_reference_time - latest.observed_at.astimezone(UTC)).total_seconds() / 3600,
        )
        if latest
        else None
    )
    quote_freshness = (
        "unavailable"
        if latest is None
        else "fresh"
        if quote_age_hours is not None and quote_age_hours <= 24
        else "stale"
    )
    fundamentals_as_of = (
        fundamentals_observation.fundamentals_as_of if fundamentals_observation else None
    )
    fundamentals_age_days = (
        (freshness_reference_date - fundamentals_as_of).days if fundamentals_as_of else None
    )
    fundamentals_freshness = (
        "unavailable"
        if fundamentals_observation is None
        else "fresh"
        if fundamentals_age_days is not None and 0 <= fundamentals_age_days <= 180
        else "stale"
    )

    return {
        "security_key": key,
        "as_of": as_of,
        "availability": "available" if latest else "no_market_observation",
        "identity": {
            "security_name": latest.security_name
            if latest
            else (positions[0]["security_name"] if positions else key),
            "isin": latest.isin if latest else None,
            "symbol": latest.symbol if latest else None,
            "exchange": latest.exchange if latest else None,
        },
        "market": None
        if latest is None
        else {
            "last_price": latest.last_price,
            "change_pct": latest.change_pct,
            "day_high": latest.day_high,
            "day_low": latest.day_low,
            "volume": latest.volume,
            "market_status": latest.market_status,
            "observed_at": latest.observed_at,
            "retrieved_at": latest.retrieved_at,
            "source_key": latest.source_key,
            "source_url": latest.source_url,
            "freshness": quote_freshness,
            "age_hours": round(quote_age_hours, 2) if quote_age_hours is not None else None,
        },
        "fundamentals": {
            "availability": "available" if fundamentals_observation else "unavailable",
            "as_of": fundamentals_as_of,
            "observed_at": fundamentals_observation.observed_at
            if fundamentals_observation
            else None,
            "freshness": fundamentals_freshness,
            "metrics": fundamentals_observation.fundamentals_json
            if fundamentals_observation
            else {},
            "metric_units": {
                key: FUNDAMENTAL_UNITS[key]
                for key in (fundamentals_observation.fundamentals_json or {})
                if key in FUNDAMENTAL_UNITS
            }
            if fundamentals_observation
            else {},
            "source_key": fundamentals_observation.source_key if fundamentals_observation else None,
            "source_url": fundamentals_observation.source_url if fundamentals_observation else None,
            "retrieved_at": fundamentals_observation.retrieved_at
            if fundamentals_observation
            else None,
        },
        "corporate_events": corporate_events,
        "corporate_events_observed_at": (
            event_observation.observed_at if event_observation else None
        ),
        "corporate_events_source_key": event_observation.source_key if event_observation else None,
        "portfolio_positions": positions,
        "portfolio_coverage": {
            "matched_scheme_count": len({row["scheme_code"] for row in positions}),
            "requested_scheme_count": len(scheme_codes or []),
            "disclosure_based": True,
        },
        "observation_history": [
            {
                "observed_at": row.observed_at,
                "last_price": row.last_price,
                "change_pct": row.change_pct,
                "source_key": row.source_key,
                "source_url": row.source_url,
                "retrieved_at": row.retrieved_at,
                "content_hash": row.content_hash,
            }
            for row in reversed(observations)
        ],
        "observation_history_limit": history_limit,
        "observation_history_type": history_type,
        "observation_history_order": "ascending",

        "freshness_policy": {
            "quote_fresh_hours": 24,
            "fundamentals_fresh_days": 180,
            "reference_date": freshness_reference_date,
            "note": (
                "Historical requests evaluate freshness relative to as_of; current requests "
                "use the current date. These are application heuristics, not exchange or "
                "regulatory standards."
            ),
        },
        "limitations": [
            (
                "Market observations and fundamentals are provider-submitted snapshots, "
                "not guaranteed live exchange data."
            ),
            "Fundamentals are shown only with their declared as-of date and source attribution.",
            "Portfolio positions come from dated AMC disclosures and may be incomplete or stale.",
            "Missing metrics are unavailable; they are never estimated from price or NAV.",
        ],
    }


def securities_for_funds(
    session: Session,
    scheme_codes: list[int],
    *,
    as_of: date | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    """Build a bounded stock-level view from the latest available disclosure per scheme."""
    if not scheme_codes or len(scheme_codes) > 20 or len(set(scheme_codes)) != len(scheme_codes):
        raise ValueError("Provide between one and twenty unique scheme codes.")
    snapshot_statement = (
        select(PortfolioSnapshot)
        .where(
            PortfolioSnapshot.scheme_code.in_(scheme_codes),
            PortfolioSnapshot.effective_date <= (as_of or date.max),
            PortfolioSnapshot.status.in_(["complete", "partial"]),
        )
        .order_by(
            PortfolioSnapshot.scheme_code,
            PortfolioSnapshot.effective_date.desc(),
            PortfolioSnapshot.snapshot_id.desc(),
        )
    )
    snapshots = session.scalars(snapshot_statement).all()
    latest_by_scheme: dict[int, PortfolioSnapshot] = {}
    for snapshot in snapshots:
        latest_by_scheme.setdefault(snapshot.scheme_code, snapshot)
    if not latest_by_scheme:
        return {
            "scheme_codes": scheme_codes,
            "securities": [],
            "coverage": {"schemes_with_disclosures": 0, "requested_schemes": len(scheme_codes)},
            "warning": "No eligible AMC portfolio disclosures are stored for these schemes.",
        }
    holdings = session.scalars(
        select(PortfolioHolding)
        .where(
            PortfolioHolding.snapshot_id.in_(
                [snapshot.snapshot_id for snapshot in latest_by_scheme.values()]
            ),
            PortfolioHolding.asset_class == "equity",
        )
        .order_by(PortfolioHolding.weight_pct.desc().nullslast())
    ).all()
    keys = list(dict.fromkeys(row.security_key for row in holdings))[: min(max(limit, 1), 100)]
    securities = [
        security_profile(session, key, as_of=as_of, scheme_codes=scheme_codes) for key in keys
    ]
    return {
        "scheme_codes": scheme_codes,
        "as_of": as_of,
        "securities": securities,
        "coverage": {
            "schemes_with_disclosures": len(latest_by_scheme),
            "requested_schemes": len(scheme_codes),
            "unique_equity_securities": len({row.security_key for row in holdings}),
            "returned_securities": len(securities),
        },
        "warning": (
            "Stock observations are joined by normalized security_key. "
            "Unmatched securities remain without market data."
        ),
    }
