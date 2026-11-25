"""Security-level intelligence built from dated provider observations and AMC disclosures."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.models.research import PortfolioHolding, PortfolioSnapshot
from mutual_fund_agent_analysis.models.security import SecurityMarketObservation


def security_profile(
    session: Session,
    security_key: str,
    *,
    as_of: date | None = None,
    scheme_codes: list[int] | None = None,
) -> dict[str, Any]:
    """Return a source-attributed security profile without manufacturing missing fundamentals."""
    key = security_key.strip().upper()
    if len(key) < 2:
        raise ValueError("security_key must contain at least two characters.")

    statement = select(SecurityMarketObservation).where(
        or_(
            SecurityMarketObservation.security_key == key,
            SecurityMarketObservation.isin == key,
        )
    )
    if as_of:
        cutoff = datetime.combine(as_of, time.max, tzinfo=UTC)
        statement = statement.where(SecurityMarketObservation.observed_at <= cutoff)
    observations = session.scalars(
        statement.order_by(
            SecurityMarketObservation.observed_at.desc(),
            SecurityMarketObservation.observation_id.desc(),
        ).limit(20)
    ).all()
    latest = observations[0] if observations else None

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

    now = datetime.now(UTC)
    quote_age_hours = (
        max(0.0, (now - latest.observed_at.astimezone(UTC)).total_seconds() / 3600)
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
    fundamentals_observation = next(
        (row for row in observations if row.fundamentals_json), None
    )
    event_observation = next(
        (row for row in observations if row.corporate_events_json), None
    )
    fundamentals_as_of = (
        fundamentals_observation.fundamentals_as_of if fundamentals_observation else None
    )
    fundamentals_age_days = (date.today() - fundamentals_as_of).days if fundamentals_as_of else None
    fundamentals_freshness = (
        "unavailable"
        if fundamentals_observation is None
        else "fresh"
        if fundamentals_age_days is not None and 0 <= fundamentals_age_days <= 180
        else "stale"
    )

    return {
        "security_key": key,
        "availability": "available" if latest else "no_market_observation",
        "identity": {
            "security_name": latest.security_name if latest else (
                positions[0]["security_name"] if positions else key
            ),
            "isin": latest.isin if latest else None,
            "symbol": latest.symbol if latest else None,
            "exchange": latest.exchange if latest else None,
        },
        "market": None if latest is None else {
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
            "freshness": fundamentals_freshness,
            "metrics": fundamentals_observation.fundamentals_json
            if fundamentals_observation
            else {},
            "source_key": fundamentals_observation.source_key
            if fundamentals_observation
            else None,
            "source_url": fundamentals_observation.source_url
            if fundamentals_observation
            else None,
        },
        "corporate_events": event_observation.corporate_events_json
        if event_observation
        else [],
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
                "content_hash": row.content_hash,
            }
            for row in observations
        ],
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
    snapshot_statement = select(PortfolioSnapshot).where(
        PortfolioSnapshot.scheme_code.in_(scheme_codes),
        PortfolioSnapshot.effective_date <= (as_of or date.max),
        PortfolioSnapshot.status.in_(["complete", "partial"]),
    ).order_by(
        PortfolioSnapshot.scheme_code,
        PortfolioSnapshot.effective_date.desc(),
        PortfolioSnapshot.snapshot_id.desc(),
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
        select(PortfolioHolding).where(
            PortfolioHolding.snapshot_id.in_(
                [snapshot.snapshot_id for snapshot in latest_by_scheme.values()]
            ),
            PortfolioHolding.asset_class == "equity",
        ).order_by(PortfolioHolding.weight_pct.desc().nullslast())
    ).all()
    keys = list(dict.fromkeys(row.security_key for row in holdings))[: min(max(limit, 1), 100)]
    securities = [
        security_profile(session, key, as_of=as_of, scheme_codes=scheme_codes)
        for key in keys
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
