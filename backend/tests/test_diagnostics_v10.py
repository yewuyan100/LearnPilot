import re

from sqlalchemy import func, select

from app.api.deps import get_llm_provider
from app.db.session import get_db
from app.main import app
from app.models import DiagnosticAdjustment, DiagnosticKnowledgeResult, MasteryEvidence
from app.services.llm.base import LLMUsage, StructuredLLMResult
from app.services.llm.errors import LLMUnavailableError


class DiagnosticProvider:
    model_name = "fake-diagnostic-model"

    def __init__(self, *, confidence=0.95, invalid_source=False, fail=False):
        self.confidence = confidence
        self.invalid_source = invalid_source
        self.fail = fail
        self.calls = 0
        self.messages = []

    def generate_structured(self, *, messages, schema, temperature=None, max_output_tokens=None):
        self.calls += 1
        self.messages.append(messages)
        if self.fail:
            raise LLMUnavailableError("unavailable")
        if schema.__name__ == "ShortAnswerGrade":
            value = schema.model_validate(
                {
                    "earned_points": 2,
                    "matched_items": ["R1"],
                    "missing_items": [],
                    "feedback": "说明了资料中的受控调用。",
                    "confidence": self.confidence,
                    "answer_supported": True,
                }
            )
        else:
            prompt = messages[-1]["content"]
            count = int(re.search(r"题目数量：(\d+)", prompt).group(1))
            types = re.search(r"允许题型：([^\n]+)", prompt).group(1).split(", ")
            questions = [self._question(types[index % len(types)], index) for index in range(count)]
            value = schema.model_validate(
                {"title": "课程初始诊断", "description": "真实资料诊断", "questions": questions}
            )
        return StructuredLLMResult(
            value=value,
            usage=LLMUsage(input_tokens=20, output_tokens=10),
            model=self.model_name,
            latency_ms=3,
        )

    def _question(self, kind, index):
        common = {
            "stem": f"根据资料判断受控调用的含义（{self.calls}-{index}）？",
            "explanation": "资料说明调用必须经过明确边界。",
            "difficulty": "medium",
            "points": 2,
            "cited_source_ids": ["S999" if self.invalid_source else "S1"],
        }
        if kind == "single_choice":
            return {
                **common,
                "question_type": kind,
                "options": [
                    {"id": "A", "text": "经过明确边界"},
                    {"id": "B", "text": "任意执行"},
                    {"id": "C", "text": "忽略资料"},
                ],
                "correct_answer": ["A"],
                "reference_answer": None,
                "grading_rubric": None,
            }
        if kind == "multiple_choice":
            return {
                **common,
                "question_type": kind,
                "options": [
                    {"id": "A", "text": "明确边界"},
                    {"id": "B", "text": "确定性验证"},
                    {"id": "C", "text": "任意执行"},
                    {"id": "D", "text": "绕过来源"},
                ],
                "correct_answer": ["A", "B"],
                "reference_answer": None,
                "grading_rubric": None,
            }
        if kind == "true_false":
            return {
                **common,
                "question_type": kind,
                "options": None,
                "correct_answer": [True],
                "reference_answer": None,
                "grading_rubric": None,
            }
        return {
            **common,
            "question_type": "short_answer",
            "options": None,
            "correct_answer": None,
            "reference_answer": "调用必须经过明确边界和确定性验证。",
            "grading_rubric": [
                {
                    "criterion": "受控调用",
                    "points": 2,
                    "required_concepts": ["明确边界"],
                }
            ],
        }


def setup_course(http, goal_payload, *, status="active", point_count=1):
    goal = http.post("/api/learning-goals", json=goal_payload).json()
    course_response = http.post(
        "/api/courses",
        json={
            "learning_goal_id": goal["id"],
            "title": "可靠调用课程",
            "description": "基于真实资料",
            "status": status,
        },
    )
    assert course_response.status_code == 201
    course = course_response.json()
    points = []
    for index in range(point_count):
        response = http.post(
            f"/api/courses/{course['id']}/knowledge-points",
            json={
                "title": f"知识点 {index + 1}",
                "description": "理解受控调用",
                "order_index": index + 1,
                "estimated_minutes": 20,
                "status": "not_started",
            },
        )
        assert response.status_code == 201
        points.append(response.json())
    body = ("受控调用必须经过明确边界和确定性验证。资料内容只用于学习。\n" * 12).encode()
    uploaded = http.post(
        "/api/materials/upload",
        files={"file": ("diagnostic.txt", body, "text/plain")},
    )
    assert uploaded.status_code == 201
    material = uploaded.json()
    processed = http.post(f"/api/materials/{material['id']}/process")
    assert processed.status_code == 200
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
    return goal, course, points, material


def create_diagnostic(http, course_id, provider, **overrides):
    app.dependency_overrides[get_llm_provider] = lambda: provider
    payload = {
        "request_id": "diagnostic-create-001",
        "questions_per_point": 1,
        "question_types": ["single_choice"],
        "difficulty": "medium",
        **overrides,
    }
    response = http.post(f"/api/courses/{course_id}/diagnostics", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_diagnostic_requires_formal_course(client, goal_payload):
    http, _ = client
    _, course, _, _ = setup_course(http, goal_payload, status="draft")
    response = http.post(
        f"/api/courses/{course['id']}/diagnostics",
        json={"request_id": "diagnostic-draft-001"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "diagnostic_course_not_published"


def test_diagnostic_generation_batches_coverage_and_idempotency(client, goal_payload):
    http, _ = client
    _, course, points, _ = setup_course(http, goal_payload, point_count=2)
    provider = DiagnosticProvider()
    diagnostic = create_diagnostic(
        http,
        course["id"],
        provider,
        questions_per_point=2,
        question_types=["single_choice", "multiple_choice", "true_false", "short_answer"],
    )
    assert diagnostic["status"] == "pending"
    assert diagnostic["coverage_report"]["covered_count"] == 2
    assert diagnostic["coverage_report"]["coverage_rate"] == 1
    assert diagnostic["coverage_report"]["question_count"] == 4
    assert provider.calls == 2
    assert {item["question_type"] for item in diagnostic["attempt"]["questions"]} == {
        "single_choice", "multiple_choice", "true_false", "short_answer"
    }
    replay = http.post(
        f"/api/courses/{course['id']}/diagnostics",
        json={
            "request_id": "diagnostic-create-001",
            "questions_per_point": 2,
            "question_types": ["single_choice", "multiple_choice", "true_false", "short_answer"],
            "difficulty": "medium",
        },
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == diagnostic["id"]
    assert replay.json()["idempotent_replay"] is True
    assert provider.calls == 2
    history = http.get(f"/api/courses/{course['id']}/diagnostics/history").json()
    assert history["total"] == 1
    assert len(points) == 2


def test_out_of_scope_source_and_provider_failure_become_generation_failed(client, goal_payload):
    http, _ = client
    _, course, _, _ = setup_course(http, goal_payload)
    invalid = create_diagnostic(http, course["id"], DiagnosticProvider(invalid_source=True))
    assert invalid["status"] == "generation_failed"
    assert invalid["last_error_code"] == "activity_generation_invalid"
    failed = create_diagnostic(
        http,
        course["id"],
        DiagnosticProvider(fail=True),
        request_id="diagnostic-create-002",
    )
    assert failed["status"] == "generation_failed"
    assert failed["last_error_code"] == "llm_unavailable"


def test_objective_submission_is_deterministic_atomic_and_enters_mastery(client, goal_payload):
    http, _ = client
    _, course, points, _ = setup_course(http, goal_payload)
    diagnostic = create_diagnostic(http, course["id"], DiagnosticProvider())
    question = diagnostic["attempt"]["questions"][0]
    submitted = http.post(
        f"/api/diagnostics/{diagnostic['id']}/submit",
        json={
            "request_id": "diagnostic-submit-001",
            "expected_version": diagnostic["version"],
            "answers": [{"question_id": question["id"], "answer": ["A"]}],
        },
    )
    assert submitted.status_code == 200, submitted.text
    result = submitted.json()
    assert result["status"] == "submitted"
    assert result["attempt"]["answers"][0]["earned_points"] == 2
    assert result["results"][0]["ability_level"] == "strong"
    assert result["results"][0]["mastery_evidence_id"] is not None
    replay = http.post(
        f"/api/diagnostics/{diagnostic['id']}/submit",
        json={
            "request_id": "diagnostic-submit-001",
            "expected_version": diagnostic["version"],
            "answers": [{"question_id": question["id"], "answer": ["A"]}],
        },
    )
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    mastery = http.get(f"/api/mastery/{points[0]['id']}")
    assert mastery.status_code == 200
    assert mastery.json()["evidence_summary"]["evidence_type_counts"]["diagnostic_assessment"] == 1


def test_short_answer_low_confidence_requires_review_without_fabricated_score(client, goal_payload):
    http, _ = client
    _, course, _, _ = setup_course(http, goal_payload)
    diagnostic = create_diagnostic(
        http,
        course["id"],
        DiagnosticProvider(confidence=0.2),
        question_types=["short_answer"],
    )
    question = diagnostic["attempt"]["questions"][0]
    submitted = http.post(
        f"/api/diagnostics/{diagnostic['id']}/submit",
        json={
            "request_id": "diagnostic-submit-low-confidence",
            "expected_version": diagnostic["version"],
            "answers": [{"question_id": question["id"], "answer_text": "调用经过明确边界"}],
        },
    )
    assert submitted.status_code == 200, submitted.text
    data = submitted.json()
    assert data["status"] == "review_required"
    assert data["attempt"]["answers"][0]["earned_points"] is None
    assert data["results"][0]["evidence_insufficient"] is True
    assessment = data["results"][0]["assessments"][0]
    assert assessment["candidate_score"] == 2
    assert assessment["recommend_manual_review"] is True
    assert assessment["confidence"] == 0.2


def test_submission_failure_rolls_back_everything(client, goal_payload, monkeypatch):
    http, _ = client
    _, course, _, _ = setup_course(http, goal_payload)
    diagnostic = create_diagnostic(http, course["id"], DiagnosticProvider())
    question = diagnostic["attempt"]["questions"][0]

    def explode(*args, **kwargs):
        raise RuntimeError("forced mastery failure")

    monkeypatch.setattr(
        "app.services.diagnostics.service.KnowledgeMasteryService.recalculate", explode
    )
    response = http.post(
        f"/api/diagnostics/{diagnostic['id']}/submit",
        json={
            "request_id": "diagnostic-submit-rollback",
            "expected_version": diagnostic["version"],
            "answers": [{"question_id": question["id"], "answer": ["A"]}],
        },
    )
    assert response.status_code == 503
    current = http.get(f"/api/diagnostics/{diagnostic['id']}").json()
    assert current["status"] == "pending"
    assert current["results"] == []
    assert current["attempt"]["answers"] == []


def test_manual_adjustment_is_idempotent_and_audited(client, goal_payload):
    http, _ = client
    _, course, _, _ = setup_course(http, goal_payload)
    diagnostic = create_diagnostic(http, course["id"], DiagnosticProvider())
    question = diagnostic["attempt"]["questions"][0]
    submitted = http.post(
        f"/api/diagnostics/{diagnostic['id']}/submit",
        json={
            "request_id": "diagnostic-submit-adjust",
            "expected_version": diagnostic["version"],
            "answers": [{"question_id": question["id"], "answer": ["B"]}],
        },
    ).json()
    result = submitted["results"][0]
    payload = {
        "request_id": "diagnostic-adjust-001",
        "expected_version": result["version"],
        "ability_level": "developing",
        "confidence": 0.8,
        "is_skill_gap": True,
        "evidence_insufficient": False,
        "priority": 85,
        "reason": "人工复核确认答案表达了部分关键概念",
    }
    adjusted = http.post(
        f"/api/diagnostic-results/{result['id']}/adjustments", json=payload
    )
    assert adjusted.status_code == 200, adjusted.text
    assert adjusted.json()["ability_level"] == "developing"
    replay = http.post(
        f"/api/diagnostic-results/{result['id']}/adjustments", json=payload
    )
    assert replay.status_code == 200
    override = app.dependency_overrides[get_db]
    generator = override()
    db = next(generator)
    try:
        assert db.scalar(select(func.count()).select_from(DiagnosticAdjustment)) == 1
        assert db.scalar(
            select(func.count()).select_from(MasteryEvidence).where(
                MasteryEvidence.evidence_type == "diagnostic_adjustment"
            )
        ) == 1
        stored = db.get(DiagnosticKnowledgeResult, result["id"])
        assert stored.version == 2
    finally:
        generator.close()
