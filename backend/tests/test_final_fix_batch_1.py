import httpx
import pytest
from pydantic import BaseModel, ValidationError

from app.api.deps import get_llm_provider
from app.core.config import Settings
from app.core.errors import AppError
from app.learning.agents.curriculum.module import CurriculumAgent
from app.learning.agents.curriculum.schemas import (
    CurriculumAgentRequest,
    CurriculumMaterialScope,
)
from app.main import app
from app.schemas.agent import AgentPlan, IntentClassification
from app.services.llm.base import LLMUsage, StructuredLLMResult
from app.services.llm.errors import (
    LLMAuthenticationError,
    LLMEmptyContentError,
    LLMOutputInvalidError,
    LLMOutputTruncatedError,
    LLMUnavailableError,
)
from app.services.llm.openai_compatible import OpenAICompatibleProvider
from app.services.llm.schemas import RagGroundedAnswerDraft


def _llm_settings(**overrides):
    values = {
        "llm_api_key": "test-key",
        "llm_base_url": "https://llm.invalid/v1",
        "llm_model": "chat-model",
        "llm_structured_model": "structured-model",
        "llm_max_retries": 1,
    }
    values.update(overrides)
    return Settings(**values)


def _response(*, content, finish_reason="stop", status=200):
    return httpx.Response(
        status,
        request=httpx.Request("POST", "https://llm.invalid/v1/chat/completions"),
        json={
            "model": "served-model",
            "choices": [{
                "finish_reason": finish_reason,
                "message": {"content": content, "reasoning_content": ""},
            }],
        } if status == 200 else None,
    )


def test_structured_provider_injects_schema_and_disables_reasoning(monkeypatch):
    captured = {}

    def post(self, path, headers, json):  # noqa: ANN001
        captured.update(json)
        return _response(content=(
            '{"answerable":true,"blocks":[{"content_markdown":"ok",'
            '"source_ids":["S1"]}],"refusal_reason":null}'
        ))

    monkeypatch.setattr(httpx.Client, "post", post)
    result = OpenAICompatibleProvider(_llm_settings()).generate_structured(
        messages=[{"role": "user", "content": "JSON answer"}],
        schema=RagGroundedAnswerDraft,
    )
    assert result.finish_reason == "stop"
    assert captured["model"] == "structured-model"
    assert captured["thinking"] == {"type": "disabled"}
    assert captured["max_tokens"] == 2400
    assert captured["response_format"] == {"type": "json_object"}
    assert "content_markdown" in captured["messages"][-1]["content"]
    assert "source_ids" in captured["messages"][-1]["content"]
    assert "JSON Schema" in captured["messages"][-1]["content"]


@pytest.mark.parametrize(
    ("content", "finish_reason", "error_type", "reason"),
    [
        ("", "length", LLMOutputTruncatedError, "finish_reason_length"),
        ("", "stop", LLMEmptyContentError, "empty_content"),
        ("not-json", "stop", LLMOutputInvalidError, "invalid_json"),
        ('{"answerable":"maybe"}', "stop", LLMOutputInvalidError, "schema_validation"),
    ],
)
def test_deterministic_structured_errors_are_not_blindly_retried(
    monkeypatch, content, finish_reason, error_type, reason
):
    calls = 0

    def post(self, path, headers, json):  # noqa: ANN001
        nonlocal calls
        calls += 1
        return _response(content=content, finish_reason=finish_reason)

    monkeypatch.setattr(httpx.Client, "post", post)
    with pytest.raises(error_type) as raised:
        OpenAICompatibleProvider(_llm_settings()).generate_structured(
            messages=[], schema=RagGroundedAnswerDraft
        )
    assert reason in raised.value.reason
    assert calls == 1


def test_transport_retries_but_authentication_does_not(monkeypatch):
    calls = 0

    def unavailable(self, path, headers, json):  # noqa: ANN001
        nonlocal calls
        calls += 1
        return _response(content=None, status=503)

    monkeypatch.setattr(httpx.Client, "post", unavailable)
    with pytest.raises(LLMUnavailableError):
        OpenAICompatibleProvider(_llm_settings()).generate_structured(
            messages=[], schema=RagGroundedAnswerDraft
        )
    assert calls == 2

    calls = 0

    def unauthorized(self, path, headers, json):  # noqa: ANN001
        nonlocal calls
        calls += 1
        return _response(content=None, status=401)

    monkeypatch.setattr(httpx.Client, "post", unauthorized)
    with pytest.raises(LLMAuthenticationError):
        OpenAICompatibleProvider(_llm_settings()).generate_structured(
            messages=[], schema=RagGroundedAnswerDraft
        )
    assert calls == 1


VALID_TOOL_ARGUMENTS = {
    "answer_from_materials": {"question": "解释资料"},
    "search_materials": {"query": "检索"},
    "list_courses": {},
    "list_knowledge_points": {"course_id": 1},
    "list_daily_tasks": {"scheduled_date": "2026-08-09"},
    "get_learning_progress": {},
    "list_learning_activities": {"status": "draft"},
    "get_activity_summary": {"activity_id": 1},
    "list_quiz_attempts": {"activity_id": 1},
    "get_wrong_answers": {"status": "active"},
    "get_knowledge_mastery": {"knowledge_point_id": 1},
    "list_weak_knowledge_points": {"course_id": 1},
    "list_due_reviews": {"start_date": "2026-08-09"},
    "get_adaptive_recommendations": {"status": "pending"},
    "explain_mastery": {"knowledge_point_id": 1},
    "get_next_learning_action": {"available_minutes": 30},
    "create_daily_task": {"learning_goal_id": 1, "title": "复习", "scheduled_date": "2026-08-09"},
    "update_daily_task_status": {"task_id": 1, "status": "completed"},
    "save_learning_note": {"learning_goal_id": 1, "note": "记录"},
    "generate_learning_activity": {"title": "练习", "material_ids": [1], "question_types": ["single_choice"], "question_count": 3, "difficulty": "easy"},
    "create_wrong_answer_review": {"wrong_answer_ids": [1]},
    "start_quiz_attempt": {"activity_id": 1},
    "accept_review_recommendation": {"recommendation_id": 1},
}


@pytest.mark.parametrize("tool_name,arguments", VALID_TOOL_ARGUMENTS.items())
def test_every_agent_tool_uses_a_typed_argument_model(tool_name, arguments):
    plan = AgentPlan.model_validate({
        "steps": [{"tool_name": tool_name, "arguments": arguments}]
    })
    assert isinstance(plan.steps[0].arguments, BaseModel)
    with pytest.raises(ValidationError):
        AgentPlan.model_validate({
            "steps": [{"tool_name": tool_name, "arguments": {**arguments, "undeclared": True}}]
        })


class RepairingPlanProvider:
    model_name = "repair-test"

    def __init__(self, repair_succeeds: bool):
        self.repair_succeeds = repair_succeeds
        self.plan_calls = 0

    def generate_structured(self, *, messages, schema, **kwargs):
        if schema is IntentClassification:
            value = schema(intent="list_courses", confidence=1, entities={})
        elif schema is AgentPlan:
            self.plan_calls += 1
            is_repair = messages[0]["content"].startswith("Repair one invalid")
            steps = ([{"tool_name": "list_courses", "arguments": {}}]
                if is_repair and self.repair_succeeds
                else [{"tool_name": "list_courses", "arguments": {}}] * 4)
            value = schema(steps=steps)
        else:
            raise AssertionError(schema)
        return StructuredLLMResult(value=value, usage=LLMUsage(), model=self.model_name, latency_ms=1)


@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_agent_plan_has_one_controlled_repair_and_safe_failure(client, repair_succeeds):
    http, _ = client
    provider = RepairingPlanProvider(repair_succeeds)
    app.dependency_overrides[get_llm_provider] = lambda: provider
    conversation = http.post("/api/agent/conversations", json={"title": "repair"}).json()
    result = http.post(
        f"/api/agent/conversations/{conversation['id']}/runs",
        json={"input": "列出课程详情", "request_id": f"repair-{str(repair_succeeds).lower()}-0001"},
    ).json()
    assert provider.plan_calls == 2
    if repair_succeeds:
        assert result["status"] == "completed"
    else:
        assert result["status"] == "failed"
        assert result["error"] == {
            "code": "agent_plan_invalid",
            "safe_message": "AI中心暂时无法理解这项请求，请换一种说法后重试。",
            "retryable": True,
        }
        assert "tool_limit_exceeded" not in result["final_answer"]


def test_agent_conversations_are_isolated_by_explicit_context(client, goal_payload):
    http, _ = client
    goal = http.post("/api/learning-goals", json=goal_payload).json()
    material = http.post(
        "/api/materials/upload",
        files={"file": ("context.md", b"# Context\nbody", "text/markdown")},
    ).json()
    general = http.post("/api/agent/conversations", json={"title": "general"}).json()
    goal_conversation = http.post("/api/agent/conversations", json={
        "title": "goal",
        "context": {"context_type": "goal", "context_id": goal["id"]},
    }).json()
    material_conversation = http.post("/api/agent/conversations", json={
        "title": "material",
        "context": {"context_type": "material", "context_id": material["id"]},
    }).json()

    assert http.get("/api/agent/conversations?context_type=general").json()[0]["id"] == general["id"]
    assert http.get(f"/api/agent/conversations?context_type=goal&context_id={goal['id']}").json()[0]["id"] == goal_conversation["id"]
    assert http.get(f"/api/agent/conversations?context_type=material&context_id={material['id']}").json()[0]["id"] == material_conversation["id"]
    assert http.get("/api/agent/conversations?context_type=goal").status_code == 422
    assert http.get(f"/api/agent/conversations?context_type=general&context_id={goal['id']}").status_code == 422
    assert http.post("/api/agent/conversations", json={
        "title": "missing",
        "context": {"context_type": "lesson", "context_id": 999999},
    }).status_code == 404


class RaisingProvider:
    def __init__(self, error):
        self.error = error

    def generate_structured(self, **kwargs):
        raise self.error


def _curriculum_request():
    return CurriculumAgentRequest(
        user_request="学习 LangGraph",
        goal_id=1,
        goal_title="LangGraph",
        goal_description="掌握基础",
        current_level="入门",
        target_date=None,
        daily_minutes=30,
        material_scope=CurriculumMaterialScope(mode="goal_only"),
    )


@pytest.mark.parametrize(
    ("error", "status_code", "public_code"),
    [
        (LLMOutputInvalidError("bad", reason="invalid_json"), 502, "curriculum_output_invalid"),
        (LLMUnavailableError("offline"), 503, "curriculum_model_unavailable"),
        (LLMAuthenticationError("bad key"), 503, "curriculum_model_configuration_error"),
    ],
)
def test_curriculum_maps_structured_failures_without_flattening(error, status_code, public_code):
    with pytest.raises(AppError) as raised:
        CurriculumAgent(RaisingProvider(error), Settings()).generate(_curriculum_request())
    assert raised.value.status_code == status_code
    assert raised.value.code == public_code
