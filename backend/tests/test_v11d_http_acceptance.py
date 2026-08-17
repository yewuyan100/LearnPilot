from sqlalchemy import func, select

from app.api.deps import get_llm_provider
from app.db.session import get_db
from app.learning.agents.curriculum.schemas import CurriculumProposalDraft
from app.learning.context import ContextQuery, LearnerContextModule, SurfaceContext
from app.learning.routing.module import AgentRouter
from app.learning.routing.schemas import RoutingRequest
from app.main import app
from app.models import (
    Course,
    CourseArchitectureDraft,
    HarnessRun,
    KnowledgePoint,
    KnowledgePointPrerequisite,
    LearningProposal,
    Lesson,
    MaterialChunk,
)
from app.services.llm.base import LLMUsage, StructuredLLMResult


class CurriculumAcceptanceProvider:
    model_name = "v11d-curriculum-acceptance"

    def __init__(self, source_chunk_id: int | None = None):
        self.messages: list[dict[str, str]] = []
        self.source_chunk_id = source_chunk_id

    def generate_structured(self, *, messages, schema, **kwargs):
        assert schema is CurriculumProposalDraft
        self.messages = messages
        value = schema.model_validate(
            {
                "course_title": "7 天 LangGraph 核心路径",
                "course_description": "从状态图基础到可恢复执行的结构化学习路径。",
                "knowledge_points": [
                    {
                        "title": "State 与 Reducer",
                        "description": "理解共享状态及其聚合规则。",
                        "learning_objectives": ["说明 State 字段如何通过 reducer 聚合"],
                        "key_terms": ["State", "Reducer"],
                        "difficulty_label": "beginner",
                        "source_chunk_ids": [self.source_chunk_id] if self.source_chunk_id else [],
                    },
                    {
                        "title": "Node 与 Edge",
                        "description": "理解节点职责和控制流连接。",
                        "learning_objectives": ["构建包含条件边的最小图"],
                        "key_terms": ["Node", "Edge"],
                        "difficulty_label": "beginner",
                        "source_chunk_ids": [self.source_chunk_id] if self.source_chunk_id else [],
                    },
                    {
                        "title": "Checkpoint 与恢复",
                        "description": "理解图执行状态的持久化与恢复。",
                        "learning_objectives": ["说明 checkpoint 的恢复边界"],
                        "key_terms": ["Checkpoint"],
                        "difficulty_label": "intermediate",
                        "source_chunk_ids": [self.source_chunk_id] if self.source_chunk_id else [],
                    },
                ],
                "prerequisites": [
                    {
                        "prerequisite_title": "State 与 Reducer",
                        "dependent_title": "Node 与 Edge",
                        "rationale": "先理解状态聚合，再组合图节点。",
                        "confidence": 0.95,
                    },
                    {
                        "prerequisite_title": "Node 与 Edge",
                        "dependent_title": "Checkpoint 与恢复",
                        "rationale": "先理解运行结构，再学习恢复。",
                        "confidence": 0.9,
                    },
                ],
                "learning_order": [
                    "State 与 Reducer",
                    "Node 与 Edge",
                    "Checkpoint 与恢复",
                ],
                "estimated_duration": 120,
                "lesson_blueprints": [
                    {
                        "knowledge_point": "State 与 Reducer",
                        "lesson_goal": "建立共享状态和聚合规则的正确心智模型。",
                        "estimated_minutes": 45,
                        "requires_lesson_generation": True,
                    },
                    {
                        "knowledge_point": "Node 与 Edge",
                        "lesson_goal": "能够规划最小状态图的节点和边。",
                        "estimated_minutes": 45,
                        "requires_lesson_generation": True,
                    },
                    {
                        "knowledge_point": "Checkpoint 与恢复",
                        "lesson_goal": "能够识别持久化和恢复的边界。",
                        "estimated_minutes": 30,
                        "requires_lesson_generation": True,
                    },
                ],
                "assumptions": ["学习者具备 Python 基础"],
                "coverage_report": {
                    "goal_alignment": "覆盖七天入门所需的状态、图结构和恢复能力。",
                    "covered_topics": ["状态聚合", "图结构", "执行恢复"],
                    "gaps": ["未覆盖生产部署"],
                    "material_grounding": (
                        "source_grounded" if self.source_chunk_id else "goal_only_unverified"
                    ),
                },
            }
        )
        return StructuredLLMResult(
            value=value,
            usage=LLMUsage(input_tokens=300, output_tokens=240),
            model=self.model_name,
            latency_ms=4,
        )


def _db_session():
    generator = app.dependency_overrides[get_db]()
    return generator, next(generator)


def _goal(http):
    return http.post(
        "/api/learning-goals",
        json={
            "title": "7 天学习 LangGraph",
            "description": "能够构建带状态、条件路由与恢复能力的基础图应用。",
            "target_date": "2026-08-08",
            "daily_minutes": 45,
            "current_level": "会 Python，未使用过图工作流",
            "status": "active",
        },
    ).json()


def test_v11d_goal_to_proposal_review_and_existing_publish_boundary(client):
    http, _ = client
    goal = _goal(http)
    provider = CurriculumAcceptanceProvider()
    app.dependency_overrides[get_llm_provider] = lambda: provider

    generated = http.post(
        f"/api/learning-goals/{goal['id']}/curriculum-proposals",
        json={
            "request_id": "v11d-generate-http-0001",
            "instruction": "我要 7 天学习 LangGraph",
            "material_ids": [],
        },
    )
    assert generated.status_code == 201, generated.text
    proposal = generated.json()
    assert proposal["status"] == "review_required"
    assert proposal["grounding_mode"] == "goal_only"
    assert proposal["curriculum"]["learning_order"] == [
        "State 与 Reducer",
        "Node 与 Edge",
        "Checkpoint 与恢复",
    ]
    assert len(proposal["curriculum"]["lesson_blueprints"]) == 3
    assert all(
        item["requires_lesson_generation"] is True
        for item in proposal["curriculum"]["lesson_blueprints"]
    )
    assert proposal["architecture"]["status"] == "ready"
    issue_codes = {
        item["code"] for item in proposal["architecture"]["quality_report"]["issues"]
    }
    assert "goal_only_unverified" in issue_codes
    assert "knowledge_point_without_source" not in issue_codes

    prompt = "\n".join(item["content"] for item in provider.messages)
    assert goal["description"] in prompt
    assert goal["current_level"] in prompt
    assert goal["target_date"] in prompt
    assert str(goal["daily_minutes"]) in prompt
    assert "diagnostic_baseline" in prompt
    assert "existing_skills" in prompt

    replay = http.post(
        f"/api/learning-goals/{goal['id']}/curriculum-proposals",
        json={
            "request_id": "v11d-generate-http-0001",
            "instruction": "我要 7 天学习 LangGraph",
            "material_ids": [],
        },
    )
    assert replay.status_code == 201
    assert replay.json()["proposal_id"] == proposal["proposal_id"]

    generator, db = _db_session()
    try:
        assert db.scalar(select(func.count()).select_from(Course)) == 0
        assert db.scalar(select(func.count()).select_from(KnowledgePoint)) == 0
        assert db.scalar(select(func.count()).select_from(Lesson)) == 0
        draft = db.get(CourseArchitectureDraft, proposal["architecture"]["draft_id"])
        assert draft is not None and draft.generation_mode == "curriculum_goal_only"
        row = db.scalar(
            select(LearningProposal).where(
                LearningProposal.public_id == proposal["proposal_id"]
            )
        )
        assert row is not None and row.domain_draft_id == str(draft.id)
    finally:
        generator.close()

    blocked = http.post(
        f"/api/curriculum-proposals/{proposal['proposal_id']}/publish",
        json={
            "expected_proposal_version": proposal["version"],
            "draft_version": proposal["architecture"]["version"],
            "publish_request_id": "v11d-publish-http-0001",
            "confirmed": False,
        },
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "curriculum_publish_confirmation_required"

    accepted = http.post(
        f"/api/curriculum-proposals/{proposal['proposal_id']}/decision",
        json={
            "decision": "accept",
            "expected_version": proposal["version"],
            "request_id": "v11d-decision-http-0001",
            "confirmed": True,
        },
    )
    assert accepted.status_code == 200, accepted.text
    accepted_body = accepted.json()
    assert accepted_body["status"] == "accepted"

    published = http.post(
        f"/api/curriculum-proposals/{proposal['proposal_id']}/publish",
        json={
            "expected_proposal_version": accepted_body["version"],
            "draft_version": accepted_body["architecture"]["version"],
            "publish_request_id": "v11d-publish-http-0002",
            "confirmed": True,
        },
    )
    assert published.status_code == 200, published.text
    publication = published.json()["publication"]
    assert len(publication["course_ids"]) == 1
    assert len(publication["knowledge_point_ids"]) == 3
    assert publication["prerequisite_count"] == 2
    assert publication["source_count"] == 0

    generator, db = _db_session()
    try:
        assert db.scalar(select(func.count()).select_from(Course)) == 1
        assert db.scalar(select(func.count()).select_from(KnowledgePoint)) == 3
        assert db.scalar(select(func.count()).select_from(KnowledgePointPrerequisite)) == 2
        assert db.scalar(select(func.count()).select_from(Lesson)) == 0
    finally:
        generator.close()


def test_v11d_harness_routes_curriculum_tutor_and_operations(client):
    http, _ = client
    goal = _goal(http)
    provider = CurriculumAcceptanceProvider()
    app.dependency_overrides[get_llm_provider] = lambda: provider
    conversation = http.post(
        "/api/agent/conversations", json={"title": "V11D Curriculum"}
    ).json()

    response = http.post(
        "/api/learning/runtime/runs",
        json={
            "request_id": "v11d-harness-http-0001",
            "actor_key": "local-owner",
            "input": "我要学习 LangGraph，请生成学习路径",
            "conversation_id": conversation["id"],
            "channel": "goal",
            "surface_context": {"goal_id": goal["id"], "timezone": "Asia/Shanghai"},
        },
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["selected_agent"] == "curriculum"
    assert body["status"] == "awaiting_confirmation"
    assert body["proposal"]["proposal_type"] == "curriculum"

    generator, db = _db_session()
    try:
        run = db.scalar(select(HarnessRun).where(HarnessRun.public_id == body["run_id"]))
        assert run is not None and run.selected_agent == "curriculum"
        proposal = db.scalar(
            select(LearningProposal).where(
                LearningProposal.public_id == body["proposal"]["proposal_id"]
            )
        )
        assert proposal is not None and proposal.source_harness_run_id == run.id

        surface = SurfaceContext(goal_id=goal["id"])
        context = LearnerContextModule(db).load(
            ContextQuery(actor_key="local-owner", surface_context=surface)
        )
        router = AgentRouter()
        decisions = {
            text: router.route(
                RoutingRequest(
                    input=text,
                    user_intent=router.classify_user_intent(text, surface),
                    context=context,
                    surface_context=surface,
                )
            ).selected_agent
            for text in ("我要学习 LangGraph", "解释 reducer", "完成今天任务")
        }
        assert decisions == {
            "我要学习 LangGraph": "curriculum",
            "解释 reducer": "tutor",
            "完成今天任务": "operations",
        }
    finally:
        generator.close()


def test_v11d_source_grounded_proposal_keeps_real_draft_sources(client):
    http, _ = client
    goal = _goal(http)
    uploaded = http.post(
        "/api/materials/upload",
        files={
            "file": (
                "langgraph.txt",
                ("LangGraph State reducer aggregates updates before checkpoint recovery. " * 20).encode(),
                "text/plain",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    material = uploaded.json()
    assert http.post(f"/api/materials/{material['id']}/process").status_code == 200
    linked = http.post(
        f"/api/materials/{material['id']}/learning-links",
        json={
            "target_type": "learning_goal",
            "learning_goal_id": goal["id"],
            "relation_type": "primary_source",
            "is_primary": True,
        },
    )
    assert linked.status_code == 201, linked.text

    generator, db = _db_session()
    try:
        chunk_id = db.scalar(
            select(MaterialChunk.id)
            .where(MaterialChunk.material_id == material["id"])
            .order_by(MaterialChunk.chunk_index)
        )
        assert chunk_id is not None
    finally:
        generator.close()
    app.dependency_overrides[get_llm_provider] = lambda: CurriculumAcceptanceProvider(chunk_id)

    response = http.post(
        f"/api/learning-goals/{goal['id']}/curriculum-proposals",
        json={
            "request_id": "v11d-grounded-http-0001",
            "instruction": "我要 7 天学习 LangGraph",
        },
    )
    assert response.status_code == 201, response.text
    proposal = response.json()
    assert proposal["grounding_mode"] == "source_grounded"
    assert proposal["material_ids"] == [material["id"]]
    assert proposal["architecture"]["quality_report"]["source_coverage"] == 100
    assert all(
        point["source_chunk_ids"] == [chunk_id]
        for point in proposal["curriculum"]["knowledge_points"]
    )

    generator, db = _db_session()
    try:
        assert db.scalar(select(func.count()).select_from(Course)) == 0
        draft = db.get(CourseArchitectureDraft, proposal["architecture"]["draft_id"])
        assert draft is not None and draft.generation_mode == "curriculum_source_grounded"
    finally:
        generator.close()
