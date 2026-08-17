from fastapi import APIRouter, Response, status
from sqlalchemy import func, select

from app.api.deps import DbSession
from app.core.errors import AppError
from app.models.course import Course
from app.models.knowledge_point import KnowledgePoint
from app.models.learning_goal import LearningGoal
from app.schemas.course import (
    CourseCreate,
    CourseRead,
    CourseUpdate,
    KnowledgePointCreate,
    KnowledgePointRead,
    KnowledgePointUpdate,
)
from app.schemas.knowledge_point_lifecycle import (
    KnowledgePointApplyRequest,
    KnowledgePointChangeRequest,
    KnowledgePointChangeResult,
    KnowledgePointImpact,
)
from app.services.crud import apply_updates, commit, get_or_404
from app.services.knowledge_point_lifecycle import KnowledgePointLifecycleService

router = APIRouter(tags=["courses"])


def serialize_course(db: DbSession, course: Course) -> CourseRead:
    count = db.scalar(
        select(func.count()).select_from(KnowledgePoint).where(
            KnowledgePoint.course_id == course.id,
            KnowledgePoint.lifecycle_status == "active",
        )
    )
    goal_title = db.scalar(select(LearningGoal.title).where(LearningGoal.id == course.learning_goal_id))
    return CourseRead.model_validate(
        {**course.__dict__, "knowledge_point_count": count or 0, "learning_goal_title": goal_title}
    )


@router.post("/courses", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(payload: CourseCreate, db: DbSession) -> CourseRead:
    get_or_404(db, LearningGoal, payload.learning_goal_id, "学习目标")
    course = Course(**payload.model_dump(mode="json"))
    db.add(course)
    commit(db, course)
    return serialize_course(db, course)


@router.get("/courses", response_model=list[CourseRead])
def list_courses(db: DbSession) -> list[CourseRead]:
    courses = db.scalars(select(Course).order_by(Course.created_at.desc())).all()
    return [serialize_course(db, course) for course in courses]


@router.get("/courses/{course_id}", response_model=CourseRead)
def get_course(course_id: int, db: DbSession) -> CourseRead:
    return serialize_course(db, get_or_404(db, Course, course_id, "课程"))


@router.patch("/courses/{course_id}", response_model=CourseRead)
def update_course(course_id: int, payload: CourseUpdate, db: DbSession) -> CourseRead:
    course = get_or_404(db, Course, course_id, "课程")
    values = payload.model_dump(exclude_unset=True, mode="json")
    if "learning_goal_id" in values:
        get_or_404(db, LearningGoal, values["learning_goal_id"], "学习目标")
    apply_updates(course, values)
    commit(db, course)
    return serialize_course(db, course)


@router.delete("/courses/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(course_id: int, db: DbSession) -> Response:
    course = get_or_404(db, Course, course_id, "课程")
    point_count = db.scalar(
        select(func.count()).select_from(KnowledgePoint).where(
            KnowledgePoint.course_id == course.id
        )
    ) or 0
    if point_count:
        raise AppError(
            "course_contains_knowledge_points",
            "含知识点的课程不能硬删除，请改为归档课程",
            status.HTTP_409_CONFLICT,
            {"knowledge_point_count": point_count},
        )
    db.delete(course)
    commit(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/courses/{course_id}/knowledge-points",
    response_model=KnowledgePointRead,
    status_code=status.HTTP_201_CREATED,
)
def create_knowledge_point(
    course_id: int, payload: KnowledgePointCreate, db: DbSession
) -> KnowledgePoint:
    get_or_404(db, Course, course_id, "课程")
    point = KnowledgePoint(course_id=course_id, **payload.model_dump(mode="json"))
    db.add(point)
    return commit(db, point)


@router.get("/courses/{course_id}/knowledge-points", response_model=list[KnowledgePointRead])
def list_knowledge_points(
    course_id: int, db: DbSession, include_inactive: bool = False
) -> list[KnowledgePoint]:
    get_or_404(db, Course, course_id, "课程")
    query = select(KnowledgePoint).where(KnowledgePoint.course_id == course_id)
    if not include_inactive:
        query = query.where(KnowledgePoint.lifecycle_status == "active")
    return list(
        db.scalars(query.order_by(KnowledgePoint.order_index))
    )


@router.patch("/knowledge-points/{point_id}", response_model=KnowledgePointRead)
def update_knowledge_point(
    point_id: int, payload: KnowledgePointUpdate, db: DbSession
) -> KnowledgePoint:
    point = get_or_404(db, KnowledgePoint, point_id, "知识点")
    if point.lifecycle_status != "active":
        raise AppError(
            "knowledge_point_not_active",
            "已归档或已替代的知识点不能再修改学习状态",
            status.HTTP_409_CONFLICT,
        )
    apply_updates(point, payload.model_dump(exclude_unset=True, mode="json"))
    return commit(db, point)


@router.get("/knowledge-points/{point_id}", response_model=KnowledgePointRead)
def get_knowledge_point(point_id: int, db: DbSession) -> KnowledgePoint:
    return get_or_404(db, KnowledgePoint, point_id, "知识点")


@router.post(
    "/knowledge-points/{point_id}/impact", response_model=KnowledgePointImpact
)
def inspect_knowledge_point_change(
    point_id: int, payload: KnowledgePointChangeRequest, db: DbSession
) -> KnowledgePointImpact:
    return KnowledgePointLifecycleService(db).inspect_change(point_id, payload)


@router.post(
    "/knowledge-points/{point_id}/archive", response_model=KnowledgePointChangeResult
)
def archive_knowledge_point(
    point_id: int, payload: KnowledgePointApplyRequest, db: DbSession
) -> KnowledgePointChangeResult:
    if payload.action != "archive":
        raise AppError(
            "knowledge_point_action_mismatch",
            "归档接口只接受 archive 操作",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return KnowledgePointLifecycleService(db).apply_change(point_id, payload)


@router.post(
    "/knowledge-points/{point_id}/supersede", response_model=KnowledgePointChangeResult
)
def supersede_knowledge_point(
    point_id: int, payload: KnowledgePointApplyRequest, db: DbSession
) -> KnowledgePointChangeResult:
    if payload.action != "supersede":
        raise AppError(
            "knowledge_point_action_mismatch",
            "替代接口只接受 supersede 操作",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return KnowledgePointLifecycleService(db).apply_change(point_id, payload)


@router.delete("/knowledge-points/{point_id}", deprecated=True)
def delete_knowledge_point(point_id: int, db: DbSession) -> None:
    impact = KnowledgePointLifecycleService(db).inspect_change(
        point_id,
        KnowledgePointChangeRequest(
            action="archive",
            lifecycle_reason="旧删除接口仅用于影响检查",
        ),
    )
    raise AppError(
        "knowledge_point_impact_analysis_required",
        "知识点不允许硬删除，请先检查影响并执行归档或替代",
        status.HTTP_409_CONFLICT,
        {"impact": impact.model_dump(mode="json")},
    )
