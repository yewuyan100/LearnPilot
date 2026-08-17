import logging

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import AppClock, AppSettings, DbSession
from app.core.errors import AppError
from app.models.course import Course
from app.models.daily_task import DailyTask
from app.models.knowledge_point import KnowledgePoint
from app.models.learning_goal import LearningGoal
from app.models.learning_session import LearningSession
from app.models.lesson import Lesson, LessonVersion
from app.learning.lessons.validation import resolve_session_lesson_version
from app.schemas.learning_session import (
    LearningSessionCreate,
    LearningSessionRead,
    LearningSessionUpdate,
)
from app.services.crud import apply_updates, commit, get_or_404

router = APIRouter(prefix="/learning-sessions", tags=["learning sessions"])
logger = logging.getLogger(__name__)


def serialize_session(db: DbSession, session: LearningSession) -> LearningSessionRead:
    def title(model, object_id):
        return db.scalar(select(model.title).where(model.id == object_id)) if object_id else None

    lesson_version = (
        db.get(LessonVersion, session.lesson_version_id)
        if session.lesson_version_id
        else None
    )
    lesson = db.get(Lesson, lesson_version.lesson_id) if lesson_version else None
    return LearningSessionRead.model_validate(
        {
            **session.__dict__,
            "goal_title": title(LearningGoal, session.learning_goal_id),
            "course_title": title(Course, session.course_id),
            "knowledge_point_title": title(KnowledgePoint, session.knowledge_point_id),
            "task_title": title(DailyTask, session.daily_task_id),
            "lesson_id": lesson.id if lesson else None,
            "lesson_title": lesson.title if lesson else None,
            "lesson_version_number": (
                lesson_version.version_number if lesson_version else None
            ),
        }
    )


@router.post("", response_model=LearningSessionRead, status_code=status.HTTP_201_CREATED)
def create_session(payload: LearningSessionCreate, db: DbSession, clock: AppClock) -> LearningSessionRead:
    get_or_404(db, LearningGoal, payload.learning_goal_id, "学习目标")
    if payload.course_id:
        get_or_404(db, Course, payload.course_id, "课程")
    if payload.knowledge_point_id:
        point = get_or_404(db, KnowledgePoint, payload.knowledge_point_id, "知识点")
        if point.lifecycle_status != "active":
            raise AppError(
                "knowledge_point_not_active",
                "不能继续已归档或已替代的知识点",
                status.HTTP_409_CONFLICT,
            )
    if payload.daily_task_id:
        task = get_or_404(db, DailyTask, payload.daily_task_id, "今日任务")
        if task.blocked_at is not None:
            raise AppError(
                "daily_task_blocked",
                task.blocked_reason or "该任务对应课程内容已变化，需要重新规划",
                status.HTTP_409_CONFLICT,
            )
        if task.knowledge_point_id:
            task_point = get_or_404(db, KnowledgePoint, task.knowledge_point_id, "知识点")
            if task_point.lifecycle_status != "active":
                raise AppError(
                    "knowledge_point_not_active",
                    "任务关联的知识点已失效",
                    status.HTTP_409_CONFLICT,
                )
            if payload.knowledge_point_id and payload.knowledge_point_id != task.knowledge_point_id:
                raise AppError(
                    "learning_session_task_point_mismatch",
                    "学习会话与任务关联的知识点不一致",
                    status.HTTP_409_CONFLICT,
                )
        existing = db.scalar(
            select(LearningSession)
            .where(
                LearningSession.daily_task_id == payload.daily_task_id,
                LearningSession.status.in_(["active", "paused"]),
                LearningSession.invalidated_at.is_(None),
            )
            .order_by(LearningSession.started_at.desc())
        )
        if existing:
            return serialize_session(db, existing)
        task.status = "in_progress"
    lesson_version = resolve_session_lesson_version(
        db,
        course_id=payload.course_id,
        knowledge_point_id=payload.knowledge_point_id,
        lesson_version_id=payload.lesson_version_id,
    )
    session = LearningSession(
        **payload.model_dump(exclude={"lesson_version_id"}),
        lesson_version_id=lesson_version.id if lesson_version else None,
        started_at=clock.now(),
        status="active",
    )
    db.add(session)
    commit(db, session)
    return serialize_session(db, session)


@router.get("", response_model=list[LearningSessionRead])
def list_sessions(db: DbSession) -> list[LearningSessionRead]:
    sessions = db.scalars(
        select(LearningSession).order_by(LearningSession.started_at.desc())
    ).all()
    return [serialize_session(db, item) for item in sessions]


@router.get("/{session_id}", response_model=LearningSessionRead)
def get_session(session_id: int, db: DbSession) -> LearningSessionRead:
    return serialize_session(db, get_or_404(db, LearningSession, session_id, "学习会话"))


@router.patch("/{session_id}", response_model=LearningSessionRead)
def update_session(
    session_id: int, payload: LearningSessionUpdate, db: DbSession,
    settings: AppSettings, clock: AppClock,
) -> LearningSessionRead:
    session = get_or_404(db, LearningSession, session_id, "学习会话")
    values = payload.model_dump(exclude_unset=True)
    point_status = values.pop("knowledge_point_status", None)
    task_status = values.pop("daily_task_status", None)
    if session.invalidated_at is not None:
        requested_status = values.get("status")
        if point_status or task_status or (
            requested_status is not None and requested_status != "cancelled"
        ):
            raise AppError(
                "learning_session_invalidated",
                session.invalidation_reason or "该学习会话已失效，不能继续学习",
                status.HTTP_409_CONFLICT,
            )
    if values.get("status") == "completed" and values.get("ended_at") is None:
        values["ended_at"] = clock.now()
    apply_updates(session, values)
    if point_status and session.knowledge_point_id:
        point = get_or_404(db, KnowledgePoint, session.knowledge_point_id, "知识点")
        if point.lifecycle_status != "active":
            raise AppError(
                "knowledge_point_not_active",
                "该学习会话关联的知识点已失效",
                status.HTTP_409_CONFLICT,
            )
        point.status = point_status
    if task_status and session.daily_task_id:
        task = get_or_404(db, DailyTask, session.daily_task_id, "今日任务")
        if task.blocked_at is not None:
            raise AppError(
                "daily_task_blocked",
                task.blocked_reason or "该任务对应课程内容已变化，需要重新规划",
                status.HTTP_409_CONFLICT,
            )
        task.status = task_status
    commit(db, session)
    if session.status == "completed" and session.knowledge_point_id:
        try:
            from app.learning.adaptive import AdaptiveLearningLoop

            AdaptiveLearningLoop(db, settings, clock).after_lesson_completed(session)
        except Exception:
            logger.exception(
                "adaptive_loop_after_lesson_failed learning_session_id=%s",
                session.id,
            )
    return serialize_session(db, session)
