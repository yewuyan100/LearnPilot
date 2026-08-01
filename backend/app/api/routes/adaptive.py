from fastapi import APIRouter, Query

from app.api.deps import AppSettings, DbSession
from app.schemas.daily_task import DailyTaskRead
from app.services.adaptive_learning.schemas import RecommendationDecisionRequest, RecommendationRead
from app.services.adaptive_learning.service import AdaptiveLearningService

router = APIRouter(prefix="/adaptive-recommendations", tags=["adaptive recommendations"])


@router.get("", response_model=list[RecommendationRead])
def list_recommendations(
    db: DbSession, settings: AppSettings, status: str | None = "pending",
    course_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[RecommendationRead]:
    return AdaptiveLearningService(db, settings).list_recommendations(
        status=status, course_id=course_id, limit=limit
    )


@router.post("/{recommendation_id}/accept")
def accept_recommendation(
    recommendation_id: int, payload: RecommendationDecisionRequest,
    db: DbSession, settings: AppSettings,
) -> dict:
    service = AdaptiveLearningService(db, settings)
    recommendation, task, replay = service.accept_recommendation(
        recommendation_id, request_id=payload.request_id, confirmed=payload.confirmed
    )
    return {
        "recommendation": service.serialize_recommendation(recommendation).model_dump(),
        "task": DailyTaskRead.model_validate(task).model_dump(),
        "idempotent_replay": replay,
    }


@router.post("/{recommendation_id}/reject", response_model=RecommendationRead)
def reject_recommendation(
    recommendation_id: int, db: DbSession, settings: AppSettings,
) -> RecommendationRead:
    service = AdaptiveLearningService(db, settings)
    return service.serialize_recommendation(service.reject_recommendation(recommendation_id))
