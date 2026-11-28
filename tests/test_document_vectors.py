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


def test_document_chunk_point_ids_are_stable_and_document_scoped():
    first = document_vectors.document_chunk_point_id(100, 0, "a" * 64)
    retry = document_vectors.document_chunk_point_id(100, 0, "a" * 64)
    changed_chunk = document_vectors.document_chunk_point_id(100, 0, "b" * 64)
    other_document = document_vectors.document_chunk_point_id(101, 0, "a" * 64)

    assert first == retry
    assert first != changed_chunk
    assert first != other_document


def test_indexing_replaces_previous_chunks_and_removes_stale_trailing_chunks(monkeypatch):
    from pydantic import SecretStr

    class FakeClient:
        def __init__(self):
            self.points = {}
            self.deleted_document_ids = []
            self.closed = False

        def collection_exists(self, _collection):
            return bool(self.points)

        def delete(self, collection_name, points_selector, wait):
            assert collection_name == "test_vectors"
            assert wait is True
            self.deleted_document_ids.append(100)
            filters = points_selector.filter
            keep_conditions = getattr(filters, "must_not", [])
            keep_version = keep_conditions[0].match.value if keep_conditions else None
            self.points = {
                point_id: document
                for point_id, document in self.points.items()
                if keep_version is not None
                and document.metadata.get("index_version") == keep_version
            }

        def close(self):
            self.closed = True

    client = FakeClient()

    class FakeStore:
        @classmethod
        def from_existing_collection(cls, **_kwargs):
            return cls()

        def add_documents(self, documents, ids):
            for document, point_id in zip(documents, ids, strict=True):
                client.points[point_id] = document

        @classmethod
        def from_documents(cls, documents, _embeddings, **kwargs):
            for document, point_id in zip(documents, kwargs["ids"], strict=True):
                client.points[point_id] = document

    class FakeEmbeddings:
        def __init__(self, **_kwargs):
            pass

    settings = type(
        "Settings",
        (),
        {
            "qdrant_url": "http://qdrant:6333",
            "qdrant_api_key": None,
            "qdrant_collection": "test_vectors",
            "gemini_api_key": SecretStr("test-key"),
            "document_embedding_model": "test-embedding",
        },
    )()
    monkeypatch.setattr(document_vectors, "get_settings", lambda: settings)
    monkeypatch.setattr(document_vectors, "_configured_client", lambda _settings: client)

    import sys
    from types import ModuleType

    import langchain_google_genai

    fake_qdrant_module = ModuleType("langchain_qdrant")
    fake_qdrant_module.QdrantVectorStore = FakeStore
    fake_client_module = ModuleType("qdrant_client")
    fake_client_models = ModuleType("qdrant_client.models")

    class FakeQdrantClient:
        def __init__(self, **_kwargs):
            pass

    class FakeFilter:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeCondition:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeMatchValue:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeFilterSelector:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    fake_client_module.QdrantClient = FakeQdrantClient
    fake_client_models.FieldCondition = FakeCondition
    fake_client_models.Filter = FakeFilter
    fake_client_models.FilterSelector = FakeFilterSelector
    fake_client_models.MatchValue = FakeMatchValue
    fake_client_module.models = fake_client_models
    monkeypatch.setitem(sys.modules, "langchain_qdrant", fake_qdrant_module)
    monkeypatch.setitem(sys.modules, "qdrant_client", fake_client_module)
    monkeypatch.setitem(sys.modules, "qdrant_client.models", fake_client_models)
    monkeypatch.setattr(langchain_google_genai, "GoogleGenerativeAIEmbeddings", FakeEmbeddings)

    original = [
        {"text": "one", "chunk_index": 0, "content_hash": "a" * 64},
        {"text": "two", "chunk_index": 1, "content_hash": "b" * 64},
        {"text": "three", "chunk_index": 2, "content_hash": "c" * 64},
    ]
    assert document_vectors.index_chunks(100, "Fixture", original) is True
    assert len(client.points) == 3

    assert document_vectors.index_chunks(100, "Fixture", list(original)) is True
    assert len(client.points) == 3

    shorter = [{"text": "replacement", "chunk_index": 0, "content_hash": "d" * 64}]
    assert document_vectors.index_chunks(100, "Fixture", shorter) is True
    assert len(client.points) == 1
    assert next(iter(client.points.values())).page_content == "replacement"
    assert client.deleted_document_ids == [100, 100, 100]
    assert client.closed is True


def test_indexing_returns_false_when_vector_store_write_fails(monkeypatch):
    from pydantic import SecretStr

    class FakeClient:
        def __init__(self):
            self.delete_calls = 0

        def collection_exists(self, _collection):
            return True

        def delete(self, **_kwargs):
            self.delete_calls += 1

        def close(self):
            return None

    client = FakeClient()

    class FakeEmbeddings:
        def __init__(self, **_kwargs):
            pass

    class FailingStore:
        @classmethod
        def from_existing_collection(cls, **_kwargs):
            raise RuntimeError("simulated Qdrant outage")

    settings = type(
        "Settings",
        (),
        {
            "qdrant_url": "http://qdrant:6333",
            "qdrant_api_key": None,
            "qdrant_collection": "test_vectors",
            "gemini_api_key": SecretStr("test-key"),
            "document_embedding_model": "test-embedding",
        },
    )()
    monkeypatch.setattr(document_vectors, "get_settings", lambda: settings)
    monkeypatch.setattr(document_vectors, "_configured_client", lambda _settings: client)

    import sys
    from types import ModuleType

    import langchain_google_genai

    fake_qdrant_module = ModuleType("langchain_qdrant")
    fake_qdrant_module.QdrantVectorStore = FailingStore
    fake_client_module = ModuleType("qdrant_client")
    fake_client_models = ModuleType("qdrant_client.models")

    class FakeQdrantClient:
        def __init__(self, **_kwargs):
            pass

    class FakeFilter:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeCondition:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeMatchValue:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeFilterSelector:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    fake_client_module.QdrantClient = FakeQdrantClient
    fake_client_models.FieldCondition = FakeCondition
    fake_client_models.Filter = FakeFilter
    fake_client_models.FilterSelector = FakeFilterSelector
    fake_client_models.MatchValue = FakeMatchValue
    fake_client_module.models = fake_client_models
    monkeypatch.setitem(sys.modules, "langchain_qdrant", fake_qdrant_module)
    monkeypatch.setitem(sys.modules, "qdrant_client", fake_client_module)
    monkeypatch.setitem(sys.modules, "qdrant_client.models", fake_client_models)
    monkeypatch.setattr(langchain_google_genai, "GoogleGenerativeAIEmbeddings", FakeEmbeddings)

    assert (
        document_vectors.index_chunks(
            100,
            "Fixture",
            [{"text": "lexical data remains", "chunk_index": 0, "content_hash": "a" * 64}],
        )
        is False
    )
    assert client.delete_calls == 0


def test_search_chunks_falls_back_when_embedding_provider_is_unavailable(monkeypatch):
    from pydantic import SecretStr

    settings = type(
        "Settings",
        (),
        {
            "qdrant_url": "http://qdrant:6333",
            "qdrant_api_key": None,
            "qdrant_collection": "test_vectors",
            "gemini_api_key": SecretStr("test-key"),
            "document_embedding_model": "test-embedding",
        },
    )()
    monkeypatch.setattr(document_vectors, "get_settings", lambda: settings)

    class FailingEmbeddings:
        def __init__(self, **_kwargs):
            raise RuntimeError("provider unavailable")

    import langchain_google_genai

    monkeypatch.setattr(langchain_google_genai, "GoogleGenerativeAIEmbeddings", FailingEmbeddings)

    assert document_vectors.search_chunks("fund expenses", 5) is None


def test_semantic_search_applies_scheme_metadata_filter(monkeypatch):
    import sys
    from types import ModuleType, SimpleNamespace

    from pydantic import SecretStr

    settings = type(
        "Settings",
        (),
        {
            "qdrant_url": "http://qdrant:6333",
            "qdrant_api_key": None,
            "qdrant_collection": "test_vectors",
            "gemini_api_key": SecretStr("test-key"),
            "document_embedding_model": "test-embedding",
        },
    )()
    monkeypatch.setattr(document_vectors, "get_settings", lambda: settings)

    class FakeEmbeddings:
        def __init__(self, **_kwargs):
            pass

    class FakeFilter:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeCondition:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeMatchValue:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FakeStore:
        @classmethod
        def from_existing_collection(cls, **_kwargs):
            return cls()

        def similarity_search_with_score(self, _query, **kwargs):
            condition = kwargs["filter"].must[0]
            assert condition.key == "metadata.scheme_code"
            assert condition.match.value == 125497
            return [
                (
                    SimpleNamespace(
                        metadata={
                            "document_id": 10,
                            "title": "Factsheet",
                            "page_number": 2,
                            "chunk_index": 1,
                            "scheme_code": 125497,
                            "source_key": "amfi",
                            "canonical_url": "https://amfi.example/factsheet",
                            "content_hash": "a" * 64,
                        },
                        page_content="Expense ratio details",
                    ),
                    0.91,
                )
            ]

    import langchain_google_genai

    fake_google = langchain_google_genai
    monkeypatch.setattr(fake_google, "GoogleGenerativeAIEmbeddings", FakeEmbeddings)
    fake_qdrant = ModuleType("langchain_qdrant")
    fake_qdrant.QdrantVectorStore = FakeStore
    fake_models = ModuleType("qdrant_client.models")
    fake_models.FieldCondition = FakeCondition
    fake_models.Filter = FakeFilter
    fake_models.MatchValue = FakeMatchValue
    fake_client = ModuleType("qdrant_client")
    fake_client.models = fake_models
    monkeypatch.setitem(sys.modules, "langchain_qdrant", fake_qdrant)
    monkeypatch.setitem(sys.modules, "qdrant_client", fake_client)
    monkeypatch.setitem(sys.modules, "qdrant_client.models", fake_models)

    results = document_vectors.search_chunks("expense ratio", 5, scheme_code=125497)
    assert len(results) == 1
    assert results[0]["document_id"] == 10
    assert results[0]["text"] == "Expense ratio details"


def test_document_search_uses_lexical_fallback_when_semantic_search_is_unavailable(monkeypatch):
    from types import SimpleNamespace

    from mutual_fund_agent_analysis.data.services import research_intelligence

    chunk = SimpleNamespace(
        chunk_text="The scheme expense ratio is documented in the factsheet.",
        document_id=10,
        page_number=2,
        chunk_index=0,
        chunk_id=100,
    )
    document = SimpleNamespace(
        document_id=10,
        title="Scheme factsheet",
        source_key="amfi",
        content_hash="a" * 64,
        effective_date=None,
        published_at=None,
    )

    class Rows:
        def all(self):
            return [(chunk, document)]

    class Session:
        def execute(self, _statement):
            return Rows()

    monkeypatch.setattr(document_vectors, "search_chunks", lambda *_args, **_kwargs: None)
    result = research_intelligence.search_documents(Session(), "expense ratio", None, 5)
    assert result["retrieval_mode"] == "lexical_fallback"
    assert result["results"][0]["document_id"] == 10
