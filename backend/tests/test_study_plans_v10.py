from contextlib import contextmanager
from datetime import date, datetime, timezone

from sqlalchemy import func, select

from app.db.session import get_db
from app.main import app
from app.models import (
    DailyTask,
    DiagnosticKnowledgeResult,
    DiagnosticSession,
    KnowledgeMastery,
    KnowledgePoint,
    KnowledgePointPrerequisite,
    ReviewSchedule,
    StudyPlanItem,
    StudyPlanVersion,
)


@contextmanager
def db_session():
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        yield db
    finally:
        generator.close()


def setup_course(http, goal_payload, *, minutes=(20, 20), titles=None):
    goal = http.post("/api/learning-goals", json=goal_payload).json()
    course_response = http.post(
        "/api/courses",
        json={
            "learning_goal_id": goal["id"],
            "title": "诊断驱动学习课程",
            "description": "用于计划生成测试",
            "status": "active",
        },
    )
    assert course_response.status_code == 201, course_response.text
    course = course_response.json()
    titles = titles or [f"知识点 {index + 1}" for index in range(len(minutes))]
    points = []
    for index, point_minutes in enumerate(minutes):
        response = http.post(
            f"/api/courses/{course['id']}/knowledge-points",
            json={
                "title": titles[index],
                "description": "计划范围内的正式知识点",
                "order_index": index + 1,
                "estimated_minutes": point_minutes,
                "status": "not_started",
            },
        )
        assert response.status_code == 201, response.text
        points.append(response.json())
    return goal, course, points


def add_prerequisite(prerequisite_id, dependent_id):
    with db_session() as db:
        db.add(
            KnowledgePointPrerequisite(
                prerequisite_knowledge_point_id=prerequisite_id,
                dependent_knowledge_point_id=dependent_id,
                relation_type="prerequisite",
                source="test",
            )
        )
        db.commit()


def plan_payload(goal, course, **overrides):
    return {
        "request_id": "study-plan-create-001",
        "learning_goal_id": goal["id"],
        "course_id": course["id"],
        "start_date": "2026-08-03",
        "target_date": "2026-08-07",
        "daily_minutes": 20,
        "available_weekdays": [0, 1, 2, 3, 4],
        "allow_weekends": False,
        "intensity": "standard",
        "include_due_reviews": True,
        "use_latest_diagnostic": True,
        "use_existing_mastery": True,
        **overrides,
    }


def create_plan(http, goal, course, **overrides):
    response = http.post("/api/study-plans", json=plan_payload(goal, course, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


def test_plan_respects_prerequisites_dates_budget_and_generation_idempotency(
    client, goal_payload
):
    http, _ = client
    goal, course, points = setup_course(http, goal_payload, minutes=(20, 20, 20))
    add_prerequisite(points[0]["id"], points[1]["id"])

    plan = create_plan(http, goal, course, target_date="2026-08-05")

    assert plan["status"] == "ready"
    version = plan["latest_version"]
    assert version["quality_report"] == {
        "prerequisite_constraint_rate": 1.0,
        "available_date_constraint_rate": 1.0,
        "duplicate_task_count": 0,
        "uncovered_required_knowledge_point_ids": [],
        "time_budget_constraint_rate": 1.0,
    }
    dates = {item["knowledge_point_id"]: item["scheduled_date"] for item in version["items"]}
    assert dates[points[0]["id"]] <= dates[points[1]["id"]]
    totals = {}
    for item in version["items"]:
        assert date.fromisoformat(item["scheduled_date"]).weekday() in {0, 1, 2}
        totals[item["scheduled_date"]] = totals.get(item["scheduled_date"], 0) + item[
            "estimated_minutes"
        ]
    assert all(total <= 20 for total in totals.values())

    replay = http.post(
        "/api/study-plans", json=plan_payload(goal, course, target_date="2026-08-05")
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == plan["id"]
    assert replay.json()["idempotent_replay"] is True


def test_diagnostic_gap_is_prioritized_within_prerequisite_safe_order(client, goal_payload):
    http, _ = client
    goal, course, points = setup_course(
        http, goal_payload, minutes=(20, 20), titles=["普通知识点", "诊断缺口"]
    )
    with db_session() as db:
        session = DiagnosticSession(
            public_id="diagnostic-plan-priority",
            course_id=course["id"],
            status="submitted",
            generation_request_id="diagnostic-plan-priority-request",
            generation_config_hash="a" * 64,
            course_snapshot_hash="b" * 64,
            prompt_version="test-v1",
            coverage_report={},
            generation_metrics={},
            submitted_at=datetime(2026, 8, 1, 5, 0, tzinfo=timezone.utc),
        )
        db.add(session)
        db.flush()
        db.add_all(
            [
                DiagnosticKnowledgeResult(
                    diagnostic_session_id=session.id,
                    knowledge_point_id=points[0]["id"],
                    answered_count=1,
                    graded_count=1,
                    earned_points=2,
                    possible_points=2,
                    score_percentage=100,
                    confidence=1,
                    ability_level="strong",
                    is_skill_gap=False,
                    evidence_insufficient=False,
                    priority=10,
                    reason="已掌握",
                    evidence_answer_ids=[],
                    evidence_source_ids=[],
                ),
                DiagnosticKnowledgeResult(
                    diagnostic_session_id=session.id,
                    knowledge_point_id=points[1]["id"],
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
                    reason="初始诊断识别为缺口",
                    evidence_answer_ids=[],
                    evidence_source_ids=[],
                ),
            ]
        )
        db.commit()

    plan = create_plan(http, goal, course, daily_minutes=60, target_date="2026-08-04")
    items = plan["latest_version"]["items"]
    assert items[0]["knowledge_point_id"] == points[1]["id"]
    assert "技能缺口" in items[0]["scheduling_reason"]
    assert sum(
        item["estimated_minutes"]
        for item in items
        if item["knowledge_point_id"] == points[1]["id"]
    ) == 30


def test_strong_mastery_shortens_learning_and_due_review_is_included(client, goal_payload):
    http, _ = client
    goal, course, points = setup_course(http, goal_payload, minutes=(60,))
    with db_session() as db:
        db.add(
            KnowledgeMastery(
                knowledge_point_id=points[0]["id"],
                mastery_score=92,
                confidence_score=85,
                mastery_level="strong",
                evidence_count=4,
                algorithm_version="test-v1",
                calculated_at=datetime(2026, 8, 1, 4, 0, tzinfo=timezone.utc),
            )
        )
        db.add(
            ReviewSchedule(
                knowledge_point_id=points[0]["id"],
                status="pending",
                priority_score=90,
                recommended_at=datetime(2026, 8, 1, 4, 0, tzinfo=timezone.utc),
                due_at=datetime(2026, 8, 4, 4, 0, tzinfo=timezone.utc),
                reason_code="confidence_decay",
                reason_summary="到期复习以确认保持程度",
            )
        )
        db.commit()

    plan = create_plan(http, goal, course, daily_minutes=30)
    items = plan["latest_version"]["items"]
    quick = next(item for item in items if item["activity_type"] == "quick_verify")
    review = next(item for item in items if item["activity_type"] == "review")
    assert quick["estimated_minutes"] == 10
    assert review["is_due_review"] is True
    assert review["review_schedule_id"] is not None


def test_infeasible_plan_explains_capacity_gap_and_cannot_publish(client, goal_payload):
    http, _ = client
    goal, course, _ = setup_course(http, goal_payload, minutes=(100,))
    plan = create_plan(http, goal, course, target_date="2026-08-04")

    assert plan["status"] == "infeasible"
    version = plan["latest_version"]
    assert version["required_minutes"] == 100
    assert version["available_minutes"] == 40
    assert version["gap_minutes"] == 60
    assert {item["code"] for item in version["conflicts"]} == {"total_time_insufficient"}
    assert {item["action"] for item in version["suggestions"]} >= {
        "extend_target_date",
        "increase_daily_minutes",
    }
    publish = http.post(
        f"/api/study-plans/{plan['id']}/publish",
        json={"request_id": "study-plan-publish-infeasible", "expected_version": 1, "confirmed": True},
    )
    assert publish.status_code == 409
    assert publish.json()["error"]["code"] == "study_plan_not_publishable"


def test_existing_dependent_task_before_prerequisite_is_rejected_by_quality_gate(
    client, goal_payload
):
    http, _ = client
    goal, course, points = setup_course(http, goal_payload, minutes=(20, 20))
    add_prerequisite(points[0]["id"], points[1]["id"])
    with db_session() as db:
        db.add(
            DailyTask(
                learning_goal_id=goal["id"],
                course_id=course["id"],
                knowledge_point_id=points[1]["id"],
                title="已有的后置知识点任务",
                task_type="learn",
                estimated_minutes=20,
                scheduled_date=date(2026, 8, 3),
                status="pending",
            )
        )
        db.commit()

    plan = create_plan(http, goal, course, target_date="2026-08-04")
    assert plan["status"] == "infeasible"
    assert plan["latest_version"]["quality_report"]["prerequisite_constraint_rate"] < 1
    assert "prerequisite_order_violation" in {
        conflict["code"] for conflict in plan["latest_version"]["conflicts"]
    }


def test_publish_is_atomic_and_idempotent_and_replan_preserves_execution_truth(
    client, goal_payload
):
    http, _ = client
    goal, course, _ = setup_course(http, goal_payload, minutes=(20, 20))
    plan = create_plan(http, goal, course)
    publish_payload = {
        "request_id": "study-plan-publish-001",
        "expected_version": plan["version"],
        "confirmed": True,
    }
    published = http.post(
        f"/api/study-plans/{plan['id']}/publish", json=publish_payload
    )
    assert published.status_code == 200, published.text
    published_data = published.json()
    assert published_data["plan"]["status"] == "active"
    assert len(published_data["created_task_ids"]) == 2
    assert len(set(published_data["created_task_ids"])) == 2

    replay = http.post(f"/api/study-plans/{plan['id']}/publish", json=publish_payload)
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    with db_session() as db:
        assert db.scalar(select(func.count()).select_from(DailyTask)) == 2
        tasks = list(db.scalars(select(DailyTask).order_by(DailyTask.id)))
        tasks[0].status = "completed"
        completed_task_id = tasks[0].id
        pending_task_id = tasks[1].id
        db.commit()

    active_plan = published_data["plan"]
    replanned = http.post(
        f"/api/study-plans/{plan['id']}/replan",
        json={
            "request_id": "study-plan-replan-001",
            "expected_version": active_plan["version"],
            "reason": "可用时间发生变化，需要移动未完成任务",
            "daily_minutes": 40,
            "target_date": "2026-08-10",
        },
    )
    assert replanned.status_code == 200, replanned.text
    replanned_data = replanned.json()
    assert replanned_data["status"] == "active"
    assert replanned_data["active_version_number"] == 1
    assert replanned_data["current_version_number"] == 2
    assert all(
        item["daily_task_id"] != completed_task_id
        for item in replanned_data["latest_version"]["items"]
    )
    assert pending_task_id in {
        item["daily_task_id"] for item in replanned_data["latest_version"]["items"]
    }

    republished = http.post(
        f"/api/study-plans/{plan['id']}/publish",
        json={
            "request_id": "study-plan-publish-002",
            "expected_version": replanned_data["version"],
            "confirmed": True,
        },
    )
    assert republished.status_code == 200, republished.text
    assert republished.json()["plan"]["active_version_number"] == 2
    history = http.get(f"/api/study-plans/{plan['id']}/versions").json()
    assert [version["status"] for version in history["items"]] == ["active", "superseded"]
    with db_session() as db:
        assert db.get(DailyTask, completed_task_id).status == "completed"
        assert db.scalar(select(func.count()).select_from(DailyTask)) == 2


def test_publish_failure_rolls_back_tasks_and_plan_state(client, goal_payload, monkeypatch):
    http, _ = client
    goal, course, _ = setup_course(http, goal_payload, minutes=(20, 20))
    plan = create_plan(http, goal, course)
    original = __import__(
        "app.services.study_plans.service", fromlist=["StudyPlanService"]
    ).StudyPlanService._create_daily_task
    calls = {"count": 0}

    def fail_on_second(self, item):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("forced publication failure")
        return original(self, item)

    monkeypatch.setattr(
        "app.services.study_plans.service.StudyPlanService._create_daily_task", fail_on_second
    )
    response = http.post(
        f"/api/study-plans/{plan['id']}/publish",
        json={
            "request_id": "study-plan-publish-rollback",
            "expected_version": plan["version"],
            "confirmed": True,
        },
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "study_plan_publish_failed"
    current = http.get(f"/api/study-plans/{plan['id']}").json()
    assert current["status"] == "ready"
    assert current["active_version_number"] is None
    with db_session() as db:
        assert db.scalar(select(func.count()).select_from(DailyTask)) == 0
        version = db.scalar(select(StudyPlanVersion))
        assert version.publish_request_id is None
        assert db.scalar(
            select(func.count()).select_from(StudyPlanItem).where(StudyPlanItem.daily_task_id.is_not(None))
        ) == 0


def test_course_change_makes_preview_stale_and_blocks_publication(client, goal_payload):
    http, _ = client
    goal, course, points = setup_course(http, goal_payload, minutes=(20,))
    plan = create_plan(http, goal, course)
    with db_session() as db:
        point = db.get(KnowledgePoint, points[0]["id"])
        point.title = "课程内容已经更新"
        db.commit()

    response = http.post(
        f"/api/study-plans/{plan['id']}/publish",
        json={
            "request_id": "study-plan-publish-stale",
            "expected_version": plan["version"],
            "confirmed": True,
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "study_plan_source_stale"
    with db_session() as db:
        assert db.scalar(select(func.count()).select_from(DailyTask)) == 0
