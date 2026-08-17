from datetime import datetime, time, timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import AppClock, DbSession
from app.models.course import Course
from app.models.daily_task import DailyTask
from app.models.knowledge_point import KnowledgePoint
from app.models.learning_goal import LearningGoal
from app.models.learning_session import LearningSession
from app.schemas.dashboard import ProgressResponse, ReviewResponse

router = APIRouter(tags=["dashboard"])


@router.get("/progress", response_model=ProgressResponse)
def progress(db: DbSession, clock: AppClock) -> ProgressResponse:
    today = clock.today()
    start_date = today - timedelta(days=6)
    start_at = datetime.combine(start_date, time.min)
    daily_sessions = []
    for offset in range(7):
        current = start_date + timedelta(days=offset)
        next_day = current + timedelta(days=1)
        count = db.scalar(
            select(func.count())
            .select_from(LearningSession)
            .where(
                LearningSession.started_at >= datetime.combine(current, time.min),
                LearningSession.started_at < datetime.combine(next_day, time.min),
            )
        )
        daily_sessions.append({"date": current.isoformat(), "count": count or 0})
    recent = db.scalars(
        select(LearningSession).order_by(LearningSession.started_at.desc()).limit(6)
    ).all()
    return ProgressResponse(
        goal_count=db.scalar(select(func.count()).select_from(LearningGoal)) or 0,
        active_course_count=db.scalar(
            select(func.count()).select_from(Course).where(Course.status == "active")
        )
        or 0,
        knowledge_point_count=db.scalar(select(func.count()).select_from(KnowledgePoint)) or 0,
        completed_knowledge_point_count=db.scalar(
            select(func.count()).select_from(KnowledgePoint).where(KnowledgePoint.status == "completed")
        )
        or 0,
        today_task_total=db.scalar(
            select(func.count()).select_from(DailyTask).where(DailyTask.scheduled_date == today)
        )
        or 0,
        today_task_completed=db.scalar(
            select(func.count())
            .select_from(DailyTask)
            .where(DailyTask.scheduled_date == today, DailyTask.status == "completed")
        )
        or 0,
        sessions_last_7_days=db.scalar(
            select(func.count()).select_from(LearningSession).where(LearningSession.started_at >= start_at)
        )
        or 0,
        daily_sessions=daily_sessions,
        recent_sessions=[
            {
                "id": item.id,
                "started_at": item.started_at,
                "ended_at": item.ended_at,
                "status": item.status,
                "notes": item.notes,
            }
            for item in recent
        ],
    )


@router.get("/review-items", response_model=ReviewResponse)
def review_items(db: DbSession, clock: AppClock) -> ReviewResponse:
    points = db.scalars(
        select(KnowledgePoint)
        .where(KnowledgePoint.status.in_(["learning", "not_started"]))
        .order_by(KnowledgePoint.updated_at.desc())
    ).all()
    tasks = db.scalars(
        select(DailyTask)
        .where(DailyTask.status.in_(["pending", "in_progress"]), DailyTask.scheduled_date < clock.today())
        .order_by(DailyTask.scheduled_date)
    ).all()
    return ReviewResponse(
        knowledge_points=[
            {
                "id": point.id,
                "course_id": point.course_id,
                "title": point.title,
                "status": point.status,
                "estimated_minutes": point.estimated_minutes,
            }
            for point in points
        ],
        unfinished_tasks=[
            {
                "id": task.id,
                "title": task.title,
                "scheduled_date": task.scheduled_date,
                "status": task.status,
                "estimated_minutes": task.estimated_minutes,
            }
            for task in tasks
        ],
    )
