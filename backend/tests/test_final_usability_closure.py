from app.main import app
from app.models import AgentConversation, MaterialLearningLink, NoteLink, StudyPlan
from app.db.session import get_db


def create_goal(http, goal_payload, title="临时事项"):
    return http.post(
        "/api/learning-goals", json={**goal_payload, "title": title}
    ).json()


def test_item_rename_trim_invalid_and_not_found(client, goal_payload):
    http, _ = client
    goal = create_goal(http, goal_payload)
    renamed = http.patch(
        f"/api/learning-goals/{goal['id']}", json={"title": "  AI 应用开发学习  "}
    )
    assert renamed.status_code == 200
    assert renamed.json()["id"] == goal["id"]
    assert renamed.json()["title"] == "AI 应用开发学习"
    assert http.get(f"/api/learning-goals/{goal['id']}").json()["title"] == "AI 应用开发学习"

    invalid = http.patch(
        f"/api/learning-goals/{goal['id']}", json={"title": "   "}
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    assert http.patch(
        "/api/learning-goals/999999", json={"title": "不存在"}
    ).status_code == 404


def test_item_delete_preserves_assets_removes_associations_and_invalidates_ai_context(
    client, goal_payload
):
    http, _ = client
    goal = create_goal(http, goal_payload)
    other_goal = create_goal(http, goal_payload, "无关事项")
    course = http.post(
        "/api/courses",
        json={"learning_goal_id": goal["id"], "title": "临时路线", "status": "active"},
    ).json()
    point = http.post(
        f"/api/courses/{course['id']}/knowledge-points",
        json={"title": "临时步骤", "order_index": 1, "estimated_minutes": 20},
    ).json()
    plan = http.post(
        "/api/study-plans",
        json={
            "request_id": "closure-plan-create-001",
            "learning_goal_id": goal["id"],
            "course_id": course["id"],
            "start_date": "2026-08-13",
            "target_date": "2026-08-20",
            "daily_minutes": 20,
            "available_weekdays": [0, 1, 2, 3, 4],
            "allow_weekends": False,
            "intensity": "standard",
            "include_due_reviews": True,
            "use_latest_diagnostic": True,
            "use_existing_mastery": True,
        },
    )
    assert plan.status_code == 201, plan.text
    material = http.post(
        "/api/materials/upload",
        files={"file": ("preserved.txt", b"independent material", "text/plain")},
    ).json()
    assert http.post(
        f"/api/materials/{material['id']}/learning-links",
        json={"target_type": "learning_goal", "learning_goal_id": goal["id"]},
    ).status_code == 201
    note = http.post(
        "/api/notes",
        json={
            "title": "独立笔记",
            "content_markdown": "删除事项后保留",
            "links": [
                {"entity_type": "learning_goal", "entity_id": goal["id"]},
                {"entity_type": "course", "entity_id": course["id"]},
                {"entity_type": "knowledge_point", "entity_id": point["id"]},
            ],
        },
    ).json()
    conversation = http.post(
        "/api/agent/conversations",
        json={
            "title": "事项上下文",
            "context": {"context_type": "goal", "context_id": goal["id"]},
        },
    ).json()

    assert http.delete(f"/api/learning-goals/{goal['id']}").status_code == 204
    assert http.get(f"/api/learning-goals/{goal['id']}").status_code == 404
    assert http.get(f"/api/materials/{material['id']}").status_code == 200
    saved_note = http.get(f"/api/notes/{note['id']}").json()
    assert saved_note["content_markdown"] == "删除事项后保留"
    assert saved_note["links"] == []
    assert http.get(f"/api/learning-goals/{other_goal['id']}").status_code == 200
    assert http.get(
        f"/api/agent/conversations/{conversation['id']}"
    ).json()["status"] == "archived"
    assert http.get(
        f"/api/agent/conversations?context_type=goal&context_id={goal['id']}"
    ).status_code == 404

    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        assert db.query(MaterialLearningLink).count() == 0
        assert db.query(NoteLink).count() == 0
        assert db.query(StudyPlan).count() == 0
        stored = db.get(AgentConversation, conversation["id"])
        assert stored.status == "archived"
    finally:
        generator.close()


def test_item_delete_not_found(client):
    http, _ = client
    response = http.delete("/api/learning-goals/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "learning_goal_not_found"
