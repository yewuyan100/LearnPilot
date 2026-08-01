from datetime import datetime

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import AppSettings, DbSession
from app.models.course import Course
from app.models.daily_task import DailyTask
from app.models.knowledge_point import KnowledgePoint
from app.models.learning_goal import LearningGoal
from app.models.learning_session import LearningSession
from app.schemas.learning_session import (
    LearningSessionCreate,
    LearningSessionRead,
    LearningSessionUpdate,
)
from app.services.crud import apply_updates, commit, get_or_404

router = APIRouter(prefix="/learning-sessions", tags=["learning sessions"])


def serialize_session(db: DbSession, session: LearningSession) -> LearningSessionRead:
    def title(model, object_id):
        return db.scalar(select(model.title).where(model.id == object_id)) if object_id else None

    return LearningSessionRead.model_validate(
        {
            **session.__dict__,
            "goal_title": title(LearningGoal, session.learning_goal_id),
            "course_title": title(Course, session.course_id),
            "knowledge_point_title": title(KnowledgePoint, session.knowledge_point_id),
            "task_title": title(DailyTask, session.daily_task_id),
        }
    )


@router.post("", response_model=LearningSessionRead, status_code=status.HTTP_201_CREATED)
def create_session(payload: LearningSessionCreate, db: DbSession) -> LearningSessionRead:
    get_or_404(db, LearningGoal, payload.learning_goal_id, "学习目标")
    if payload.course_id:
        get_or_404(db, Course, payload.course_id, "课程")
    if payload.knowledge_point_id:
        get_or_404(db, KnowledgePoint, payload.knowledge_point_id, "知识点")
    if payload.daily_task_id:
        task = get_or_404(db, DailyTask, payload.daily_task_id, "今日任务")
        existing = db.scalar(
            select(LearningSession)
            .where(
                LearningSession.daily_task_id == payload.daily_task_id,
                LearningSession.status.in_(["active", "paused"]),
            )
            .order_by(LearningSession.started_at.desc())
        )
        if existing:
            return serialize_session(db, existing)
        task.status = "in_progress"
    session = LearningSession(
        **payload.model_dump(),
        started_at=datetime.now(),
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
    session_id: int, payload: LearningSessionUpdate, db: DbSession, settings: AppSettings
) -> LearningSessionRead:
    session = get_or_404(db, LearningSession, session_id, "学习会话")
    values = payload.model_dump(exclude_unset=True)
    point_status = values.pop("knowledge_point_status", None)
    task_status = values.pop("daily_task_status", None)
    if values.get("status") == "completed" and values.get("ended_at") is None:
        values["ended_at"] = datetime.now()
    apply_updates(session, values)
    if point_status and session.knowledge_point_id:
        get_or_404(db, KnowledgePoint, session.knowledge_point_id, "知识点").status = point_status
    if task_status and session.daily_task_id:
        get_or_404(db, DailyTask, session.daily_task_id, "今日任务").status = task_status
    commit(db, session)
    if session.status == "completed" and session.knowledge_point_id:
        from app.services.adaptive_learning.lifecycle import try_refresh_adaptive_learning
        try_refresh_adaptive_learning(
            db, settings, session.knowledge_point_id,
            trigger_type="learning_session_completed", trigger_source_id=session.id,
        )
    return serialize_session(db, session)
