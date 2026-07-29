from pathlib import Path


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

