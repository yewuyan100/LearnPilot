import json
from pathlib import Path

from app.core.config import get_settings
from app.main import app
from app.services.vector_store.service import INDEX_BUILD_LOCK


def upload_text(test_client, filename: str, content: bytes):
    return test_client.post(
        "/api/materials/upload",
        files={"file": (filename, content, "text/plain")},
    )


def test_processing_chunks_reprocessing_search_and_delete(client):
    test_client, _ = client
    uploaded = upload_text(
        test_client,
        "mcp.txt",
        (
            "MCP 是连接 AI 应用与外部工具和资源的开放协议。\n\n"
            "Client 发起请求，Server 提供 Tools、Resources 和 Prompts。"
        ).encode(),
    )
    assert uploaded.status_code == 201
    material = uploaded.json()
    assert material["processing_status"] == "ready"
    assert material["ingestion_status"] == "pending"
    assert material["indexing_status"] == "pending"

    processed = test_client.post(f"/api/materials/{material['id']}/process")
    assert processed.status_code == 200
    completed = processed.json()
    assert completed["ingestion_status"] == "completed"
    assert completed["indexing_status"] == "completed"
    assert completed["chunk_count"] > 0
    assert completed["indexed_chunk_count"] == completed["chunk_count"]

    page = test_client.get(f"/api/materials/{material['id']}/chunks?page=1&page_size=1")
    assert page.status_code == 200
    assert page.json()["total"] == completed["chunk_count"]
    assert "MCP" in page.json()["items"][0]["content"]
    assert "embedding" not in page.json()["items"][0]

    first_ids = [
        item["id"]
        for item in test_client.get(
            f"/api/materials/{material['id']}/chunks?page_size=100"
        ).json()["items"]
    ]
    reprocessed = test_client.post(f"/api/materials/{material['id']}/process")
    assert reprocessed.status_code == 200
    assert reprocessed.json()["chunk_count"] == len(first_ids)
    second_page = test_client.get(
        f"/api/materials/{material['id']}/chunks?page_size=100"
    ).json()
    assert second_page["total"] == len(first_ids)
    assert [item["chunk_index"] for item in second_page["items"]] == list(
        range(len(first_ids))
    )

    index_status = test_client.get("/api/materials/index/status")
    assert index_status.status_code == 200
    assert index_status.json()["available"] is True
    assert index_status.json()["stale"] is False

    searched = test_client.post(
        "/api/materials/search",
        json={"query": "MCP 的工具和资源由谁提供？", "top_k": 3},
    )
    assert searched.status_code == 200
    result = searched.json()["results"][0]
    assert result["material_id"] == material["id"]
    assert result["original_filename"] == "mcp.txt"
    assert "content" in result
    assert "embedding" not in result

    deleted = test_client.delete(f"/api/materials/{material['id']}")
    assert deleted.status_code == 204
    assert test_client.get(f"/api/materials/{material['id']}").status_code == 404
    assert test_client.get("/api/materials/index/status").json()["available"] is False


def test_failed_reprocessing_preserves_previous_chunks_and_can_retry(client):
    test_client, _ = client
    material = upload_text(test_client, "stable.txt", b"Stable UTF-8 content about MCP.").json()
    other = upload_text(
        test_client,
        "other.txt",
        b"Independent content about MCP resources.",
    ).json()
    assert test_client.post(f"/api/materials/{material['id']}/process").status_code == 200
    assert test_client.post(f"/api/materials/{other['id']}/process").status_code == 200
    before = test_client.get(
        f"/api/materials/{material['id']}/chunks?page_size=100"
    ).json()
    other_before = test_client.get(
        f"/api/materials/{other['id']}/chunks?page_size=100"
    ).json()
    Path(material["file_path"]).write_bytes(b"\xff\xfe")

    failed = test_client.post(f"/api/materials/{material['id']}/process")
    assert failed.status_code == 422
    state = test_client.get(f"/api/materials/{material['id']}").json()
    assert state["ingestion_status"] == "failed"
    assert state["chunk_count"] == before["total"]
    after = test_client.get(
        f"/api/materials/{material['id']}/chunks?page_size=100"
    ).json()
    assert [item["content_hash"] for item in after["items"]] == [
        item["content_hash"] for item in before["items"]
    ]
    other_after = test_client.get(
        f"/api/materials/{other['id']}/chunks?page_size=100"
    ).json()
    assert [item["content_hash"] for item in other_after["items"]] == [
        item["content_hash"] for item in other_before["items"]
    ]

    Path(material["file_path"]).write_text("Recovered UTF-8 MCP content.", encoding="utf-8")
    retried = test_client.post(f"/api/materials/{material['id']}/process")
    assert retried.status_code == 200
    assert retried.json()["ingestion_status"] == "completed"


def test_search_validation_filter_rebuild_and_missing_material(client):
    test_client, _ = client
    first = upload_text(test_client, "tools.txt", b"MCP tools execute actions.").json()
    second = upload_text(test_client, "resources.txt", b"MCP resources expose data.").json()
    for material in (first, second):
        assert test_client.post(f"/api/materials/{material['id']}/process").status_code == 200

    empty = test_client.post("/api/materials/search", json={"query": "   "})
    assert empty.status_code == 422
    too_many = test_client.post(
        "/api/materials/search",
        json={"query": "MCP", "top_k": 11},
    )
    assert too_many.status_code == 422
    missing_filter = test_client.post(
        "/api/materials/search",
        json={"query": "MCP", "material_ids": [999]},
    )
    assert missing_filter.status_code == 404

    filtered = test_client.post(
        "/api/materials/search",
        json={"query": "resources data", "material_ids": [second["id"]]},
    )
    assert filtered.status_code == 200
    assert {
        item["material_id"] for item in filtered.json()["results"]
    } == {second["id"]}

    rebuilt = test_client.post("/api/materials/index/rebuild")
    assert rebuilt.status_code == 200
    assert rebuilt.json()["chunk_count"] >= 2
    assert rebuilt.json()["embedding_dimension"] == 16


def test_chunks_and_processing_return_404(client):
    test_client, _ = client
    assert test_client.post("/api/materials/999/process").status_code == 404
    assert test_client.get("/api/materials/999/chunks").status_code == 404


def test_search_without_index_is_explicit(client):
    test_client, _ = client
    response = test_client.post("/api/materials/search", json={"query": "MCP"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "index_unavailable"

    rebuilt = test_client.post("/api/materials/index/rebuild")
    assert rebuilt.status_code == 200
    assert rebuilt.json()["chunk_count"] == 0
    status_response = test_client.get("/api/materials/index/status")
    assert status_response.status_code == 200
    assert status_response.json()["available"] is False
    assert test_client.post(
        "/api/materials/search",
        json={"query": "MCP"},
    ).status_code == 409


def test_rebuild_rejects_concurrent_request(client):
    test_client, _ = client
    assert INDEX_BUILD_LOCK.acquire(blocking=False)
    try:
        response = test_client.post("/api/materials/index/rebuild")
    finally:
        INDEX_BUILD_LOCK.release()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "index_build_in_progress"


def test_search_is_stably_ranked_and_deleted_material_is_not_returned(client):
    test_client, _ = client
    first = upload_text(test_client, "first.txt", b"Identical stable ranking text.").json()
    second = upload_text(test_client, "second.txt", b"Identical stable ranking text.").json()
    for material in (first, second):
        assert test_client.post(f"/api/materials/{material['id']}/process").status_code == 200

    searched = test_client.post(
        "/api/materials/search",
        json={"query": "Identical stable ranking text", "top_k": 10},
    )
    assert searched.status_code == 200
    results = searched.json()["results"]
    assert [item["rank"] for item in results] == list(range(1, len(results) + 1))
    assert [item["score"] for item in results] == sorted(
        [item["score"] for item in results],
        reverse=True,
    )
    assert [item["chunk_id"] for item in results] == sorted(
        item["chunk_id"] for item in results
    )

    assert test_client.delete(f"/api/materials/{first['id']}").status_code == 204
    after_delete = test_client.post(
        "/api/materials/search",
        json={"query": "Identical stable ranking text", "top_k": 10},
    )
    assert after_delete.status_code == 200
    assert {item["material_id"] for item in after_delete.json()["results"]} == {
        second["id"]
    }
    status_response = test_client.get("/api/materials/index/status").json()
    assert status_response["chunk_count"] == 1


def test_search_rejects_stale_manifest(client):
    test_client, _ = client
    material = upload_text(
        test_client,
        "stale.txt",
        b"Content protected by the manifest checksum.",
    ).json()
    assert test_client.post(f"/api/materials/{material['id']}/process").status_code == 200

    settings = app.dependency_overrides[get_settings]()
    manifest = json.loads(settings.faiss_manifest_path.read_text(encoding="utf-8"))
    manifest["content_checksum"] = "stale"
    settings.faiss_manifest_path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    response = test_client.post(
        "/api/materials/search",
        json={"query": "manifest checksum"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "index_stale"
