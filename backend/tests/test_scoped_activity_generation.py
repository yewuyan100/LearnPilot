from io import BytesIO

from app.api.deps import get_llm_provider
from app.main import app
from tests.fakes import FakeLearningLLM
from tests.test_learning_activities_api import generate, prepare_context
from tests.test_material_learning_links import create_structure


class NoSourceLearningLLM(FakeLearningLLM):
    def generate_structured(self, **kwargs):
        result = super().generate_structured(**kwargs)
        if kwargs["schema"].__name__ == "GeneratedActivity":
            for question in result.value.questions:
                question.cited_source_ids = []
        return result


def request_payload(course_id, point_id, request_id, **extra):
    return {
        "title": "Scoped learning activity",
        "course_id": course_id,
        "knowledge_point_id": point_id,
        "question_types": ["single_choice", "multiple_choice", "true_false", "short_answer"],
        "question_count": 4,
        "difficulty": "mixed",
        "request_id": request_id,
        **extra,
    }


def test_activity_course_scope_only_uses_linked_material(client):
    http, _ = client
    fake = FakeLearningLLM()
    app.dependency_overrides[get_llm_provider] = lambda: fake
    course, point, linked = prepare_context(client)
    outside = http.post(
        "/api/materials/upload",
        files={"file": ("outside.txt", BytesIO(b"Outside global material " * 30), "text/plain")},
    ).json()
    assert http.post(f"/api/materials/{outside['id']}/process").status_code == 200

    response = http.post(
        "/api/learning-activities/generate",
        json=request_payload(course["id"], point["id"], "scoped-activity-0001"),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["source_scope"]["resolved_material_ids"] == [linked["id"]]
    sources = [source for question in body["questions"] for source in question["sources"]]
    assert sources
    assert {source["material_id"] for source in sources} == {linked["id"]}


def test_activity_empty_scope_is_explicit_and_does_not_call_model(client, goal_payload):
    http, _ = client
    _, course, point = create_structure(http, goal_payload)
    fake = FakeLearningLLM()
    app.dependency_overrides[get_llm_provider] = lambda: fake
    response = http.post(
        "/api/learning-activities/generate",
        json=request_payload(course["id"], point["id"], "scoped-activity-empty"),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "activity_source_scope_empty"
    assert fake.calls == 0


def test_without_materials_mode_is_explicit_and_creates_no_question_sources(
    client, goal_payload
):
    http, _ = client
    _, course, point = create_structure(http, goal_payload)
    fake = NoSourceLearningLLM()
    app.dependency_overrides[get_llm_provider] = lambda: fake
    response = http.post(
        "/api/learning-activities/generate",
        json=request_payload(
            course["id"],
            point["id"],
            "activity-without-sources",
            source_mode="without_materials",
        ),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["source_scope"]["source_mode"] == "without_materials"
    assert body["source_scope"]["resolved_material_ids"] == []
    assert all(question["sources"] == [] for question in body["questions"])
