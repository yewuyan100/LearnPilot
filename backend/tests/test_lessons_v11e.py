from sqlalchemy import select

from app.db.session import get_db
from app.learning.agents.lesson.schemas import (
    GeneratedGuidedPractice,
    GeneratedLessonDraft,
    GeneratedLessonExample,
    GeneratedUnderstandingCheck,
    LessonAgentResult,
)
from app.learning.lessons.module import LessonModule
from app.learning.lessons.schemas import (
    LessonCreate,
    LessonGenerateRequest,
    LessonPublishRequest,
)
from app.main import app
from app.models import LessonVersion, MaterialChunk
from app.services.rag.types import RagSource


class FakeLessonAgent:
    def __init__(self, source: RagSource):
        self.source = source
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        point_title = request.knowledge_points[0].title
        return LessonAgentResult(
            draft=GeneratedLessonDraft(
                objectives=[f"Explain {point_title} and apply it in context"],
                core_explanation_markdown=(
                    f"{point_title} starts by identifying the declared boundary, "
                    "then applying the rule to one concrete case. [S1]"
                ),
                common_mistakes=["Using a source that is outside the declared course scope."],
                examples=[
                    GeneratedLessonExample(
                        title="Boundary example",
                        explanation_markdown="Keep the explanation inside the linked material. [S1]",
                    )
                ],
                guided_practice=[
                    GeneratedGuidedPractice(
                        prompt="Identify the boundary before solving the example.",
                        hint="Start from the linked source.",
                        expected_approach="Name the boundary, then apply the rule.",
                    )
                ],
                checks=[
                    GeneratedUnderstandingCheck(
                        prompt="What boundary must be checked first?",
                        check_type="short_answer",
                        expected_concepts=["declared source scope"],
                    )
                ],
                estimated_minutes=request.target_minutes,
                cited_source_ids=["S1"],
            ),
            sources=[self.source],
            model_name="fake-v11e-lesson-agent",
        )


def _db_session():
    generator = app.dependency_overrides[get_db]()
    return generator, next(generator)


def _course_point(http, goal_payload):
    goal = http.post(
        "/api/learning-goals",
        json={**goal_payload, "title": "V11E domain goal", "current_level": "beginner"},
    ).json()
    course = http.post(
        "/api/courses",
        json={
            "learning_goal_id": goal["id"],
            "title": "Scoped lesson course",
            "status": "active",
        },
    ).json()
    point = http.post(
        f"/api/courses/{course['id']}/knowledge-points",
        json={
            "title": "Declared source boundary",
            "description": "Keep teaching inside the effective material scope.",
            "order_index": 1,
            "estimated_minutes": 25,
        },
    ).json()
    return goal, course, point


def _material(http, course_id: int, *, name: str, linked: bool = True):
    content = (
        "Declared source boundary means a lesson cites only materials linked to its course. "
        "A concrete example checks the boundary before explaining the rule. " * 12
    )
    upload = http.post(
        "/api/materials/upload",
        files={"file": (name, content.encode(), "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    material = upload.json()
    processed = http.post(f"/api/materials/{material['id']}/process")
    assert processed.status_code == 200, processed.text
    if linked:
        response = http.post(
            f"/api/materials/{material['id']}/learning-links",
            json={
                "target_type": "course",
                "course_id": course_id,
                "relation_type": "primary_source",
                "is_primary": True,
            },
        )
        assert response.status_code == 201, response.text
    return material


def _source(db, material_id: int) -> RagSource:
    chunk = db.scalar(
        select(MaterialChunk)
        .where(MaterialChunk.material_id == material_id)
        .order_by(MaterialChunk.chunk_index)
    )
    assert chunk is not None
    return RagSource(
        source_label="S1",
        rank=1,
        score=0.99,
        chunk_id=chunk.id,
        material_id=material_id,
        original_filename="lesson-scope.txt",
        chunk_index=chunk.chunk_index,
        content=chunk.content,
        page_number=chunk.page_number,
        section_title=chunk.section_title,
    )


def test_lesson_module_versions_publish_and_preserves_session_history(client, goal_payload):
    http, _ = client
    goal, course, point = _course_point(http, goal_payload)
    material = _material(http, course["id"], name="lesson-scope.txt")

    legacy = http.post(
        "/api/learning-sessions",
        json={
            "learning_goal_id": goal["id"],
            "course_id": course["id"],
            "knowledge_point_id": point["id"],
        },
    ).json()
    assert legacy["lesson_version_id"] is None

    generator, db = _db_session()
    try:
        agent = FakeLessonAgent(_source(db, material["id"]))
        module = LessonModule(db, agent, app.state.clock)
        lesson = module.create(
            course["id"],
            LessonCreate(title="A real lesson", description="A complete teaching experience."),
        )
        lesson = module.generate(
            lesson.id,
            LessonGenerateRequest(
                request_id="v11e-domain-version-0001",
                knowledge_point_ids=[point["id"]],
                target_minutes=25,
            ),
        )
        assert lesson.latest_version is not None
        assert lesson.latest_version.status == "ready"
        assert lesson.active_version is None
        lesson = module.publish(
            lesson.id,
            1,
            LessonPublishRequest(expected_version_number=1, confirmed=True),
        )
        first_version_id = lesson.active_version.id
        assert lesson.active_version.status == "published"

        lesson = module.generate(
            lesson.id,
            LessonGenerateRequest(
                request_id="v11e-domain-version-0002",
                knowledge_point_ids=[point["id"]],
                target_minutes=30,
            ),
        )
        assert lesson.status == "published"
        assert lesson.active_version.version_number == 1
        assert lesson.latest_version.version_number == 2
        assert lesson.latest_version.status == "ready"
        lesson = module.publish(
            lesson.id,
            2,
            LessonPublishRequest(expected_version_number=2, confirmed=True),
        )
        assert lesson.active_version.version_number == 2
        assert db.get(LessonVersion, first_version_id).status == "superseded"
    finally:
        generator.close()

    unchanged_legacy = http.get(f"/api/learning-sessions/{legacy['id']}").json()
    assert unchanged_legacy["lesson_version_id"] is None
    completed = http.patch(
        f"/api/learning-sessions/{legacy['id']}", json={"status": "completed"}
    )
    assert completed.status_code == 200, completed.text
    bound = http.post(
        "/api/learning-sessions",
        json={
            "learning_goal_id": goal["id"],
            "course_id": course["id"],
            "knowledge_point_id": point["id"],
        },
    )
    assert bound.status_code == 201, bound.text
    assert bound.json()["lesson_version_id"] == lesson.active_version.id
    assert bound.json()["lesson_id"] == lesson.id
    assert bound.json()["lesson_version_number"] == 2


def test_lesson_generation_rejects_source_outside_effective_scope(client, goal_payload):
    http, _ = client
    _goal, course, point = _course_point(http, goal_payload)
    _material(http, course["id"], name="in-scope.txt")
    outside = _material(http, course["id"], name="outside.txt", linked=False)

    generator, db = _db_session()
    try:
        module = LessonModule(
            db,
            FakeLessonAgent(_source(db, outside["id"])),
            app.state.clock,
        )
        lesson = module.create(
            course["id"], LessonCreate(title="Scope validation lesson")
        )
        lesson = module.generate(
            lesson.id,
            LessonGenerateRequest(
                request_id="v11e-invalid-source-0001",
                knowledge_point_ids=[point["id"]],
            ),
        )
        assert lesson.latest_version.status == "review_required"
        codes = {item["code"] for item in lesson.latest_version.quality_report["issues"]}
        assert "source_outside_effective_scope" in codes
        assert {item.material_id for item in lesson.latest_version.sources} == {outside["id"]}
    finally:
        generator.close()

    blocked = http.post(
        f"/api/lessons/{lesson.id}/versions/1/publish",
        json={"expected_version_number": 1, "confirmed": True},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "lesson_version_not_ready"
