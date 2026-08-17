from contextlib import contextmanager
from datetime import date, datetime, timezone

from sqlalchemy import func, select

from app.db.session import get_db
from app.main import app
from app.models import (
    DailyTask,
    DiagnosticKnowledgeResult,
    DiagnosticSession,
    LearningSession,
    NextActionAcceptance,
    ReviewSchedule,
)


@contextmanager
def db_session():
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        yield db
    finally:
        generator.close()


def setup_course(http, goal_payload, *, minutes=(20,), status="active"):
    goal = http.post("/api/learning-goals", json=goal_payload).json()
    course_response = http.post(
        "/api/courses",
        json={
            "learning_goal_id": goal["id"],
            "title": "下一步推荐课程",
            "description": "确定性推荐测试",
            "status": status,
        },
    )
    assert course_response.status_code == 201
    course = course_response.json()
    points = []
    for index, point_minutes in enumerate(minutes):
        response = http.post(
            f"/api/courses/{course['id']}/knowledge-points",
            json={
                "title": f"知识点 {index + 1}",
                "description": "可执行知识点",
                "order_index": index + 1,
                "estimated_minutes": point_minutes,
                "status": "not_started",
            },
        )
        assert response.status_code == 201
        points.append(response.json())
    return goal, course, points


def add_pending_diagnostic(course_id, *, status="pending"):
    with db_session() as db:
        diagnostic = DiagnosticSession(
            public_id=f"next-action-diagnostic-{status}",
            course_id=course_id,
            status=status,
            generation_request_id=f"next-action-diagnostic-request-{status}",
            generation_config_hash="a" * 64,
            course_snapshot_hash="b" * 64,
            prompt_version="test-v1",
            coverage_report={},
            generation_metrics={},
            submitted_at=(
                datetime(2026, 8, 1, 3, 0, tzinfo=timezone.utc)
                if status != "pending"
                else None
            ),
        )
        db.add(diagnostic)
        db.commit()
        return diagnostic.id


def add_due_review(point_id):
    with db_session() as db:
        review = ReviewSchedule(
            knowledge_point_id=point_id,
            status="pending",
            priority_score=95,
            recommended_at=datetime(2026, 7, 30, 4, 0, tzinfo=timezone.utc),
            due_at=datetime(2026, 7, 31, 4, 0, tzinfo=timezone.utc),
            reason_code="low_mastery",
            reason_summary="薄弱知识点需要及时巩固",
        )
        db.add(review)
        db.commit()
        return review.id


def test_active_session_has_highest_priority_and_accept_is_non_destructive_and_idempotent(
    client, goal_payload
):
    http, _ = client
    goal, course, points = setup_course(http, goal_payload)
    add_pending_diagnostic(course["id"])
    add_due_review(points[0]["id"])
    with db_session() as db:
        task = DailyTask(
            learning_goal_id=goal["id"],
            course_id=course["id"],
            knowledge_point_id=points[0]["id"],
            title="进行中的学习",
            task_type="learn",
            estimated_minutes=20,
            scheduled_date=date(2026, 8, 1),
            status="in_progress",
        )
        db.add(task)
        db.flush()
        session = LearningSession(
            learning_goal_id=goal["id"],
            course_id=course["id"],
            knowledge_point_id=points[0]["id"],
            daily_task_id=task.id,
            started_at=datetime(2026, 8, 1, 4, 0, tzinfo=timezone.utc),
            status="active",
            notes="保留现场",
        )
        db.add(session)
        db.commit()
        task_id, session_id = task.id, session.id

    first = http.get("/api/next-learning-action")
    second = http.get("/api/next-learning-action")
    assert first.status_code == 200
    action = first.json()
    assert action["action_type"] == "resume_session"
    assert action["target_id"] == session_id
    assert action["priority"] == 100
    assert second.json()["reason"] == action["reason"]
    assert second.json()["action_signature"] == action["action_signature"]

    payload = {
        "request_id": "next-action-accept-session",
        "action_signature": action["action_signature"],
    }
    accepted = http.post("/api/next-learning-action/accept", json=payload)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["learning_session_id"] == session_id
    replay = http.post("/api/next-learning-action/accept", json=payload)
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    with db_session() as db:
        assert db.get(DailyTask, task_id).status == "in_progress"
        assert db.get(LearningSession, session_id).status == "active"
        assert db.scalar(select(func.count()).select_from(NextActionAcceptance)) == 1


def test_unfinished_diagnostic_precedes_due_review_without_changing_diagnostic(client, goal_payload):
    http, _ = client
    _, course, points = setup_course(http, goal_payload)
    diagnostic_id = add_pending_diagnostic(course["id"])
    add_due_review(points[0]["id"])

    action = http.get("/api/next-learning-action").json()
    assert action["action_type"] == "complete_assessment"
    assert action["target_id"] == diagnostic_id
    accepted = http.post(
        "/api/next-learning-action/accept",
        json={
            "request_id": "next-action-accept-diagnostic",
            "action_signature": action["action_signature"],
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["outcome_kind"] == "diagnostic_session"
    with db_session() as db:
        assert db.get(DiagnosticSession, diagnostic_id).status == "pending"
        assert db.scalar(select(func.count()).select_from(DailyTask)) == 0


def test_due_review_accept_creates_existing_execution_objects_without_fake_completion(
    client, goal_payload
):
    http, _ = client
    _, _, points = setup_course(http, goal_payload)
    review_id = add_due_review(points[0]["id"])
    action = http.get("/api/next-learning-action").json()
    assert action["action_type"] == "review"
    assert action["target_kind"] == "review_schedule"
    assert action["target_id"] == review_id
    assert action["is_due_review"] is True

    payload = {
        "request_id": "next-action-accept-review",
        "action_signature": action["action_signature"],
    }
    accepted = http.post("/api/next-learning-action/accept", json=payload)
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["outcome_kind"] == "learning_session"
    assert body["daily_task_id"] is not None
    assert body["learning_session_id"] is not None
    replay = http.post("/api/next-learning-action/accept", json=payload)
    assert replay.json()["idempotent_replay"] is True
    with db_session() as db:
        task = db.get(DailyTask, body["daily_task_id"])
        review = db.get(ReviewSchedule, review_id)
        assert task.status == "in_progress"
        assert task.task_type == "review"
        assert review.status == "pending"
        assert db.scalar(select(func.count()).select_from(DailyTask)) == 1
        assert db.scalar(select(func.count()).select_from(LearningSession)) == 1


def test_today_formal_plan_action_respects_available_time_and_links_plan(client, goal_payload):
    http, _ = client
    goal, course, _ = setup_course(http, goal_payload, minutes=(20,))
    created = http.post(
        "/api/study-plans",
        json={
            "request_id": "next-action-plan-create",
            "learning_goal_id": goal["id"],
            "course_id": course["id"],
            "start_date": "2026-08-01",
            "target_date": "2026-08-02",
            "daily_minutes": 20,
            "available_weekdays": [5, 6],
            "allow_weekends": True,
            "intensity": "standard",
            "include_due_reviews": True,
            "use_latest_diagnostic": True,
            "use_existing_mastery": True,
        },
    )
    assert created.status_code == 201, created.text
    plan = created.json()
    published = http.post(
        f"/api/study-plans/{plan['id']}/publish",
        json={
            "request_id": "next-action-plan-publish",
            "expected_version": plan["version"],
            "confirmed": True,
        },
    )
    assert published.status_code == 200, published.text

    action = http.get("/api/next-learning-action?available_minutes=20").json()
    assert action["reason_code"] == "today_formal_plan"
    assert action["from_formal_plan"] is True
    assert action["plan_id"] == plan["id"]
    assert action["plan_item_id"] is not None
    short_window = http.get("/api/next-learning-action?available_minutes=10").json()
    assert short_window["action_type"] == "replan_required"
    assert short_window["reason_code"] == "no_executable_action"


def test_skill_gap_reason_is_stable_and_accept_creates_one_task_and_session(
    client, goal_payload
):
    http, _ = client
    _, course, points = setup_course(http, goal_payload)
    diagnostic_id = add_pending_diagnostic(course["id"], status="submitted")
    with db_session() as db:
        db.add(
            DiagnosticKnowledgeResult(
                diagnostic_session_id=diagnostic_id,
                knowledge_point_id=points[0]["id"],
                answered_count=1,
                graded_count=1,
                earned_points=0,
                possible_points=2,
                score_percentage=0,
                confidence=1,
                ability_level="beginner",
                is_skill_gap=True,
                evidence_insufficient=False,
                priority=95,
                reason="诊断确认缺口",
                evidence_answer_ids=[],
                evidence_source_ids=[],
            )
        )
        db.commit()

    action = http.get("/api/next-learning-action").json()
    assert action["reason_code"] == "diagnostic_skill_gap"
    assert action["target_kind"] == "knowledge_point"
    assert action["knowledge_point_id"] == points[0]["id"]
    assert http.get("/api/next-learning-action").json()["reason"] == action["reason"]
    accepted = http.post(
        "/api/next-learning-action/accept",
        json={
            "request_id": "next-action-accept-gap",
            "action_signature": action["action_signature"],
        },
    )
    assert accepted.status_code == 200, accepted.text
    with db_session() as db:
        assert db.scalar(select(func.count()).select_from(DailyTask)) == 1
        assert db.scalar(select(func.count()).select_from(LearningSession)) == 1
        task = db.scalar(select(DailyTask))
        assert task.status == "in_progress"
    assert http.get("/api/next-learning-action").json()["action_type"] == "resume_session"


def test_empty_state_requests_replan_and_old_signature_is_rejected(client, goal_payload):
    http, _ = client
    original = http.get("/api/next-learning-action").json()
    assert original["action_type"] == "replan_required"
    assert original["target_id"] is None

    http.post("/api/learning-goals", json=goal_payload)
    stale = http.post(
        "/api/next-learning-action/accept",
        json={
            "request_id": "next-action-accept-stale",
            "action_signature": original["action_signature"],
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "next_action_stale"
    with db_session() as db:
        assert db.scalar(select(func.count()).select_from(NextActionAcceptance)) == 0


def test_agent_uses_controlled_next_action_read_tool(client):
    http, _ = client
    conversation = http.post(
        "/api/agent/conversations", json={"title": "下一步建议"}
    ).json()
    run = http.post(
        f"/api/agent/conversations/{conversation['id']}/runs",
        json={"input": "我下一步应该学什么？", "request_id": "agent-next-action-001"},
    )
    assert run.status_code == 202, run.text
    body = run.json()
    assert body["status"] == "completed"
    assert body["tool_calls"][0]["tool_name"] == "get_next_learning_action"
    assert body["tool_calls"][0]["tool_kind"] == "read"
    assert body["confirmation"] is None
