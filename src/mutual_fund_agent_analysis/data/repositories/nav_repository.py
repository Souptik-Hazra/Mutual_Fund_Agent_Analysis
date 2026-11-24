"""Idempotent PostgreSQL upserts for schemes, NAVs, and reconciliation results."""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.data.providers.contracts import NavResponse
from mutual_fund_agent_analysis.data.services.nav_reconciliation import (
    NAV_RECONCILIATION_TOLERANCE,
    build_reconciliation,
)
from mutual_fund_agent_analysis.models import (
    MutualFundScheme,
    NavObservation,
    NavReconciliation,
    ProviderSyncRun,
)


def _reconcile_dates(session: Session, scheme_code: int, nav_dates: set[date]) -> None:
    if not nav_dates:
        return
    observations = session.scalars(
        select(NavObservation).where(
            NavObservation.scheme_code == scheme_code,
            NavObservation.nav_date.in_(nav_dates),
        )
    ).all()
    grouped: dict = {}
    for observation in observations:
        grouped.setdefault(observation.nav_date, {})[observation.source] = Decimal(
            observation.nav
        )

    for nav_date, values in grouped.items():
        result = build_reconciliation(values, NAV_RECONCILIATION_TOLERANCE)
        statement = insert(NavReconciliation).values(
            scheme_code=scheme_code,
            nav_date=nav_date,
            source_values=result["source_values"],
            canonical_nav=result["canonical_nav"],
            canonical_source=result["canonical_source"],
            absolute_difference=result["absolute_difference"],
            relative_difference=result["relative_difference"],
            status=result["status"],
            tolerance=result["tolerance"],
            evaluated_at=datetime.now(UTC),
        )
        statement = statement.on_conflict_do_update(
            index_elements=[NavReconciliation.scheme_code, NavReconciliation.nav_date],
            set_={
                "source_values": statement.excluded.source_values,
                "canonical_nav": statement.excluded.canonical_nav,
                "canonical_source": statement.excluded.canonical_source,
                "absolute_difference": statement.excluded.absolute_difference,
                "relative_difference": statement.excluded.relative_difference,
                "status": statement.excluded.status,
                "tolerance": statement.excluded.tolerance,
                "evaluated_at": statement.excluded.evaluated_at,
            },
        )
        session.execute(statement)


def upsert_nav_response(
    session: Session,
    response: NavResponse,
    source: str = "mfapi",
) -> int:
    """Upsert source-specific observations and refresh their canonical decisions."""
    normalized_source = source.strip().lower()
    if not normalized_source or len(normalized_source) > 40:
        raise ValueError("source must contain between 1 and 40 characters.")
    metadata = response.meta
    scheme_values = {
        "scheme_code": metadata.scheme_code,
        "scheme_name": metadata.scheme_name,
        "fund_house": metadata.fund_house,
        "scheme_type": metadata.scheme_type,
        "scheme_category": metadata.scheme_category,
        "isin_growth": metadata.isin_growth,
        "isin_div_reinvestment": metadata.isin_div_reinvestment,
        "source": normalized_source,
        "source_updated_at": datetime.now(UTC),
    }
    scheme_statement = insert(MutualFundScheme).values(**scheme_values)
    excluded = scheme_statement.excluded
    scheme_statement = scheme_statement.on_conflict_do_update(
        index_elements=[MutualFundScheme.scheme_code],
        set_={
            "scheme_name": excluded.scheme_name,
            "fund_house": func.coalesce(excluded.fund_house, MutualFundScheme.fund_house),
            "scheme_type": func.coalesce(excluded.scheme_type, MutualFundScheme.scheme_type),
            "scheme_category": func.coalesce(
                excluded.scheme_category, MutualFundScheme.scheme_category
            ),
            "isin_growth": func.coalesce(excluded.isin_growth, MutualFundScheme.isin_growth),
            "isin_div_reinvestment": func.coalesce(
                excluded.isin_div_reinvestment, MutualFundScheme.isin_div_reinvestment
            ),
            "source": excluded.source,
            "source_updated_at": excluded.source_updated_at,
        },
    )
    session.execute(scheme_statement)

    fetched_at = datetime.now(UTC)
    nav_values = [
        {
            "scheme_code": metadata.scheme_code,
            "nav_date": point.date,
            "nav": point.nav,
            "source": normalized_source,
            "fetched_at": fetched_at,
        }
        for point in response.data
    ]
    processed = 0
    affected_dates = {value["nav_date"] for value in nav_values}
    for offset in range(0, len(nav_values), 1000):
        batch = nav_values[offset : offset + 1000]
        nav_statement = insert(NavObservation).values(batch)
        nav_statement = nav_statement.on_conflict_do_update(
            index_elements=[
                NavObservation.scheme_code,
                NavObservation.nav_date,
                NavObservation.source,
            ],
            set_={
                "nav": nav_statement.excluded.nav,
                "fetched_at": nav_statement.excluded.fetched_at,
            },
        )
        session.execute(nav_statement)
        processed += len(batch)

    raw_payload = response.raw_payload
    if raw_payload is None:
        raw_payload = (
            response.model_dump(mode="json")
            if hasattr(response, "model_dump")
            else {
                "provider": normalized_source,
                "scheme_code": metadata.scheme_code,
                "observations": [
                    {"date": point.date.isoformat(), "nav": str(point.nav)}
                    for point in response.data
                ],
            }
        )
    session.add(
        ProviderSyncRun(
            scheme_code=metadata.scheme_code,
            source=normalized_source,
            fetched_at=fetched_at,
            observation_count=processed,
            response_payload=raw_payload,
        )
    )
    _reconcile_dates(session, metadata.scheme_code, affected_dates)
    return processed
