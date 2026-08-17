from sqlalchemy import func, select

from app.api.deps import get_llm_provider
from app.db.session import get_db
from app.learning.agents.lesson.schemas import GeneratedLessonDraft
from app.learning.agents.tutor.schemas import TutorModelAnswer
from app.learning.context.module import LearnerContextModule
from app.learning.context.schemas import ContextQuery, SurfaceContext
from app.main import app
from app.models import MasteryEvidence
from app.services.llm.base import LLMUsage, StructuredLLMResult


class V11ELessonTutorProvider:
    model_name = "v11e-lesson-tutor-acceptance"

    def __init__(self):
        self.lesson_messages: list[dict[str, str]] = []
        self.tutor_messages: list[dict[str, str]] = []

    def generate_structured(self, *, messages, schema, **kwargs):
        if schema is GeneratedLessonDraft:
            self.lesson_messages = messages
            value = schema.model_validate(
                {
                    "objectives": [
                        "Explain Lesson context boundary and apply it to one learning case"
                    ],
                    "core_explanation_markdown": (
                        "Lesson context boundary keeps teaching and citations inside the "
                        "lesson's declared source snapshot. [S1]"
                    ),
                    "common_mistakes": [
                        "Treating an unrelated course material as if it were a lesson source."
                    ],
                    "examples": [
                        {
                            "title": "Bounded explanation",
                            "explanation_markdown": (
                                "Read the linked source, name the boundary, then explain. [S1]"
                            ),
                        }
                    ],
                    "guided_practice": [
                        {
                            "prompt": "Name the source boundary for this lesson.",
                            "hint": "Inspect the cited material before answering.",
                            "expected_approach": "Use the exact lesson source snapshot.",
                        }
                    ],
                    "checks": [
                        {
                            "prompt": "Why must the Tutor stay inside this lesson source?",
                            "check_type": "short_answer",
                            "options": [],
                            "expected_concepts": ["lesson source snapshot"],
                        }
                    ],
                    "estimated_minutes": 28,
                    "cited_source_ids": ["S1"],
                }
            )
        elif schema is TutorModelAnswer:
            self.tutor_messages = messages
            value = schema(
                answer_markdown=(
                    "The lesson objective gives the destination; the cited source gives "
                    "the evidence boundary. Work through the bounded example first. [S1]"
                ),
                teaching_mode="worked_example",
                cited_source_ids=["S1"],
                follow_up_check="Which lesson objective does this example support?",
                limitations=[],
            )
        else:  # pragma: no cover - protects the acceptance seam
            raise AssertionError(f"Unexpected structured schema: {schema}")
        return StructuredLLMResult(
            value=value,
            usage=LLMUsage(input_tokens=160, output_tokens=80),
            model=self.model_name,
            latency_ms=4,
        )


def _db_session():
    generator = app.dependency_overrides[get_db]()
    return generator, next(generator)


def test_v11e_lesson_to_tutor_http_acceptance(client, goal_payload):
    http, _ = client
    goal = http.post(
        "/api/learning-goals",
        json={
            **goal_payload,
            "title": "V11E complete lesson goal",
            "current_level": "needs worked examples",
        },
    ).json()
    course = http.post(
        "/api/courses",
        json={
            "learning_goal_id": goal["id"],
            "title": "Lesson runtime course",
            "status": "active",
        },
    ).json()
    point = http.post(
        f"/api/courses/{course['id']}/knowledge-points",
        json={
            "title": "Lesson context boundary",
            "description": "Bind teaching to an exact lesson version and its real sources.",
            "order_index": 1,
            "estimated_minutes": 28,
        },
    ).json()
    content = (
        "Lesson context boundary uses an exact lesson version and a real source snapshot. "
        "The objective, example, guided practice, Tutor and check share that boundary. " * 16
    )
    uploaded = http.post(
        "/api/materials/upload",
        files={"file": ("lesson-runtime.txt", content.encode(), "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    material = uploaded.json()
    assert http.post(f"/api/materials/{material['id']}/process").status_code == 200
    linked = http.post(
        f"/api/materials/{material['id']}/learning-links",
        json={
            "target_type": "course",
            "course_id": course["id"],
            "relation_type": "primary_source",
            "is_primary": True,
        },
    )
    assert linked.status_code == 201, linked.text

    provider = V11ELessonTutorProvider()
    app.dependency_overrides[get_llm_provider] = lambda: provider
    created = http.post(
        f"/api/courses/{course['id']}/lessons",
        json={
            "title": "Stay inside the learning boundary",
            "description": "Objectives, explanation, example, practice and check in one lesson.",
        },
    )
    assert created.status_code == 201, created.text
    lesson = created.json()
    generated = http.post(
        f"/api/lessons/{lesson['id']}/generate",
        json={
            "request_id": "v11e-http-generation-0001",
            "knowledge_point_ids": [point["id"]],
            "primary_knowledge_point_id": point["id"],
            "target_minutes": 28,
        },
    )
    assert generated.status_code == 200, generated.text
    lesson = generated.json()
    assert lesson["latest_version"]["status"] == "ready"
    assert lesson["active_version"] is None
    assert lesson["latest_version"]["objectives"]
    assert lesson["latest_version"]["examples"]
    assert lesson["latest_version"]["guided_practice"]
    assert lesson["latest_version"]["checks"]
    assert {item["material_id"] for item in lesson["latest_version"]["sources"]} == {
        material["id"]
    }

    published = http.post(
        f"/api/lessons/{lesson['id']}/versions/1/publish",
        json={"expected_version_number": 1, "confirmed": True},
    )
    assert published.status_code == 200, published.text
    lesson = published.json()
    version = lesson["active_version"]
    assert version["status"] == "published"

    session = http.post(
        "/api/learning-sessions",
        json={
            "learning_goal_id": goal["id"],
            "course_id": course["id"],
            "knowledge_point_id": point["id"],
            "lesson_version_id": version["id"],
        },
    )
    assert session.status_code == 201, session.text
    session = session.json()
    assert session["lesson_id"] == lesson["id"]
    assert session["lesson_version_id"] == version["id"]

    generator, db = _db_session()
    try:
        context = LearnerContextModule(db).load(
            ContextQuery(
                actor_key="local-owner",
                surface_context=SurfaceContext(
                    goal_id=goal["id"],
                    course_id=course["id"],
                    knowledge_point_id=point["id"],
                    lesson_id=lesson["id"],
                    lesson_version_id=version["id"],
                    learning_session_id=session["id"],
                ),
            )
        )
        assert context.lesson and context.lesson.id == lesson["id"]
        assert context.lesson_version and context.lesson_version.id == version["id"]
        assert context.lesson_version.objectives == version["objectives"]
        assert context.material_scope.material_ids == [material["id"]]
        evidence_before = db.scalar(select(func.count()).select_from(MasteryEvidence))
    finally:
        generator.close()

    conversation = http.post(
        "/api/agent/conversations", json={"title": "V11E Lesson Tutor"}
    ).json()
    tutor = http.post(
        "/api/learning/runtime/runs",
        json={
            "request_id": "v11e-tutor-runtime-0001",
            "actor_key": "local-owner",
            "input": "Why does the lesson boundary matter? Please use one example.",
            "conversation_id": conversation["id"],
            "channel": "learning_session",
            "surface_context": {
                "goal_id": goal["id"],
                "course_id": course["id"],
                "knowledge_point_id": point["id"],
                "lesson_id": lesson["id"],
                "lesson_version_id": version["id"],
                "learning_session_id": session["id"],
                "source_path": f"/lessons/{lesson['id']}?session={session['id']}",
                "timezone": "Asia/Shanghai",
            },
        },
    )
    assert tutor.status_code == 202, tutor.text
    answer = tutor.json()["tutor_answer"]
    assert answer["teaching_mode"] == "worked_example"
    assert {item["material_id"] for item in answer["citations"]} == {material["id"]}
    assert {item["kind"] for item in answer["context_references"]} >= {
        "lesson",
        "lesson_version",
        "knowledge_point",
        "learning_session",
        "material",
    }
    tutor_prompt = "\n".join(item["content"] for item in provider.tutor_messages)
    assert lesson["title"] in tutor_prompt
    assert '"version_number": 1' in tutor_prompt
    assert version["objectives"][0] in tutor_prompt

    generator, db = _db_session()
    try:
        evidence_after = db.scalar(select(func.count()).select_from(MasteryEvidence))
        assert evidence_after == evidence_before
    finally:
        generator.close()
