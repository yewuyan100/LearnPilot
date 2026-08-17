from pathlib import Path


def create_learning_context(http):
    goal = http.post(
        "/api/learning-goals",
        json={
            "title": "建立可靠的学习笔记",
            "description": "",
            "target_date": "2026-08-20",
            "daily_minutes": 30,
            "current_level": "入门",
            "status": "active",
        },
    ).json()
    course = http.post(
        "/api/courses",
        json={
            "learning_goal_id": goal["id"],
            "title": "笔记方法",
            "description": "",
            "status": "active",
        },
    ).json()
    point = http.post(
        f"/api/courses/{course['id']}/knowledge-points",
        json={
            "title": "来源摘录",
            "description": "",
            "order_index": 0,
            "estimated_minutes": 20,
            "status": "learning",
        },
    ).json()
    return goal, course, point


def upload_and_process(http, name="notes-source.txt"):
    material = http.post(
        "/api/materials/upload",
        files={
            "file": (
                name,
                "可靠笔记保留来源位置，也允许用户添加自己的理解。".encode(),
                "text/plain",
            )
        },
    ).json()
    processed = http.post(f"/api/materials/{material['id']}/process").json()
    chunk = http.get(
        f"/api/materials/{material['id']}/chunks?page_size=10"
    ).json()["items"][0]
    return processed, chunk


def test_note_crud_autosave_search_pin_archive_and_reflection(client):
    http, _ = client
    _, course, point = create_learning_context(http)
    created = http.post(
        "/api/notes",
        json={
            "content_markdown": "# 可靠笔记\n先记录，再整理。",
            "note_type": "study",
            "tags": ["方法", "方法", "复习"],
            "links": [
                {
                    "entity_type": "course",
                    "entity_id": course["id"],
                    "relation_type": "about",
                },
                {
                    "entity_type": "knowledge_point",
                    "entity_id": point["id"],
                },
            ],
        },
    )
    assert created.status_code == 201
    note = created.json()
    assert note["title"] == "可靠笔记"
    assert note["tags"] == ["复习", "方法"]
    assert len(note["links"]) == 2

    autosaved = http.patch(
        f"/api/notes/{note['id']}",
        json={
            "title": "可恢复的学习笔记",
            "content_markdown": "## 更新\n自动保存使用同一个 PATCH 接口。",
            "is_pinned": True,
            "tags": ["可靠性", "复习"],
        },
    )
    assert autosaved.status_code == 200
    assert autosaved.json()["is_pinned"] is True
    assert autosaved.json()["tags"] == ["可靠性", "复习"]

    searched = http.get("/api/notes?q=自动保存&tag=可靠性&pinned=true").json()
    assert searched["total"] == 1
    assert searched["items"][0]["id"] == note["id"]
    related = http.get(
        f"/api/notes?entity_type=course&entity_id={course['id']}"
    ).json()
    assert related["total"] == 1

    reflection = http.post(
        "/api/notes",
        json={
            "title": "本周复盘",
            "content_markdown": "完成情况：整理了一条真实笔记。",
            "note_type": "reflection",
        },
    ).json()
    assert http.get("/api/notes?note_type=reflection").json()["items"][0][
        "id"
    ] == reflection["id"]

    archived = http.delete(f"/api/notes/{note['id']}")
    assert archived.status_code == 204
    assert http.get("/api/notes").json()["total"] == 1
    archived_page = http.get("/api/notes?archived=true").json()
    assert archived_page["total"] == 1
    assert archived_page["items"][0]["status"] == "archived"
    restored = http.patch(
        f"/api/notes/{note['id']}", json={"status": "active"}
    ).json()
    assert restored["archived_at"] is None

    unconfirmed = http.delete(
        f"/api/notes/{note['id']}?permanent=true"
    )
    assert unconfirmed.status_code == 409
    assert unconfirmed.json()["error"]["code"] == "note_delete_confirmation_required"
    assert http.delete(
        f"/api/notes/{note['id']}?permanent=true&confirmed=true"
    ).status_code == 204
    assert http.get(f"/api/notes/{note['id']}").status_code == 404


def test_note_source_snapshot_and_invalidated_links_survive_source_deletion(client):
    http, _ = client
    goal, course, _ = create_learning_context(http)
    material, chunk = upload_and_process(http)
    created = http.post(
        "/api/notes",
        json={
            "title": "资料摘录",
            "content_markdown": "我的补充：来源位置需要保留。",
            "note_type": "material",
            "links": [
                {"entity_type": "course", "entity_id": course["id"]},
                {"entity_type": "material", "entity_id": material["id"]},
            ],
            "sources": [
                {
                    "material_id": material["id"],
                    "chunk_id": chunk["id"],
                    "quoted_text": "可靠笔记保留来源位置",
                }
            ],
        },
    )
    assert created.status_code == 201
    note = created.json()
    assert note["sources"][0]["source_available"] is True
    assert "片段" in note["sources"][0]["source_locator"]

    assert http.delete(f"/api/materials/{material['id']}").status_code == 204
    after_material_delete = http.get(f"/api/notes/{note['id']}").json()
    material_link = next(
        item for item in after_material_delete["links"]
        if item["entity_type"] == "material"
    )
    assert material_link["source_available"] is False
    assert material_link["entity_title"] == "来源已失效"
    source = after_material_delete["sources"][0]
    assert source["material_id"] is None
    assert source["source_available"] is False
    assert source["quoted_text"] == "可靠笔记保留来源位置"

    assert http.delete(f"/api/learning-goals/{goal['id']}").status_code == 204
    after_course_delete = http.get(f"/api/notes/{note['id']}").json()
    assert all(
        item["entity_type"] != "course"
        for item in after_course_delete["links"]
    )
    assert after_course_delete["content_markdown"].startswith("我的补充")


def test_note_rename_rejects_empty_title_and_delete_preserves_linked_assets(client):
    http, _ = client
    goal, _, _ = create_learning_context(http)
    material, chunk = upload_and_process(http, "delete-note-source.txt")
    unrelated = http.post(
        "/api/notes",
        json={"title": "无关笔记", "content_markdown": "保留"},
    ).json()
    note = http.post(
        "/api/notes",
        json={
            "title": "  临时标题  ",
            "content_markdown": "正文保持不变",
            "links": [{"entity_type": "learning_goal", "entity_id": goal["id"]}],
            "sources": [{
                "material_id": material["id"],
                "chunk_id": chunk["id"],
                "quoted_text": "独立资料摘录",
            }],
        },
    ).json()
    assert note["title"] == "临时标题"

    renamed = http.patch(
        f"/api/notes/{note['id']}", json={"title": "  LangGraph Checkpoint 复盘  "}
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "LangGraph Checkpoint 复盘"
    assert renamed.json()["content_markdown"] == "正文保持不变"

    invalid = http.patch(f"/api/notes/{note['id']}", json={"title": "   "})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "note_title_invalid"

    assert http.delete(
        f"/api/notes/{note['id']}?permanent=true&confirmed=true"
    ).status_code == 204
    assert http.get(f"/api/notes/{note['id']}").status_code == 404
    assert http.get(f"/api/materials/{material['id']}").status_code == 200
    assert http.get(f"/api/learning-goals/{goal['id']}").status_code == 200
    assert http.get(f"/api/notes/{unrelated['id']}").status_code == 200


def test_note_delete_not_found(client):
    http, _ = client
    response = http.delete("/api/notes/999999?permanent=true&confirmed=true")
    assert response.status_code == 404


def test_note_link_source_and_markdown_validation(client):
    http, _ = client
    _, course, _ = create_learning_context(http)
    note = http.post(
        "/api/notes",
        json={
            "title": "安全 Markdown",
            "content_markdown": '<script>alert("x")</script> **仍是数据**',
        },
    )
    assert note.status_code == 201
    assert note.headers["content-type"].startswith("application/json")
    assert "<script>" in note.json()["content_markdown"]

    invalid_character = http.patch(
        f"/api/notes/{note.json()['id']}",
        json={"content_markdown": "bad\u0000content"},
    )
    assert invalid_character.status_code == 422
    assert invalid_character.json()["error"]["code"] == "note_content_invalid"

    invalid_type = http.post(
        f"/api/notes/{note.json()['id']}/links",
        json={"entity_type": "unknown", "entity_id": 1},
    )
    assert invalid_type.status_code == 422
    missing_target = http.post(
        f"/api/notes/{note.json()['id']}/links",
        json={"entity_type": "course", "entity_id": 999},
    )
    assert missing_target.status_code == 404

    first = http.post(
        f"/api/notes/{note.json()['id']}/links",
        json={"entity_type": "course", "entity_id": course["id"]},
    )
    duplicate = http.post(
        f"/api/notes/{note.json()['id']}/links",
        json={"entity_type": "course", "entity_id": course["id"]},
    )
    assert first.status_code == duplicate.status_code == 201
    assert first.json()["id"] == duplicate.json()["id"]
    assert http.delete(
        f"/api/notes/{note.json()['id']}/links/{first.json()['id']}"
    ).status_code == 204

    material, chunk = upload_and_process(http, "other-source.txt")
    bad_chunk = http.post(
        f"/api/notes/{note.json()['id']}/sources",
        json={
            "material_id": material["id"],
            "chunk_id": chunk["id"] + 999,
            "quoted_text": "不存在的片段",
        },
    )
    assert bad_chunk.status_code == 422


def test_note_without_links_and_filter_validation(client):
    http, _ = client
    created = http.post(
        "/api/notes", json={"content_markdown": "临时想法"}
    )
    assert created.status_code == 201
    assert created.json()["links"] == []
    assert created.json()["sources"] == []
    assert http.get("/api/notes?entity_type=course").status_code == 422
