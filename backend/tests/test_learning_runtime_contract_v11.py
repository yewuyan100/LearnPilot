from sqlalchemy import func, select

from app.api.deps import get_llm_provider
from app.db.session import get_db
from app.learning.context import ContextQuery, LearnerContextModule, SurfaceContext
from app.main import app
from app.models import AgentRun, HarnessRun, LearningEvent
from app.schemas.agent import AgentPlan, IntentClassification
from app.services.llm.base import LLMUsage, StructuredLLMResult


class HarnessAgentProvider:
    model_name = "harness-contract-agent"

    def __init__(self, goal_id: int | None = None):
        self.goal_id = goal_id

    def generate_structured(self, *, messages, schema, **kwargs):
        text = messages[-1]["content"]
        create_task = "create task" in text.lower()
        if schema is IntentClassification:
            value = schema(
                intent="create_daily_task" if create_task else "list_courses",
                confidence=0.99,
                entities=(
                    {
                        "learning_goal_id": self.goal_id,
                        "title": "Harness contract task",
                        "estimated_minutes": 20,
                        "scheduled_date": "2026-08-01",
                    }
                    if create_task
                    else {}
                ),
            )
        elif schema is AgentPlan:
            value = schema(
                steps=[
                    {
                        "tool_name": "create_daily_task",
                        "arguments": {
                            "learning_goal_id": self.goal_id,
                            "title": "Harness contract task",
                            "estimated_minutes": 20,
                            "scheduled_date": "2026-08-01",
                        },
                    }
                ]
                if create_task
                else [{"tool_name": "list_courses", "arguments": {}}]
            )
        else:
            raise AssertionError(f"Unexpected schema: {schema}")
        return StructuredLLMResult(
            value=value,
            usage=LLMUsage(),
            model=self.model_name,
            latency_ms=1,
        )


def _db_session():
    generator = app.dependency_overrides[get_db]()
    return generator, next(generator)


def _learning_surface(http, goal_payload):
    goal = http.post("/api/learning-goals", json=goal_payload).json()
    course = http.post(
        "/api/courses",
        json={"learning_goal_id": goal["id"], "title": "Harness course", "status": "active"},
    ).json()
    point = http.post(
        f"/api/courses/{course['id']}/knowledge-points",
        json={"title": "Harness point", "order_index": 1, "estimated_minutes": 20},
    ).json()
    session = http.post(
        "/api/learning-sessions",
        json={
            "learning_goal_id": goal["id"],
            "course_id": course["id"],
            "knowledge_point_id": point["id"],
        },
    ).json()
    return goal, course, point, session


def _runtime_payload(conversation_id, request_id, *, text="list courses", surface=None):
    return {
        "request_id": request_id,
        "actor_key": "local-owner",
        "input": text,
        "conversation_id": conversation_id,
        "channel": "test",
        "surface_context": surface or {"timezone": "Asia/Shanghai"},
    }


def test_runtime_is_idempotent_and_rejects_changed_input(client):
    http, _ = client
    app.dependency_overrides[get_llm_provider] = lambda: HarnessAgentProvider()
    conversation = http.post("/api/agent/conversations", json={"title": "Harness"}).json()
    payload = _runtime_payload(conversation["id"], "harness-idempotent-1")

    first = http.post("/api/learning/runtime/runs", json=payload)
    second = http.post("/api/learning/runtime/runs", json=payload)
    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json() == first.json()

    conflict = http.post(
        "/api/learning/runtime/runs",
        json={**payload, "input": "a different input"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "request_id_conflict"

    generator, db = _db_session()
    try:
        assert db.scalar(select(func.count()).select_from(HarnessRun)) == 1
    finally:
        generator.close()


def test_learner_context_loads_explicit_goal_course_point_and_session(client, goal_payload):
    http, _ = client
    goal, course, point, session = _learning_surface(http, goal_payload)
    generator, db = _db_session()
    try:
        context = LearnerContextModule(db).load(
            ContextQuery(
                actor_key="local-owner",
                surface_context=SurfaceContext(
                    goal_id=goal["id"],
                    course_id=course["id"],
                    knowledge_point_id=point["id"],
                    learning_session_id=session["id"],
                ),
            )
        )
        assert context.goal.id == goal["id"]
        assert context.course.id == course["id"]
        assert context.knowledge_point.id == point["id"]
        assert context.learning_session.id == session["id"]
        assert context.valid is True
        assert len(context.context_version) == 64
    finally:
        generator.close()


def test_runtime_rejects_a_knowledge_point_from_another_course(client, goal_payload):
    http, _ = client
    goal, course, _point, _session = _learning_surface(http, goal_payload)
    other_course = http.post(
        "/api/courses",
        json={"learning_goal_id": goal["id"], "title": "Other course", "status": "active"},
    ).json()
    other_point = http.post(
        f"/api/courses/{other_course['id']}/knowledge-points",
        json={"title": "Other point", "order_index": 1, "estimated_minutes": 20},
    ).json()
    conversation = http.post("/api/agent/conversations", json={"title": "Mismatch"}).json()
    payload = _runtime_payload(
        conversation["id"],
        "harness-mismatch-1",
        surface={
            "goal_id": goal["id"],
            "course_id": course["id"],
            "knowledge_point_id": other_point["id"],
            "timezone": "Asia/Shanghai",
        },
    )

    response = http.post("/api/learning/runtime/runs", json=payload)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "context_mismatch"


def test_runtime_bridges_existing_agent_and_records_run_and_events(client):
    http, _ = client
    app.dependency_overrides[get_llm_provider] = lambda: HarnessAgentProvider()
    conversation = http.post("/api/agent/conversations", json={"title": "Bridge"}).json()
    response = http.post(
        "/api/learning/runtime/runs",
        json=_runtime_payload(conversation["id"], "harness-bridge-1"),
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "completed"
    assert body["selected_agent"] == "operations"

    generator, db = _db_session()
    try:
        harness_run = db.scalar(select(HarnessRun).where(HarnessRun.public_id == body["run_id"]))
        assert harness_run is not None
        agent_run = db.scalar(select(AgentRun).where(AgentRun.harness_run_id == harness_run.id))
        assert agent_run is not None
        assert agent_run.status == "completed"
        events = db.scalars(
            select(LearningEvent).where(LearningEvent.harness_run_id == harness_run.id)
        ).all()
        assert {event.event_type for event in events} == {"run.started", "run.completed"}
    finally:
        generator.close()


def test_runtime_resume_delegates_to_existing_confirmation_flow(client, goal_payload):
    http, _ = client
    goal = http.post("/api/learning-goals", json=goal_payload).json()
    app.dependency_overrides[get_llm_provider] = lambda: HarnessAgentProvider(goal["id"])
    conversation = http.post("/api/agent/conversations", json={"title": "Resume"}).json()
    pending = http.post(
        "/api/learning/runtime/runs",
        json=_runtime_payload(
            conversation["id"],
            "harness-resume-run-1",
            text="create task",
            surface={"goal_id": goal["id"], "timezone": "Asia/Shanghai"},
        ),
    )
    assert pending.status_code == 202
    assert pending.json()["status"] == "awaiting_confirmation"

    resume_payload = {"decision": "approve", "request_id": "harness-resume-decision-1"}
    resumed = http.post(
        f"/api/learning/runtime/runs/{pending.json()['run_id']}/resume",
        json=resume_payload,
    )
    replay = http.post(
        f"/api/learning/runtime/runs/{pending.json()['run_id']}/resume",
        json=resume_payload,
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "completed"
    assert replay.json() == resumed.json()
