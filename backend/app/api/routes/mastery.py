from fastapi import APIRouter, Query

from app.api.deps import AppSettings, DbSession
from app.services.adaptive_learning.schemas import (
    MasteryDetail, MasteryPage, RebuildRequest, RebuildResult,
    SelfAssessmentRequest, WeakPointRead,
)
from app.services.adaptive_learning.service import AdaptiveLearningService

router = APIRouter(prefix="/mastery", tags=["adaptive mastery"])


@router.get("", response_model=MasteryPage)
def list_mastery(
    db: DbSession, settings: AppSettings,
    course_id: int | None = Query(default=None, gt=0), mastery_level: str | None = None,
    sort: str = Query(default="weakness", pattern="^(weakness|mastery_desc|recent)$"),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
) -> MasteryPage:
    return AdaptiveLearningService(db, settings).list_mastery(
        course_id=course_id, mastery_level=mastery_level, sort=sort, page=page, page_size=page_size
    )

@router.get("/weak-points", response_model=list[WeakPointRead])
def weak_points(
    db: DbSession, settings: AppSettings, course_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=20, ge=1, le=100), include_unassessed: bool = True,
) -> list[WeakPointRead]:
    return AdaptiveLearningService(db, settings).weak_points(
        course_id=course_id, limit=limit, include_unassessed=include_unassessed
    )


@router.post("/rebuild", response_model=RebuildResult)
def rebuild(payload: RebuildRequest, db: DbSession, settings: AppSettings) -> RebuildResult:
    return AdaptiveLearningService(db, settings).rebuild(
        course_id=payload.course_id, knowledge_point_id=payload.knowledge_point_id
    )


@router.get("/{knowledge_point_id}", response_model=MasteryDetail)
def mastery_detail(knowledge_point_id: int, db: DbSession, settings: AppSettings) -> MasteryDetail:
    return AdaptiveLearningService(db, settings).detail(knowledge_point_id)


@router.put("/{knowledge_point_id}/self-assessment", response_model=MasteryDetail)
def self_assessment(
    knowledge_point_id: int, payload: SelfAssessmentRequest,
    db: DbSession, settings: AppSettings,
) -> MasteryDetail:
    return AdaptiveLearningService(db, settings).self_assessment(
        knowledge_point_id, rating=payload.rating, request_id=payload.request_id
    )
