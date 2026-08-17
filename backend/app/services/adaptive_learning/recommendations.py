from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.clock import clock_from_settings
from app.core.errors import AppError
from app.models import (
    AdaptiveRecommendation, Course, DailyTask, KnowledgePoint, LearningGoal,
    ReviewSchedule,
)


class AdaptiveRecommendationService:
    def __init__(self, db, settings, *, now: datetime | None = None):
        self.db = db
        self.settings = settings
        self.now = now or clock_from_settings(settings).now()

    def generate(self, mastery, schedule: ReviewSchedule | None) -> tuple[AdaptiveRecommendation | None, bool]:
        if schedule is None or mastery.mastery_score is None:
            return None, False
        current = self.db.scalar(select(AdaptiveRecommendation).where(
            AdaptiveRecommendation.knowledge_point_id == mastery.knowledge_point_id,
            AdaptiveRecommendation.status.in_(("pending", "accepted")),
        ).order_by(AdaptiveRecommendation.id.desc()))
        due_at = schedule.due_at.replace(tzinfo=timezone.utc) if schedule.due_at.tzinfo is None else schedule.due_at
        suggested_date = due_at.astimezone(ZoneInfo(self.settings.app_timezone)).date()
        priority = "high" if schedule.priority_score >= 70 else "medium" if schedule.priority_score >= 45 else "low"
        minutes = 30 if priority == "high" else 25 if priority == "medium" else 20
        point = self.db.get(KnowledgePoint, mastery.knowledge_point_id)
        details = {
            "mastery_score": float(mastery.mastery_score),
            "confidence_score": float(mastery.confidence_score),
            "mastery_level": mastery.mastery_level,
            "reason_summary": schedule.reason_summary,
            "schedule_id": schedule.id,
            "due_at": schedule.due_at.isoformat(),
        }
        if current and current.source_snapshot_id == schedule.source_snapshot_id and current.reason_details_json == details:
            return current, False
        if current:
            current.status = "superseded"
            self.db.flush()
        recommendation = AdaptiveRecommendation(
            recommendation_type="review_task", knowledge_point_id=mastery.knowledge_point_id,
            status="pending", priority=priority,
            title=f"复习：{point.title if point else '知识点'}",
            reason_code=schedule.reason_code, reason_details_json=details,
            suggested_date=suggested_date, suggested_minutes=minutes,
            source_snapshot_id=schedule.source_snapshot_id,
        )
        self.db.add(recommendation)
        self.db.flush()
        return recommendation, True

    def accept(self, recommendation_id: int, *, request_id: str, confirmed: bool) -> tuple[AdaptiveRecommendation, DailyTask, bool]:
        if not confirmed:
            raise AppError("adaptive_recommendation_conflict", "创建复习任务前必须明确确认", 409)
        recommendation = self.db.get(AdaptiveRecommendation, recommendation_id)
        if not recommendation:
            raise AppError("adaptive_recommendation_not_found", "复习建议不存在", 404)
        if recommendation.created_task_id:
            task = self.db.get(DailyTask, recommendation.created_task_id)
            if task:
                return recommendation, task, True
        if recommendation.status not in {"pending", "accepted"}:
            code = "adaptive_recommendation_expired" if recommendation.status == "expired" else "adaptive_recommendation_conflict"
            raise AppError(code, "当前复习建议不能再接受", 409)
        point = self.db.get(KnowledgePoint, recommendation.knowledge_point_id)
        course = self.db.get(Course, point.course_id) if point else None
        goal = self.db.get(LearningGoal, course.learning_goal_id) if course else None
        if not point or not course or not goal:
            raise AppError("adaptive_task_creation_failed", "建议关联的学习目标或课程已不可用", 409)
        task = DailyTask(
            learning_goal_id=goal.id, course_id=course.id, knowledge_point_id=point.id,
            title=recommendation.title, task_type="review",
            estimated_minutes=recommendation.suggested_minutes,
            scheduled_date=recommendation.suggested_date, status="pending",
        )
        self.db.add(task)
        self.db.flush()
        recommendation.status = "executed"
        recommendation.created_task_id = task.id
        schedule_id = recommendation.reason_details_json.get("schedule_id")
        schedule = self.db.get(ReviewSchedule, schedule_id) if schedule_id else None
        if schedule and schedule.status in {"pending", "scheduled"}:
            schedule.status = "scheduled"
            schedule.completed_task_id = task.id
        self.db.commit()
        self.db.refresh(recommendation)
        self.db.refresh(task)
        return recommendation, task, False

    def reject(self, recommendation_id: int) -> AdaptiveRecommendation:
        recommendation = self.db.get(AdaptiveRecommendation, recommendation_id)
        if not recommendation:
            raise AppError("adaptive_recommendation_not_found", "复习建议不存在", 404)
        if recommendation.created_task_id:
            raise AppError("adaptive_recommendation_conflict", "已创建任务的建议不能拒绝", 409)
        if recommendation.status == "rejected":
            return recommendation
        if recommendation.status != "pending":
            raise AppError("adaptive_recommendation_conflict", "当前复习建议不能拒绝", 409)
        recommendation.status = "rejected"
        self.db.commit()
        self.db.refresh(recommendation)
        return recommendation
