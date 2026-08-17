from tests.test_material_learning_links import (
    archive_point,
    create_structure,
    link_payload,
    upload_material,
)


def process(http, material):
    response = http.post(f"/api/materials/{material['id']}/process")
    assert response.status_code == 200
    return response.json()


def test_chunk_source_is_searchable_traceable_and_idempotent(client, goal_payload):
    http, _ = client
    _, course, point = create_structure(http, goal_payload)
    material = process(http, upload_material(http))
    assert http.post(
        f"/api/materials/{material['id']}/learning-links",
        json=link_payload("course", course["id"]),
    ).status_code == 201

    page = http.get(
        f"/api/knowledge-points/{point['id']}/source-chunks",
        params={"material_id": material["id"], "search": "Scoped", "page_size": 10},
    )
    assert page.status_code == 200
    chunk = page.json()["items"][0]
    payload = {
        "material_id": material["id"],
        "material_chunk_id": chunk["id"],
        "source_type": "chunk",
        "note": "Key evidence",
    }
    created = http.post(f"/api/knowledge-points/{point['id']}/sources", json=payload)
    assert created.status_code == 201
    body = created.json()
    assert body["material_id"] == material["id"]
    assert body["material_chunk_id"] == chunk["id"]
    assert body["source_available"] is True
    assert f"chunk={chunk['id']}" in body["context_url"]
    assert "Deterministic learning material" in body["quoted_text"]

    duplicate = http.post(f"/api/knowledge-points/{point['id']}/sources", json=payload)
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == body["id"]
    assert len(http.get(f"/api/knowledge-points/{point['id']}/sources").json()) == 1


def test_source_rejects_out_of_scope_and_chunk_material_mismatch(client, goal_payload):
    http, _ = client
    _, _, point = create_structure(http, goal_payload)
    material_a = process(http, upload_material(http, "a.md"))
    material_b = process(http, upload_material(http, "b.md"))
    out_of_scope = http.post(
        f"/api/knowledge-points/{point['id']}/sources",
        json={"material_id": material_a["id"], "source_type": "material"},
    )
    assert out_of_scope.status_code == 409

    assert http.post(
        f"/api/materials/{material_a['id']}/learning-links",
        json=link_payload("knowledge_point", point["id"]),
    ).status_code == 201
    chunk_b = http.get(f"/api/materials/{material_b['id']}/chunks").json()["items"][0]
    mismatch = http.post(
        f"/api/knowledge-points/{point['id']}/sources",
        json={
            "material_id": material_a["id"],
            "material_chunk_id": chunk_b["id"],
            "source_type": "chunk",
        },
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "knowledge_point_source_chunk_mismatch"


def test_source_lifecycle_does_not_delete_material(client, goal_payload):
    http, _ = client
    _, _, point = create_structure(http, goal_payload)
    material = process(http, upload_material(http))
    assert http.post(
        f"/api/materials/{material['id']}/learning-links",
        json=link_payload("knowledge_point", point["id"]),
    ).status_code == 201
    source = http.post(
        f"/api/knowledge-points/{point['id']}/sources",
        json={"material_id": material["id"], "source_type": "material"},
    ).json()
    assert http.delete(
        f"/api/knowledge-points/{point['id']}/sources/{source['id']}"
    ).status_code == 204
    assert http.get(f"/api/materials/{material['id']}").status_code == 200

    assert http.post(
        f"/api/knowledge-points/{point['id']}/sources",
        json={"material_id": material["id"], "source_type": "material"},
    ).status_code == 201
    archive_point(http, point, "来源生命周期测试归档")
    assert http.get(f"/api/materials/{material['id']}").status_code == 200
