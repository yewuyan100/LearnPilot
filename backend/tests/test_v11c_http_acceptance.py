from sqlalchemy import func, select

from app.api.deps import get_llm_provider
from app.db.session import get_db
from app.learning.agents.tutor.schemas import TutorModelAnswer
from app.learning.context import ContextQuery, LearnerContextModule, SurfaceContext
from app.learning.routing.module import AgentRouter
from app.learning.routing.schemas import RoutingRequest
from app.main import app
from app.models import AgentRun, HarnessRun, LearningEvent, MasteryEvidence
from app.services.llm.base import LLMUsage, StructuredLLMResult


class TutorAcceptanceProvider:
    model_name = "v11c-tutor-acceptance"

    def __init__(self):
        self.messages: list[dict[str, str]] = []

    def generate_structured(self, *, messages, schema, **kwargs):
        assert schema is TutorModelAnswer
        self.messages = messages
        return StructuredLLMResult(
            value=schema(
                answer_markdown=(
                    "这个概念的关键是先限定当前课程的执行边界，再看一个具体例子。"
                    "当前资料把 Course A 的边界定义为 tutor-scope-anchor。[S1]"
                ),
                teaching_mode="worked_example",
                cited_source_ids=["S1"],
                follow_up_check="你能用一句话说明为什么不能跨课程取资料吗？",
                limitations=[],
            ),
            usage=LLMUsage(input_tokens=120, output_tokens=60),
            model=self.model_name,
            latency_ms=3,
        )


def _db_session():
    generator = app.dependency_overrides[get_db]()
    return generator, next(generator)


def _course(http, goal_id: int, suffix: str):
    course = http.post(
        "/api/courses",
        json={"learning_goal_id": goal_id, "title": f"Course {suffix}", "status": "active"},
    ).json()
    point = http.post(
        f"/api/courses/{course['id']}/knowledge-points",
        json={"title": f"Point {suffix}", "order_index": 1, "estimated_minutes": 20},
    ).json()
    return course, point


def _material(http, filename: str, content: str):
    uploaded = http.post(
        "/api/materials/upload",
        files={"file": (filename, content.encode("utf-8"), "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    material = uploaded.json()
    processed = http.post(f"/api/materials/{material['id']}/process")
    assert processed.status_code == 200, processed.text
    return material


def _link_course(http, material_id: int, course_id: int):
    response = http.post(
        f"/api/materials/{material_id}/learning-links",
        json={
            "target_type": "course",
            "course_id": course_id,
            "relation_type": "primary_source",
            "is_primary": True,
        },
    )
    assert response.status_code == 201, response.text


def test_v11c_context_scoped_tutor_http_acceptance(client, goal_payload):
    http, _ = client
    goal = http.post(
        "/api/learning-goals",
        json={**goal_payload, "title": "V11C Goal", "current_level": "API beginner"},
    ).json()
    course_a, point_a = _course(http, goal["id"], "A")
    course_b, _point_b = _course(http, goal["id"], "B")
    material_a = _material(
        http,
        "course-a.txt",
        "tutor-scope-anchor means Course A keeps retrieval inside its declared boundary. " * 12,
    )
    material_b = _material(
        http,
        "course-b.txt",
        "tutor-scope-anchor means Course B has a different and private answer. " * 12,
    )
    _link_course(http, material_a["id"], course_a["id"])
    _link_course(http, material_b["id"], course_b["id"])

    session = http.post(
        "/api/learning-sessions",
        json={
            "learning_goal_id": goal["id"],
            "course_id": course_a["id"],
            "knowledge_point_id": point_a["id"],
        },
    ).json()
    conversation = http.post(
        "/api/agent/conversations", json={"title": "V11C Tutor"}
    ).json()
    provider = TutorAcceptanceProvider()
    app.dependency_overrides[get_llm_provider] = lambda: provider

    generator, db = _db_session()
    try:
        context = LearnerContextModule(db).load(
            ContextQuery(
                actor_key="local-owner",
                surface_context=SurfaceContext(
                    goal_id=goal["id"],
                    course_id=course_a["id"],
                    knowledge_point_id=point_a["id"],
                    learning_session_id=session["id"],
                ),
            )
        )
        assert context.goal and context.goal.id == goal["id"]
        assert context.course and context.course.id == course_a["id"]
        assert context.knowledge_point and context.knowledge_point.id == point_a["id"]
        assert context.learning_session and context.learning_session.id == session["id"]
        assert context.material_scope.scoped is True
        assert context.material_scope.material_ids == [material_a["id"]]
        evidence_before = db.scalar(select(func.count()).select_from(MasteryEvidence))
    finally:
        generator.close()

    response = http.post(
        "/api/learning/runtime/runs",
        json={
            "request_id": "v11c-tutor-http-0001",
            "actor_key": "local-owner",
            "input": "为什么 tutor-scope-anchor 要限定边界？请举例。",
            "conversation_id": conversation["id"],
            "channel": "learning_session",
            "surface_context": {
                "goal_id": goal["id"],
                "course_id": course_a["id"],
                "knowledge_point_id": point_a["id"],
                "learning_session_id": session["id"],
                "source_path": f"/learning-sessions/{session['id']}",
                "timezone": "Asia/Shanghai",
            },
        },
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["selected_agent"] == "tutor"
    assert "Course A / Point A" in body["answer"]
    assert "[S1]" in body["answer"]
    answer = body["tutor_answer"]
    assert answer["teaching_mode"] == "worked_example"
    assert answer["follow_up_check"]
    assert {item["material_id"] for item in answer["citations"]} == {material_a["id"]}
    assert material_b["id"] not in {item["material_id"] for item in answer["citations"]}
    assert {item["kind"] for item in answer["context_references"]} >= {
        "course",
        "knowledge_point",
        "learning_session",
        "material",
    }

    prompt = "\n".join(item["content"] for item in provider.messages)
    assert "Course A" in prompt
    assert "Point A" in prompt
    assert "API beginner" in prompt
    assert "course-b.txt" not in prompt

    generator, db = _db_session()
    try:
        run = db.scalar(select(HarnessRun).where(HarnessRun.public_id == body["run_id"]))
        assert run and run.selected_agent == "tutor"
        assert db.scalar(
            select(func.count()).select_from(AgentRun).where(AgentRun.harness_run_id == run.id)
        ) == 0
        assert db.scalar(select(func.count()).select_from(MasteryEvidence)) == evidence_before
        event_types = set(
            db.scalars(
                select(LearningEvent.event_type).where(LearningEvent.harness_run_id == run.id)
            )
        )
        assert event_types == {"run.started", "TutorInteractionRecorded", "run.completed"}
    finally:
        generator.close()

    mismatch = http.post(
        "/api/learning/runtime/runs",
        json={
            "request_id": "v11c-tutor-http-0002",
            "actor_key": "local-owner",
            "input": "为什么这个概念成立？",
            "conversation_id": conversation["id"],
            "channel": "learning_session",
            "surface_context": {
                "goal_id": goal["id"],
                "course_id": course_b["id"],
                "knowledge_point_id": point_a["id"],
                "learning_session_id": session["id"],
                "timezone": "Asia/Shanghai",
            },
        },
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "context_mismatch"

    openapi = http.get("/openapi.json").json()
    assert all(not path.startswith("/api/tutor") for path in openapi["paths"])


def test_v11c_router_keeps_crud_on_operations_and_routes_contextual_questions(client, goal_payload):
    http, _ = client
    goal = http.post("/api/learning-goals", json=goal_payload).json()
    course, point = _course(http, goal["id"], "Router")
    generator, db = _db_session()
    try:
        surface = SurfaceContext(
            goal_id=goal["id"], course_id=course["id"], knowledge_point_id=point["id"]
        )
        context = LearnerContextModule(db).load(
            ContextQuery(actor_key="local-owner", surface_context=surface)
        )
        router = AgentRouter()
        learning = router.route(
            RoutingRequest(
                input="为什么这个概念成立？",
                user_intent=router.classify_user_intent("为什么这个概念成立？", surface),
                context=context,
                surface_context=surface,
            )
        )
        operation = router.route(
            RoutingRequest(
                input="创建一个复习任务",
                user_intent=router.classify_user_intent("创建一个复习任务", surface),
                context=context,
                surface_context=surface,
            )
        )
        assert learning.selected_agent == "tutor"
        assert operation.selected_agent == "operations"
    finally:
        generator.close()
