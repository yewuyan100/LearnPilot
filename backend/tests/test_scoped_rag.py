from app.api.deps import get_llm_provider
from app.main import app
from tests.test_material_learning_links import create_structure, link_payload, upload_material
from tests.test_rag import FakeLLMProvider


def answer_value():
    return {
        "answerable": True,
        "blocks": [{
            "content_markdown": "Scoped evidence supports the answer.",
            "source_ids": ["S1"],
        }],
        "refusal_reason": None,
    }


def process(http, material):
    assert http.post(f"/api/materials/{material['id']}/process").status_code == 200
    return material


def ask(http, conversation_id, request_id, **scope):
    return http.post(
        f"/api/rag/conversations/{conversation_id}/ask",
        json={
            "question": "What does scoped source explain?",
            "request_id": request_id,
            "top_k": 3,
            **scope,
        },
    )


def test_rag_scope_filters_goal_course_point_and_material(client, goal_payload):
    http, _ = client
    goal, course, point = create_structure(http, goal_payload)
    material_a = process(http, upload_material(http, "course-a.md"))
    material_b = process(http, upload_material(http, "global-b.md"))
    assert http.post(
        f"/api/materials/{material_a['id']}/learning-links",
        json=link_payload("course", course["id"]),
    ).status_code == 201
    provider = FakeLLMProvider([answer_value(), answer_value(), answer_value(), answer_value()])
    app.dependency_overrides[get_llm_provider] = lambda: provider
    conversation = http.post("/api/rag/conversations", json={"title": "Scoped"}).json()

    scopes = [
        {"learning_goal_id": goal["id"]},
        {"course_id": course["id"]},
        {"knowledge_point_id": point["id"]},
        {"material_ids": [material_b["id"]]},
    ]
    expected = [material_a["id"], material_a["id"], material_a["id"], material_b["id"]]
    for index, (scope, expected_material_id) in enumerate(zip(scopes, expected), start=1):
        response = ask(http, conversation["id"], f"scope-{index:04d}", **scope)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["assistant_message"]["citations"][0]["material_id"] == expected_material_id
        assert body["retrieval"]["resolved_material_ids"] == [expected_material_id]
        assert body["retrieval"]["final_count"] >= 1
        if scope.get("course_id"):
            contexts = body["assistant_message"]["citations"][0]["learning_context"]
            assert contexts["material_links"][0]["target_type"] == "course"


def test_scope_intersection_and_empty_scope_never_fall_back_global(client, goal_payload):
    http, _ = client
    _, course, _ = create_structure(http, goal_payload)
    linked = process(http, upload_material(http, "linked.md"))
    outside = process(http, upload_material(http, "outside.md"))
    assert http.post(
        f"/api/materials/{linked['id']}/learning-links",
        json=link_payload("course", course["id"]),
    ).status_code == 201
    provider = FakeLLMProvider([])
    app.dependency_overrides[get_llm_provider] = lambda: provider
    conversation = http.post("/api/rag/conversations", json={"title": "Empty scope"}).json()

    empty = ask(
        http,
        conversation["id"],
        "empty-0001",
        course_id=course["id"],
        material_ids=[outside["id"]],
    )
    assert empty.status_code == 200
    body = empty.json()
    assert body["assistant_message"]["answerable"] is False
    assert body["assistant_message"]["refusal_reason"] == "empty_material_scope"
    assert body["retrieval"]["resolved_material_ids"] == []
    assert body["assistant_message"]["citations"] == []
    assert provider.calls == 0

    link = http.get(f"/api/materials/{linked['id']}/learning-links").json()[0]
    assert http.delete(
        f"/api/materials/{linked['id']}/learning-links/{link['id']}"
    ).status_code == 204
    after_unlink = ask(http, conversation["id"], "empty-0002", course_id=course["id"])
    assert after_unlink.json()["assistant_message"]["refusal_reason"] == "empty_material_scope"
