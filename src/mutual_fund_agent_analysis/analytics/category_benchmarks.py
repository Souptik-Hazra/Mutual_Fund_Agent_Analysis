"""Effective-dated benchmark resolution for exact scheme cohorts."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.models.category_benchmark import CategoryBenchmarkMapping
from mutual_fund_agent_analysis.models.intelligence import DataSource
from mutual_fund_agent_analysis.models.scheme import MutualFundScheme


def resolve_category_benchmark(
    session: Session, scheme: MutualFundScheme, as_of: date | None = None
) -> CategoryBenchmarkMapping | None:
    """Resolve exactly one active mapping; overlapping mappings fail closed."""
    effective_date = as_of or date.today()
    query = (
        select(CategoryBenchmarkMapping)
        .where(
            CategoryBenchmarkMapping.active.is_(True),
            CategoryBenchmarkMapping.scheme_category == scheme.scheme_category,
            CategoryBenchmarkMapping.scheme_type.is_(None)
            if scheme.scheme_type is None
            else CategoryBenchmarkMapping.scheme_type == scheme.scheme_type,
            CategoryBenchmarkMapping.plan_type.is_(None)
            if scheme.plan_type is None
            else CategoryBenchmarkMapping.plan_type == scheme.plan_type,
            CategoryBenchmarkMapping.option_type.is_(None)
            if scheme.option_type is None
            else CategoryBenchmarkMapping.option_type == scheme.option_type,
            CategoryBenchmarkMapping.effective_from <= effective_date,
            (CategoryBenchmarkMapping.effective_to.is_(None))
            | (CategoryBenchmarkMapping.effective_to >= effective_date),
        )
        .order_by(
            CategoryBenchmarkMapping.effective_from.desc(),
            CategoryBenchmarkMapping.mapping_id.desc(),
        )
    )
    rows = session.scalars(query.limit(2)).all()
    if len(rows) > 1:
        raise ValueError("Multiple active benchmark mappings overlap for this scheme cohort.")
    if not rows:
        return None
    mapping = rows[0]
    source = session.get(DataSource, mapping.source_key) if mapping.source_key else None
    if source is None or not source.enabled or not source.is_official or source.source_type != "official":
        return None
    return mapping
