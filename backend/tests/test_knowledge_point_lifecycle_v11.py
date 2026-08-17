from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.db.session import get_db
from app.main import app
from app.models import (
    DailyTask,
    KnowledgeMastery,
    KnowledgePoint,
    KnowledgePointLifecycleChange,
    KnowledgePointPrerequisite,
    LearningActivity,
    LearningSession,
    ReviewSchedule,
    StudyPlanItem,
    StudyPlanVersion,
)
from app.schemas.knowledge_point_lifecycle import (
    KnowledgePointApplyRequest,
    KnowledgePointChangeRequest,
)
from app.services.knowledge_point_lifecycle import KnowledgePointLifecycleService


@contextmanager
def db_session():
    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        yield db
    finally:
        generator.close()


def setup_published_plan(http, goal_payload):
    goal = http.post("/api/learning-goals", json=goal_payload).json()
    course = http.post(
        "/api/courses",
        json={
            "learning_goal_id": goal["id"],
            "title": "V11A 生命周期课程",
            "status": "active",
        },
    ).json()
    points = [
        http.post(
            f"/api/courses/{course['id']}/knowledge-points",
            json={
                "title": title,
                "order_index": index,
                "estimated_minutes": 20,
            },
        ).json()
        for index, title in enumerate(("旧知识点", "后续知识点"), start=1)
    ]
    plan = http.post(
        "/api/study-plans",
        json={
            "request_id": "v11a-unit-plan-create",
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
        },
    ).json()
    published_response = http.post(
        f"/api/study-plans/{plan['id']}/publish",
        json={
            "request_id": "v11a-unit-plan-publish",
            "expected_version": plan["version"],
            "confirmed": True,
        },
    )
    assert published_response.status_code == 200, published_response.text
    published = published_response.json()
    item = next(
        item
        for item in published["plan"]["active_version"]["items"]
        if item["knowledge_point_id"] == points[0]["id"]
    )
    session = http.post(
        "/api/learning-sessions",
        json={
            "learning_goal_id": goal["id"],
            "course_id": course["id"],
            "knowledge_point_id": points[0]["id"],
            "daily_task_id": item["daily_task_id"],
        },
    ).json()
    return goal, course, points, published["plan"], item, session


def test_lifecycle_module_inspects_then_atomically_archives_without_relinking_facts(
    client, goal_payload
):
    http, _ = client
    _, course, points, plan, item, session = setup_published_plan(http, goal_payload)
    point_id = points[0]["id"]
    now = datetime(2026, 8, 1, 6, 0, tzinfo=timezone.utc)

    with db_session() as db:
        activity = LearningActivity(
            title="历史测验",
            activity_type="quiz",
            status="published",
            course_id=course["id"],
            knowledge_point_id=point_id,
            source_scope={},
            question_count=0,
            total_points=0,
            generation_request_id="v11a-unit-activity",
            generation_config_hash="a" * 64,
            prompt_version="test-v1",
            validation_warnings=[],
        )
        mastery = KnowledgeMastery(
            knowledge_point_id=point_id,
            mastery_score=50,
            confidence_score=70,
            mastery_level="developing",
            evidence_count=1,
            algorithm_version="test-v1",
            calculated_at=now,
        )
        review = ReviewSchedule(
            knowledge_point_id=point_id,
            status="pending",
            priority_score=80,
            recommended_at=now,
            due_at=now,
            reason_code="test",
            reason_summary="历史复习安排",
        )
        edge = KnowledgePointPrerequisite(
            prerequisite_knowledge_point_id=point_id,
            dependent_knowledge_point_id=points[1]["id"],
            relation_type="prerequisite",
            source="test",
        )
        db.add_all([activity, mastery, review, edge])
        db.commit()
        activity_id, mastery_id, review_id, edge_id = (
            activity.id,
            mastery.id,
            review.id,
            edge.id,
        )

        service = KnowledgePointLifecycleService(db, now=lambda: now)
        change = KnowledgePointChangeRequest(
            action="archive", lifecycle_reason="课程结构已调整"
        )
        impact = service.inspect_change(point_id, change)

        assert impact.point_version == 1
        assert impact.study_plan_ids == [plan["id"]]
        assert impact.study_plan_item_ids == [item["id"]]
        assert impact.actionable_daily_task_ids == [item["daily_task_id"]]
        assert impact.active_learning_session_ids == [session["id"]]
        assert impact.activity_ids == [activity_id]
        assert impact.mastery_ids == [mastery_id]
        assert impact.review_schedule_ids == [review_id]
        assert impact.prerequisite_edge_ids == [edge_id]
        assert db.get(DailyTask, item["daily_task_id"]).blocked_at is None

        request = KnowledgePointApplyRequest(
            action="archive",
            lifecycle_reason="课程结构已调整",
            request_id="v11a-unit-archive-request",
            expected_version=1,
            impact_hash=impact.impact_hash,
            confirmed=True,
        )
        result = service.apply_change(point_id, request)
        assert result.idempotent_replay is False
        assert result.point.lifecycle_status == "archived"
        assert result.point.version == 2

        version = db.get(StudyPlanVersion, impact.study_plan_version_ids[0])
        task = db.get(DailyTask, item["daily_task_id"])
        learning_session = db.get(LearningSession, session["id"])
        assert version.stale_at.replace(tzinfo=timezone.utc) == now
        assert task.blocked_at.replace(tzinfo=timezone.utc) == now
        assert learning_session.invalidated_at.replace(tzinfo=timezone.utc) == now

        # Historical facts and prerequisite structure retain the original point id.
        assert db.get(StudyPlanItem, item["id"]).knowledge_point_id == point_id
        assert db.get(LearningActivity, activity_id).knowledge_point_id == point_id
        assert db.get(KnowledgeMastery, mastery_id).knowledge_point_id == point_id
        assert db.get(ReviewSchedule, review_id).knowledge_point_id == point_id
        assert db.get(KnowledgePointPrerequisite, edge_id) is not None

        replay = service.apply_change(point_id, request)
        assert replay.idempotent_replay is True
        assert replay.impact.impact_hash == impact.impact_hash
        assert len(
            list(
                db.scalars(
                    select(KnowledgePointLifecycleChange).where(
                        KnowledgePointLifecycleChange.knowledge_point_id == point_id
                    )
                )
            )
        ) == 1

        with pytest.raises(AppError) as request_conflict:
            service.apply_change(
                point_id,
                request.model_copy(update={"lifecycle_reason": "同请求号的不同操作原因"}),
            )
        assert request_conflict.value.code == "knowledge_point_request_id_conflict"

        with pytest.raises(IntegrityError):
            db.delete(db.get(KnowledgePoint, point_id))
            db.commit()
        db.rollback()


def test_lifecycle_module_rejects_stale_confirmation_and_supports_directional_supersede(
    client, goal_payload
):
    http, _ = client
    goal = http.post("/api/learning-goals", json=goal_payload).json()
    course = http.post(
        "/api/courses",
        json={"learning_goal_id": goal["id"], "title": "替代课程", "status": "active"},
    ).json()
    old = http.post(
        f"/api/courses/{course['id']}/knowledge-points",
        json={"title": "旧定义", "order_index": 1},
    ).json()
    replacement = http.post(
        f"/api/courses/{course['id']}/knowledge-points",
        json={"title": "新定义", "order_index": 2},
    ).json()
    unused = http.post(
        f"/api/courses/{course['id']}/knowledge-points",
        json={"title": "无引用知识点", "order_index": 3},
    ).json()

    with db_session() as db:
        service = KnowledgePointLifecycleService(db)
        change = KnowledgePointChangeRequest(
            action="supersede",
            superseded_by_id=replacement["id"],
            lifecycle_reason="正式定义升级",
        )
        impact = service.inspect_change(old["id"], change)
        with pytest.raises(AppError) as stale:
            service.apply_change(
                old["id"],
                KnowledgePointApplyRequest(
                    **change.model_dump(),
                    request_id="v11a-stale-impact-request",
                    expected_version=1,
                    impact_hash="0" * 64,
                    confirmed=True,
                ),
            )
        assert stale.value.code == "knowledge_point_impact_changed"
        assert db.get(KnowledgePoint, old["id"]).lifecycle_status == "active"
        assert db.get(KnowledgePoint, old["id"]).version == 1

        result = service.apply_change(
            old["id"],
            KnowledgePointApplyRequest(
                **change.model_dump(),
                request_id="v11a-supersede-request",
                expected_version=1,
                impact_hash=impact.impact_hash,
                confirmed=True,
            ),
        )
        assert result.point.lifecycle_status == "superseded"
        assert result.point.superseded_by_id == replacement["id"]
        assert db.get(KnowledgePoint, replacement["id"]).lifecycle_status == "active"

        archive_change = KnowledgePointChangeRequest(
            action="archive", lifecycle_reason="无引用内容不再使用"
        )
        archive_impact = service.inspect_change(unused["id"], archive_change)
        assert archive_impact.study_plan_ids == []
        assert archive_impact.daily_task_ids == []
        assert archive_impact.learning_session_ids == []
        archived = service.apply_change(
            unused["id"],
            KnowledgePointApplyRequest(
                **archive_change.model_dump(),
                request_id="v11a-unused-archive-request",
                expected_version=1,
                impact_hash=archive_impact.impact_hash,
                confirmed=True,
            ),
        )
        assert archived.point.lifecycle_status == "archived"
