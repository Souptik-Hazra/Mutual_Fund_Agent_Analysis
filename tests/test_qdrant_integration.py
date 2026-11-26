"""Disposable Qdrant integration checks; no production collection or credentials are used."""

import os
import time
import uuid

import httpx


def test_qdrant_document_filter_reindex_and_delete_lifecycle():
    base_url = os.getenv("QDRANT_TEST_URL")
    if not base_url:
        import pytest
        pytest.skip("Set QDRANT_TEST_URL to run the disposable Qdrant integration test.")

    collection = "mfa_test_" + uuid.uuid4().hex[:16]
    document_one, document_two = 101, 202
    point_id, other_point_id = str(uuid.uuid4()), str(uuid.uuid4())

    with httpx.Client(base_url=base_url.rstrip("/"), timeout=5) as client:
        for attempt in range(30):
            try:
                client.get("/").raise_for_status()
                break
            except httpx.HTTPError:
                if attempt == 29:
                    raise
                time.sleep(1)

        client.put(
            f"/collections/{collection}",
            json={"vectors": {"size": 2, "distance": "Cosine"}},
        ).raise_for_status()
        try:
            initial_points = [
                {
                    "id": point_id,
                    "vector": [0.1, 0.9],
                    "payload": {"metadata": {"document_id": document_one, "chunk_index": 0, "scheme_code": 125497}},
                },
                {
                    "id": other_point_id,
                    "vector": [0.9, 0.1],
                    "payload": {"metadata": {"document_id": document_two, "chunk_index": 0, "scheme_code": 125498}},
                },
            ]
            client.put(
                f"/collections/{collection}/points?wait=true",
                json={"points": initial_points},
            ).raise_for_status()
            # Repeating the same point ID is an upsert, not a duplicate chunk.
            client.put(
                f"/collections/{collection}/points?wait=true",
                json={"points": [{"id": point_id, "vector": [0.2, 0.8], "payload": initial_points[0]["payload"]}]},
            ).raise_for_status()

            scroll = client.post(
                f"/collections/{collection}/points/scroll",
                json={
                    "filter": {"must": [{"key": "metadata.scheme_code", "match": {"value": 125497}}]},
                    "with_payload": True,
                    "limit": 10,
                },
            )
            scroll.raise_for_status()
            rows = scroll.json()["result"]["points"]
            assert len(rows) == 1
            assert rows[0]["id"] == point_id

            deleted = client.post(
                f"/collections/{collection}/points/delete?wait=true",
                json={"filter": {"must": [{"key": "metadata.document_id", "match": {"value": document_one}}]}},
            )
            deleted.raise_for_status()
            remaining = client.post(
                f"/collections/{collection}/points/scroll",
                json={"with_payload": True, "limit": 10},
            )
            remaining.raise_for_status()
            points = remaining.json()["result"]["points"]
            assert len(points) == 1
            assert points[0]["payload"]["metadata"]["document_id"] == document_two
        finally:
            removed = client.delete(f"/collections/{collection}")
            assert removed.status_code in {200, 404}
