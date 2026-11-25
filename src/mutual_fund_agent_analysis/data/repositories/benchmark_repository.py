"""Idempotent persistence for benchmark TRI/NTR observations."""

from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.data.providers.niftyindices import BenchmarkResponse
from mutual_fund_agent_analysis.data.services.intelligence import (
    add_entity_alias,
    add_entity_identifier,
    create_entity,
)
from mutual_fund_agent_analysis.models.intelligence import DataSource
from mutual_fund_agent_analysis.models.benchmark import (
    BenchmarkIndex,
    BenchmarkObservation,
    BenchmarkSyncRun,
)


def upsert_benchmark_response(
    session: Session,
    response: BenchmarkResponse,
    source: str = "niftyindices",
) -> int:
    """Upsert benchmark metadata and observations while preserving source identity."""
    normalized_source = source.strip().lower()
    if not normalized_source or len(normalized_source) > 40:
        raise ValueError("source must contain between 1 and 40 characters.")

    master = insert(BenchmarkIndex).values(
        benchmark_code=response.benchmark_code,
        benchmark_name=response.benchmark_name,
        provider=normalized_source,
        updated_at=datetime.now(UTC),
    )
    master = master.on_conflict_do_update(
        index_elements=[BenchmarkIndex.benchmark_code],
        set_={
            "benchmark_name": master.excluded.benchmark_name,
            "provider": master.excluded.provider,
            "updated_at": master.excluded.updated_at,
        },
    )
    session.execute(master)

    source_key = (
        normalized_source if session.get(DataSource, normalized_source) is not None else None
    )
    entity = create_entity(
        session,
        "benchmark",
        f"{response.benchmark_name} [{response.benchmark_code}]",
    )
    add_entity_alias(
        session, entity.entity_id, response.benchmark_name,
        alias_type="publisher_name", source_key=source_key, is_primary=True,
    )
    add_entity_identifier(
        session, entity.entity_id, "BENCHMARK_CODE", response.benchmark_code,
        source_key=source_key, is_primary=True,
    )

    fetched_at = datetime.now(UTC)
    rows = [
        {
            "benchmark_code": response.benchmark_code,
            "observation_date": point.date,
            "source": normalized_source,
            "tri_value": point.tri,
            "ntr_value": point.ntr,
            "fetched_at": fetched_at,
            "raw_metadata": {"benchmark_name": response.benchmark_name},
        }
        for point in response.data
    ]
    processed = 0
    for offset in range(0, len(rows), 1000):
        batch = rows[offset : offset + 1000]
        statement = insert(BenchmarkObservation).values(batch)
        statement = statement.on_conflict_do_update(
            index_elements=[
                BenchmarkObservation.benchmark_code,
                BenchmarkObservation.observation_date,
                BenchmarkObservation.source,
            ],
            set_={
                "tri_value": statement.excluded.tri_value,
                "ntr_value": statement.excluded.ntr_value,
                "fetched_at": statement.excluded.fetched_at,
                "raw_metadata": statement.excluded.raw_metadata,
            },
        )
        session.execute(statement)
        processed += len(batch)

    session.add(
        BenchmarkSyncRun(
            benchmark_code=response.benchmark_code,
            source=normalized_source,
            fetched_at=fetched_at,
            observation_count=processed,
            response_payload=response.raw_payload or {
                "provider": normalized_source,
                "benchmark_code": response.benchmark_code,
                "benchmark_name": response.benchmark_name,
                "observations": [
                    {
                        "date": point.date.isoformat(),
                        "tri": str(point.tri),
                        "ntr": str(point.ntr) if point.ntr is not None else None,
                    }
                    for point in response.data
                ],
            },
        )
    )
    return processed
