from datetime import date
from io import BytesIO

from app.api.deps import get_llm_provider
from app.main import app
from tests.fakes import FakeLearningLLM


class InvalidSourceLearningLLM(FakeLearningLLM):
    def generate_structured(self, **kwargs):
        result = super().generate_structured(**kwargs)
        if kwargs["schema"].__name__ == "GeneratedActivity":
            result.value.questions[0].cited_source_ids = ["S999"]
        return result


class RepairingSourceLearningLLM(FakeLearningLLM):
    def generate_structured(self, **kwargs):
        result = super().generate_structured(**kwargs)
        if kwargs["schema"].__name__ == "GeneratedActivity" and self.calls == 1:
            result.value.questions[0].cited_source_ids = ["S999"]
        return result


def prepare_context(client):
    http, _ = client
    goal = http.post(
        "/api/learning-goals",
        json={
            "title": "学习 MCP",
            "description": "",
            "target_date": None,
            "daily_minutes": 30,
            "current_level": "入门",
            "status": "active",
        },
    ).json()
    course = http.post(
        "/api/courses",
        json={
            "learning_goal_id": goal["id"],
            "title": "MCP 基础",
            "description": "Tools Resources Prompts",
            "status": "active",
        },
    ).json()
    point = http.post(
        f"/api/courses/{course['id']}/knowledge-points",
        json={
            "title": "控制方向",
            "description": "Tools 和 Resources 的差异",
            "order_index": 0,
            "estimated_minutes": 20,
            "status": "learning",
        },
    ).json()
    text = (
        "MCP 核心原语包括 Tools、Resources 和 Prompts。"
        "Tools 由模型主动调用。Resources 是由应用控制并提供上下文的数据。"
        "Prompts 是可复用的交互模板。"
    ) * 8
    material = http.post(
        "/api/materials/upload",
        files={"file": ("mcp.txt", BytesIO(text.encode("utf-8")), "text/plain")},
    ).json()
    processed = http.post(f"/api/materials/{material['id']}/process")
    assert processed.status_code == 200, processed.text
    return course, point, material


def generate(http, course, point, material, request_id="activity-request-1"):
    return http.post(
        "/api/learning-activities/generate",
        json={
            "title": "MCP 控制方向测验",
            "course_id": course["id"],
            "knowledge_point_id": point["id"],
            "material_ids": [material["id"]],
            "question_types": [
                "single_choice",
                "multiple_choice",
                "true_false",
                "short_answer",
            ],
            "question_count": 4,
            "difficulty": "mixed",
            "request_id": request_id,
        },
    )


def test_activity_generation_lifecycle_grading_and_review(client):
    http, _ = client
    fake = FakeLearningLLM()
    app.dependency_overrides[get_llm_provider] = lambda: fake
    course, point, material = prepare_context(client)

    generated_response = generate(http, course, point, material)
    assert generated_response.status_code == 201, generated_response.text
    draft = generated_response.json()
    assert draft["status"] == "draft"
    assert len(draft["questions"]) == 4
    assert all(question["sources"] for question in draft["questions"])
    assert draft["questions"][0]["correct_answer"] == ["A"]

    replay = generate(http, course, point, material)
    assert replay.status_code == 201
    assert replay.json()["id"] == draft["id"]
    conflict = http.post(
        "/api/learning-activities/generate",
        json={
            "title": "不同配置",
            "material_ids": [material["id"]],
            "question_types": ["single_choice"],
            "question_count": 1,
            "difficulty": "easy",
            "request_id": "activity-request-1",
        },
    )
    assert conflict.status_code == 409

    published = http.post(
        f"/api/learning-activities/{draft['id']}/publish"
    ).json()
    assert published["status"] == "published"
    assert all(question["correct_answer"] is None for question in published["questions"])

    task = http.post(
        "/api/daily-tasks",
        json={
            "learning_goal_id": course["learning_goal_id"],
            "course_id": course["id"],
            "knowledge_point_id": point["id"],
            "activity_id": draft["id"],
            "title": "完成 MCP 测验",
            "estimated_minutes": 20,
            "scheduled_date": date.today().isoformat(),
        },
    ).json()
    session = http.post(
        "/api/learning-sessions",
        json={
            "learning_goal_id": course["learning_goal_id"],
            "course_id": course["id"],
            "knowledge_point_id": point["id"],
            "daily_task_id": task["id"],
        },
    ).json()
    started = http.post(
        f"/api/learning-activities/{draft['id']}/attempts",
        json={"learning_session_id": session["id"]},
    )
    assert started.status_code == 201
    attempt = started.json()
    assert attempt["status"] == "in_progress"
    serialized = str(attempt)
    assert "correct_answer" not in serialized
    assert "grading_rubric" not in serialized
    by_type = {item["question_type"]: item for item in attempt["questions"]}

    saved = http.put(
        f"/api/quiz-attempts/{attempt['id']}/answers/{by_type['single_choice']['id']}",
        json={"answer": ["B"]},
    )
    assert saved.status_code == 200
    submission = {
        "request_id": "submit-request-1",
        "answers": [
            {"question_id": by_type["multiple_choice"]["id"], "answer": ["C", "A", "B"]},
            {"question_id": by_type["true_false"]["id"], "answer": [True]},
            {
                "question_id": by_type["short_answer"]["id"],
                "answer_text": "Tools 由模型主动调用，Resources 由应用控制并提供上下文。",
            },
        ],
    }
    result_response = http.post(
        f"/api/quiz-attempts/{attempt['id']}/submit", json=submission
    )
    assert result_response.status_code == 200, result_response.text
    result = result_response.json()
    assert result["status"] == "completed"
    assert result["earned_points"] == 9
    assert result["total_points"] == 11
    assert result["incorrect_count"] == 1
    short = next(
        answer for answer in result["answers"] if answer["question_type"] == "short_answer"
    )
    assert short["matched_rubric_items"] == ["工具控制方向", "资源控制方向"]
    assert short["sources"]
    assert fake.temperatures[-1] == 0.0
    assert http.get(f"/api/learning-sessions/{session['id']}").json()["status"] == "completed"
    today_task = next(
        item for item in http.get("/api/today").json()["tasks"] if item["id"] == task["id"]
    )
    assert today_task["status"] == "completed"

    replay_submit = http.post(
        f"/api/quiz-attempts/{attempt['id']}/submit", json=submission
    ).json()
    assert replay_submit["idempotent_replay"] is True
    assert http.put(
        f"/api/quiz-attempts/{attempt['id']}/answers/{by_type['single_choice']['id']}",
        json={"answer": ["A"]},
    ).status_code == 409
    changed_submission = {
        **submission,
        "answers": [
            *submission["answers"][:-1],
            {
                "question_id": by_type["short_answer"]["id"],
                "answer_text": "不同答案",
            },
        ],
    }
    assert http.post(
        f"/api/quiz-attempts/{attempt['id']}/submit", json=changed_submission
    ).status_code == 409

    wrongs = http.get("/api/wrong-answers?status=active").json()
    assert wrongs["total"] == 1
    wrong = wrongs["items"][0]
    assert wrong["error_type"] == "incorrect"
    review = http.post(
        "/api/wrong-answers/review",
        json={"wrong_answer_ids": [wrong["id"]], "request_id": "review-request-1"},
    ).json()
    review_replay = http.post(
        "/api/wrong-answers/review",
        json={"wrong_answer_ids": [wrong["id"]], "request_id": "review-request-1"},
    ).json()
    assert review_replay["id"] == review["id"]
    review_question = review["questions"][0]
    review_result = http.post(
        f"/api/quiz-attempts/{review['id']}/submit",
        json={
            "request_id": "review-submit-1",
            "answers": [
                {"question_id": review_question["id"], "answer": ["A"]}
            ],
        },
    )
    assert review_result.status_code == 200, review_result.text
    resolved = http.get(f"/api/wrong-answers/{wrong['id']}").json()
    assert resolved["status"] == "resolved"
    assert resolved["review_count"] == 1

    result_after = http.get(f"/api/quiz-attempts/{attempt['id']}").json()
    source_snapshot = result_after["answers"][0]["sources"][0]
    removed = http.delete(f"/api/materials/{material['id']}")
    assert removed.status_code == 204
    snapshot_after = http.get(f"/api/quiz-attempts/{attempt['id']}").json()
    snapshots = [
        source
        for answer in snapshot_after["answers"]
        for source in answer["sources"]
    ]
    assert snapshots
    assert all(source["original_filename"] == "mcp.txt" for source in snapshots)
    assert any(source["source_available"] is False for source in snapshots)
    assert source_snapshot["content_excerpt"]


def test_draft_editing_and_generation_failure_is_atomic(client):
    http, _ = client
    fake = FakeLearningLLM()
    app.dependency_overrides[get_llm_provider] = lambda: fake
    course, point, material = prepare_context(client)
    draft = generate(http, course, point, material, "activity-request-2").json()
    assert http.post(
        f"/api/learning-activities/{draft['id']}/attempts", json={}
    ).status_code == 409
    ids = [question["id"] for question in draft["questions"]]
    reordered = http.post(
        f"/api/learning-activities/{draft['id']}/questions/reorder",
        json={"question_ids": list(reversed(ids))},
    )
    assert reordered.status_code == 200
    assert [item["id"] for item in reordered.json()["questions"]] == list(reversed(ids))
    deleted = http.delete(
        f"/api/learning-activities/{draft['id']}/questions/{ids[0]}"
    )
    assert deleted.status_code == 200
    assert deleted.json()["question_count"] == 3

    invalid = InvalidSourceLearningLLM()
    app.dependency_overrides[get_llm_provider] = lambda: invalid
    failed = generate(http, course, point, material, "activity-request-invalid")
    assert failed.status_code == 422
    assert invalid.calls == 2
    listed = http.get("/api/learning-activities?page_size=100").json()
    assert listed["total"] == 1


def test_generation_repairs_one_invalid_batch(client):
    http, _ = client
    fake = RepairingSourceLearningLLM()
    app.dependency_overrides[get_llm_provider] = lambda: fake
    course, point, material = prepare_context(client)
    response = generate(http, course, point, material, "activity-request-repair")
    assert response.status_code == 201, response.text
    assert fake.calls == 2
    assert response.json()["status"] == "draft"


def test_short_answer_failure_is_not_zero_and_can_retry(client):
    http, _ = client
    fake = FakeLearningLLM()
    app.dependency_overrides[get_llm_provider] = lambda: fake
    course, point, material = prepare_context(client)
    draft = generate(http, course, point, material, "activity-request-3").json()
    http.post(f"/api/learning-activities/{draft['id']}/publish")
    attempt = http.post(
        f"/api/learning-activities/{draft['id']}/attempts", json={}
    ).json()
    snapshot = {question["id"]: question for question in draft["questions"]}
    answers = []
    for question in attempt["questions"]:
        original = snapshot[question["id"]]
        if question["question_type"] == "short_answer":
            answers.append(
                {
                    "question_id": question["id"],
                    "answer_text": "模型主动调用，应用控制上下文。",
                }
            )
        else:
            answers.append(
                {
                    "question_id": question["id"],
                    "answer": original["correct_answer"],
                }
            )
    payload = {"request_id": "submit-request-failure", "answers": answers}
    app.dependency_overrides[get_llm_provider] = lambda: None
    failed = http.post(
        f"/api/quiz-attempts/{attempt['id']}/submit", json=payload
    )
    assert failed.status_code == 503
    restored = http.get(f"/api/quiz-attempts/{attempt['id']}").json()
    assert restored["status"] == "failed"
    short = next(
        answer
        for answer in restored["answers"]
        if answer["question_type"] == "short_answer"
    )
    assert short["grading_status"] == "failed"
    assert short["earned_points"] is None

    app.dependency_overrides[get_llm_provider] = lambda: fake
    retried = http.post(
        f"/api/quiz-attempts/{attempt['id']}/submit", json=payload
    )
    assert retried.status_code == 200
    assert retried.json()["status"] == "completed"
