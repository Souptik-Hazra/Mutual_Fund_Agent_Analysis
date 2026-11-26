"""Historical event version selection tests."""

from datetime import UTC, datetime
from types import SimpleNamespace

from mutual_fund_agent_analysis.api.routes.research import _event_state_as_of


class StubSession:
    def __init__(self, revision=None, evidence=None):
        self.revision = revision
        self.evidence = evidence
        self.scalar_calls = 0

    def scalar(self, _statement):
        self.scalar_calls += 1
        return self.revision

    def get(self, _model, _identity):
        return self.evidence


def test_historical_event_uses_next_revision_snapshot_before_source_update():
    previous_state = {
        "title": "Original announcement",
        "status": "reported",
        "event_date": "2026-01-05",
        "published_at": "2026-01-04T08:00:00+00:00",
        "source_key": "exchange",
        "evidence": {"verification_status": "unverified"},
    }
    revision = SimpleNamespace(snapshot=previous_state)
    event = SimpleNamespace(
        event_id=7,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    session = StubSession(revision=revision)

    result = _event_state_as_of(
        session, event, datetime(2026, 1, 6, tzinfo=UTC)
    )

    assert result == previous_state
    assert session.scalar_calls == 1


def test_event_is_absent_before_its_creation_time():
    event = SimpleNamespace(
        event_id=8,
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    session = StubSession()

    result = _event_state_as_of(
        session, event, datetime(2026, 1, 1, tzinfo=UTC)
    )

    assert result is None
    assert session.scalar_calls == 0


def test_current_event_state_is_used_after_latest_revision():
    event = SimpleNamespace(
        event_id=9,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_key="exchange",
        external_id="evt-9",
        evidence_id=None,
        related_entity_id=12,
        title="Corrected announcement",
        summary="Updated details",
        event_type="results",
        status="confirmed",
        event_date=datetime(2026, 1, 7).date(),
        published_at=datetime(2026, 1, 6, tzinfo=UTC),
        canonical_url="https://example.com/event",
        confidence=None,
        metadata_json={"revision": 2},
    )
    session = StubSession(revision=None)

    result = _event_state_as_of(
        session, event, datetime(2026, 2, 1, tzinfo=UTC)
    )

    assert result["title"] == "Corrected announcement"
    assert result["status"] == "confirmed"
    assert result["event_date"] == "2026-01-07"
