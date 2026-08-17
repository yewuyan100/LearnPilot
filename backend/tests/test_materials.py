from pathlib import Path

from app.services.material_deletion import MaterialDeletionService
from app.services.vector_store.service import MaterialIndexService


def test_upload_and_delete_material(client):
    test_client, upload_path = client
    response = test_client.post(
        "/api/materials/upload",
        files={"file": ("guide.md", b"# MCP\nContent", "text/markdown")},
    )
    assert response.status_code == 201
    material = response.json()
    stored_path = Path(material["file_path"])
    assert stored_path.exists()
    assert stored_path.parent == upload_path
    assert material["processing_status"] == "ready"

    deleted = test_client.delete(f"/api/materials/{material['id']}")
    assert deleted.status_code == 204
    assert not stored_path.exists()
    assert test_client.get("/api/materials").json() == []

    replay = test_client.delete(f"/api/materials/{material['id']}")
    assert replay.status_code == 204


def test_material_delete_index_failure_is_visible_and_retryable(client, monkeypatch):
    test_client, _ = client
    material = test_client.post(
        "/api/materials/upload",
        files={"file": ("retry.md", b"# Retry\nContent", "text/markdown")},
    ).json()
    original_rebuild = MaterialIndexService.rebuild

    def fail_rebuild(self):
        raise RuntimeError("index unavailable")

    monkeypatch.setattr(MaterialIndexService, "rebuild", fail_rebuild)
    failed = test_client.delete(f"/api/materials/{material['id']}")
    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "material_delete_pending"
    state = test_client.get(f"/api/materials/{material['id']}").json()
    assert state["deletion_status"] == "failed"
    assert state["deletion_error"] == "资料索引更新失败，可重新尝试"

    monkeypatch.setattr(MaterialIndexService, "rebuild", original_rebuild)
    retried = test_client.post(f"/api/materials/{material['id']}/delete/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "completed"
    assert retried.json()["attempts"] == 2
    assert test_client.get(f"/api/materials/{material['id']}").status_code == 404


def test_material_delete_file_failure_survives_new_service_request(client, monkeypatch):
    test_client, _ = client
    material = test_client.post(
        "/api/materials/upload",
        files={"file": ("locked.txt", b"locked", "text/plain")},
    ).json()
    target = Path(material["file_path"])
    original_unlink = Path.unlink

    def fail_target(path, *args, **kwargs):
        if path == target:
            raise PermissionError("locked")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_target)
    failed = test_client.delete(f"/api/materials/{material['id']}")
    assert failed.status_code == 503
    assert target.exists()
    assert test_client.get(f"/api/materials/{material['id']}").json()[
        "deletion_status"
    ] == "failed"

    monkeypatch.setattr(Path, "unlink", original_unlink)
    retried = test_client.post(f"/api/materials/{material['id']}/delete/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "completed"
    assert not target.exists()


def test_rejects_unsupported_file(client):
    test_client, _ = client
    response = test_client.post(
        "/api/materials/upload",
        files={"file": ("script.exe", b"MZ", "application/octet-stream")},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_file_type"


def test_rejects_oversized_file(client):
    test_client, upload_path = client
    response = test_client.post(
        "/api/materials/upload",
        files={"file": ("large.txt", b"x" * (1024 * 1024 + 1), "text/plain")},
    )
    assert response.status_code == 413
    assert not list(upload_path.glob("*"))
