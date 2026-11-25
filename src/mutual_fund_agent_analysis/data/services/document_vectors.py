"""Optional Qdrant semantic retrieval for uploaded research documents."""
import logging
from typing import Any

from mutual_fund_agent_analysis.core.config import get_settings

logger = logging.getLogger(__name__)


def index_chunks(document_id: int, title: str, chunks: list[dict[str, Any]]) -> bool:
    """Index chunks when Qdrant and Gemini credentials are configured; never block ingestion."""
    settings = get_settings()
    if not settings.qdrant_url or not settings.gemini_api_key:
        return False
    try:
        from langchain_core.documents import Document
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        from langchain_qdrant import QdrantVectorStore

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
        QdrantVectorStore.from_documents(
            documents,
            embeddings,
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
            collection_name=settings.qdrant_collection,
        )
        return True
    except Exception:
        logger.exception("Qdrant document indexing failed; lexical retrieval remains available.")
        return False


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
            results.append({
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
            })
            if len(results) >= limit:
                break
        return results if results else None
    except Exception:
        logger.exception("Qdrant semantic search failed; falling back to lexical retrieval.")
        return None
