from fastapi import APIRouter, Response, status
from sqlalchemy import select

from app.api.deps import AppClock, AppSettings, DbSession
from app.core.errors import AppError
from app.models.course import Course
from app.models.daily_task import DailyTask
from app.models.knowledge_point import KnowledgePoint
from app.models.learning_goal import LearningGoal
from app.models.learning_activity import LearningActivity
from app.models.learning_session import LearningSession
from app.schemas.daily_task import DailyTaskCreate, DailyTaskRead, DailyTaskUpdate, TodayResponse
from app.services.crud import apply_updates, commit, get_or_404

router = APIRouter(tags=["daily tasks"])


@router.get("/today", response_model=TodayResponse)
def get_today(db: DbSession, clock: AppClock) -> TodayResponse:
    today = clock.today()
    tasks = list(
        db.scalars(
            select(DailyTask)
            .where(DailyTask.scheduled_date == today)
            .order_by(DailyTask.status, DailyTask.created_at)
        )
    )
    goal = db.scalar(
        select(LearningGoal)
        .where(LearningGoal.status == "active")
        .order_by(LearningGoal.updated_at.desc())
    )
    course = db.scalar(select(Course).order_by(Course.updated_at.desc()))
    session = db.scalar(select(LearningSession).order_by(LearningSession.started_at.desc()))
    return TodayResponse(
        date=today,
        current_goal={
            "id": goal.id,
            "title": goal.title,
            "target_date": goal.target_date,
            "daily_minutes": goal.daily_minutes,
            "current_level": goal.current_level,
        }
        if goal
        else None,
        tasks=[DailyTaskRead.model_validate(task) for task in tasks],
        pending_count=sum(
            task.status in {"pending", "in_progress"} and task.blocked_at is None
            for task in tasks
        ),
        blocked_count=sum(task.blocked_at is not None for task in tasks),
        recent_course={"id": course.id, "title": course.title, "status": course.status} if course else None,
        recent_session={
            "id": session.id,
            "learning_goal_id": session.learning_goal_id,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "status": session.status,
            "notes": session.notes,
        }
        if session
        else None,
    )


@router.post("/daily-tasks", response_model=DailyTaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: DailyTaskCreate, db: DbSession) -> DailyTask:
    get_or_404(db, LearningGoal, payload.learning_goal_id, "学习目标")
    if payload.course_id:
        get_or_404(db, Course, payload.course_id, "课程")
    if payload.knowledge_point_id:
        point = get_or_404(db, KnowledgePoint, payload.knowledge_point_id, "知识点")
        if point.lifecycle_status != "active":
            raise AppError(
                "knowledge_point_not_active",
                "不能为已归档或已替代的知识点创建任务",
                status.HTTP_409_CONFLICT,
            )
    if payload.activity_id:
        get_or_404(db, LearningActivity, payload.activity_id, "学习活动")
    task = DailyTask(**payload.model_dump())
    db.add(task)
    return commit(db, task)


@router.patch("/daily-tasks/{task_id}", response_model=DailyTaskRead)
def update_task(task_id: int, payload: DailyTaskUpdate, db: DbSession, settings: AppSettings, clock: AppClock) -> DailyTask:
    task = get_or_404(db, DailyTask, task_id, "今日任务")
    values = payload.model_dump(exclude_unset=True)
    if task.blocked_at is not None and values.get("status") in {"in_progress", "completed"}:
        raise AppError(
            "daily_task_blocked",
            task.blocked_reason or "该任务对应课程内容已变化，需要重新规划",
            status.HTTP_409_CONFLICT,
        )
    if values.get("activity_id"):
        get_or_404(db, LearningActivity, values["activity_id"], "学习活动")
    apply_updates(task, values)
    commit(db, task)
    if task.status == "completed" and task.knowledge_point_id:
        from app.services.adaptive_learning.lifecycle import try_refresh_adaptive_learning
        from app.services.adaptive_learning.scheduler import ReviewScheduler
        ReviewScheduler(db, settings).complete_for_task(task)
        db.commit()
        try_refresh_adaptive_learning(
            db, settings, task.knowledge_point_id,
            trigger_type="task_completed", trigger_source_id=task.id,
            clock=clock,
        )
    return task


@router.delete("/daily-tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: DbSession) -> Response:
    task = get_or_404(db, DailyTask, task_id, "今日任务")
    db.delete(task)
    commit(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
