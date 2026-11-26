"""Optional Qdrant semantic retrieval with idempotent document lifecycle operations."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from mutual_fund_agent_analysis.core.config import get_settings

logger = logging.getLogger(__name__)
_POINT_NAMESPACE = uuid.UUID("4f0d43e7-cc25-4a92-9bcb-fd3e3a7a21f4")


def document_chunk_point_id(document_id: int, chunk_index: int, content_hash: str) -> str:
    """Return a stable Qdrant point ID for one immutable document chunk."""
    if document_id <= 0 or chunk_index < 0 or not content_hash:
        raise ValueError("Document and chunk identity must be valid.")
    return str(uuid.uuid5(_POINT_NAMESPACE, f"{document_id}:{chunk_index}:{content_hash}"))


def _configured_client(settings: Any) -> Any:
    from qdrant_client import QdrantClient

    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
        timeout=10,
    )


def _delete_document_points(client: Any, collection_name: str, document_id: int) -> None:
    from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

    if not client.collection_exists(collection_name):
        return
    client.delete(
        collection_name=collection_name,
        points_selector=FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(
                        key="metadata.document_id",
                        match=MatchValue(value=document_id),
                    )
                ]
            )
        ),
        wait=True,
    )


def delete_document_chunks(document_id: int) -> bool:
    """Delete every semantic point for a document; lexical records remain authoritative."""
    if document_id <= 0:
        raise ValueError("document_id must be positive.")
    settings = get_settings()
    if not settings.qdrant_url:
        return False
    client = None
    try:
        client = _configured_client(settings)
        _delete_document_points(client, settings.qdrant_collection, document_id)
        return True
    except Exception:
        logger.exception("Qdrant document deletion failed for document_id=%s.", document_id)
        return False
    finally:
        if client is not None:
            client.close()


def index_chunks(document_id: int, title: str, chunks: list[dict[str, Any]]) -> bool:
    """Replace a document's semantic chunks atomically at the document-filter level.

    Stable point IDs make retries idempotent. Old points are removed before the new
    chunk set is written, so a shorter reindex cannot leave stale trailing chunks.
    PostgreSQL lexical chunks remain available if Qdrant or embeddings are unavailable.
    """
    settings = get_settings()
    if not settings.qdrant_url or not settings.gemini_api_key:
        return False
    if document_id <= 0:
        raise ValueError("document_id must be positive.")
    client = None
    try:
        from langchain_core.documents import Document
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        from langchain_qdrant import QdrantVectorStore

        client = _configured_client(settings)
        embeddings = GoogleGenerativeAIEmbeddings(
            model=settings.document_embedding_model,
            google_api_key=settings.gemini_api_key.get_secret_value(),
        )
        documents = [
            Document(
                page_content=row["text"],
                metadata={
                    "document_id": document_id,
                    "title": title,
                    "chunk_index": row["chunk_index"],
                    "page_number": row.get("page_number"),
                    "scheme_code": row.get("scheme_code"),
                    "content_hash": row["content_hash"],
                    "source_key": row.get("source_key"),
                    "canonical_url": row.get("canonical_url"),
                },
            )
            for row in chunks
        ]
        point_ids = [
            document_chunk_point_id(document_id, row["chunk_index"], row["content_hash"])
            for row in chunks
        ]
        _delete_document_points(client, settings.qdrant_collection, document_id)
        if not documents:
            return True

        if client.collection_exists(settings.qdrant_collection):
            store = QdrantVectorStore.from_existing_collection(
                embedding=embeddings,
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key.get_secret_value()
                if settings.qdrant_api_key
                else None,
                collection_name=settings.qdrant_collection,
            )
            store.add_documents(documents, ids=point_ids)
        else:
            QdrantVectorStore.from_documents(
                documents,
                embeddings,
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key.get_secret_value()
                if settings.qdrant_api_key
                else None,
                collection_name=settings.qdrant_collection,
                ids=point_ids,
            )
        return True
    except Exception:
        logger.exception(
            "Qdrant document indexing failed for document_id=%s; lexical retrieval remains available.",
            document_id,
        )
        return False
    finally:
        if client is not None:
            client.close()


def search_chunks(
    query: str, limit: int, scheme_code: int | None = None
) -> list[dict[str, Any]] | None:
    """Return semantic matches, or None when semantic retrieval is not configured."""
    settings = get_settings()
    if not settings.qdrant_url or not settings.gemini_api_key:
        return None
    try:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        from langchain_qdrant import QdrantVectorStore

        embeddings = GoogleGenerativeAIEmbeddings(
            model=settings.document_embedding_model,
            google_api_key=settings.gemini_api_key.get_secret_value(),
        )
        store = QdrantVectorStore.from_existing_collection(
            embedding=embeddings,
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
            collection_name=settings.qdrant_collection,
        )
        search_kwargs: dict[str, Any] = {}
        if scheme_code is not None:
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            search_kwargs["filter"] = Filter(
                must=[
                    FieldCondition(
                        key="metadata.scheme_code",
                        match=MatchValue(value=scheme_code),
                    )
                ]
            )
        matches = store.similarity_search_with_score(
            query,
            k=min(max(limit, 1), 100),
            **search_kwargs,
        )
        results = []
        for document, score in matches:
            metadata = document.metadata
            if scheme_code is not None and metadata.get("scheme_code") != scheme_code:
                continue
            results.append(
                {
                    "score": float(score),
                    "document_id": metadata.get("document_id"),
                    "title": metadata.get("title"),
                    "page_number": metadata.get("page_number"),
                    "chunk_index": metadata.get("chunk_index"),
                    "source_key": metadata.get("source_key"),
                    "canonical_url": metadata.get("canonical_url"),
                    "text": document.page_content,
                    "citation": {
                        "document_id": metadata.get("document_id"),
                        "title": metadata.get("title"),
                        "content_hash": metadata.get("content_hash"),
                        "source_key": metadata.get("source_key"),
                        "canonical_url": metadata.get("canonical_url"),
                    },
                }
            )
            if len(results) >= limit:
                break
        return results if results else None
    except Exception:
        logger.exception("Qdrant semantic search failed; falling back to lexical retrieval.")
        return None
