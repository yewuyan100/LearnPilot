from fastapi import APIRouter, Query

from app.api.deps import AppClock, AppSettings, DbSession
from app.core.errors import AppError
from app.schemas.daily_task import DailyTaskRead
from app.services.adaptive_learning.schemas import RecommendationDecisionRequest, RecommendationRead
from app.services.adaptive_learning.service import AdaptiveLearningService
from app.services.adaptive_learning.lifecycle import adaptive_refresh_status, retry_adaptive_refresh

router = APIRouter(prefix="/adaptive-recommendations", tags=["adaptive recommendations"])


@router.get("/refresh-status/{knowledge_point_id}")
def get_refresh_status(knowledge_point_id: int, db: DbSession) -> dict:
    return adaptive_refresh_status(db, knowledge_point_id) or {
        "status": "idle",
        "entity_id": str(knowledge_point_id),
    }


@router.post("/refresh-tasks/{task_id}/retry")
def retry_refresh_task(
    task_id: int, db: DbSession, settings: AppSettings, clock: AppClock
) -> dict:
    try:
        return retry_adaptive_refresh(db, settings, task_id, clock=clock)
    except ValueError as exc:
        raise AppError("adaptive_refresh_task_not_found", "掌握状态更新任务不存在", 404) from exc


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
