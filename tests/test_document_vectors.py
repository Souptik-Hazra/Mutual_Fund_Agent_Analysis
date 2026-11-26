"""Tests for optional Qdrant document deletion semantics."""

import pytest

from mutual_fund_agent_analysis.data.services import document_vectors


def test_document_deletion_succeeds_when_semantic_index_is_not_configured(monkeypatch):
    monkeypatch.setattr(
        document_vectors,
        "get_settings",
        lambda: type("Settings", (), {"qdrant_url": None})(),
    )
    assert document_vectors.delete_document_chunks(12) is True


def test_document_deletion_rejects_invalid_document_ids():
    with pytest.raises(ValueError):
        document_vectors.delete_document_chunks(0)
