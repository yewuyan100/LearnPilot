from datetime import date
from fastapi import APIRouter, Query

from app.api.deps import AppSettings, DbSession
from app.services.adaptive_learning.schemas import ScheduleRead
from app.services.adaptive_learning.service import AdaptiveLearningService

router = APIRouter(prefix="/reviews", tags=["adaptive reviews"])


@router.get("", response_model=list[ScheduleRead])
def list_reviews(
    db: DbSession, settings: AppSettings,
    status: str | None = Query(default=None, pattern="^(pending|scheduled|completed|dismissed|superseded)$"),
    course_id: int | None = Query(default=None, gt=0), start_date: date | None = None,
    end_date: date | None = None, overdue: bool = False,
    limit: int = Query(default=100, ge=1, le=200),
) -> list[ScheduleRead]:
    return AdaptiveLearningService(db, settings).list_reviews(
        status=status, course_id=course_id, start_date=start_date,
        end_date=end_date, overdue=overdue, limit=limit,
    )
