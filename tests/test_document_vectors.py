"""Unit checks for deterministic vector point identity."""

from mutual_fund_agent_analysis.data.services.document_vectors import document_chunk_point_id


def test_document_chunk_point_ids_are_stable_and_scoped_to_content():
    first = document_chunk_point_id(10, 0, "a" * 64)
    retry = document_chunk_point_id(10, 0, "a" * 64)
    changed = document_chunk_point_id(10, 0, "b" * 64)
    other_document = document_chunk_point_id(11, 0, "a" * 64)

    assert first == retry
    assert len({first, changed, other_document}) == 3


def test_document_chunk_point_id_rejects_invalid_identity():
    import pytest

    with pytest.raises(ValueError):
        document_chunk_point_id(0, 0, "a" * 64)
    with pytest.raises(ValueError):
        document_chunk_point_id(10, -1, "a" * 64)
