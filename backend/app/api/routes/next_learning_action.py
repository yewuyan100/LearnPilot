from fastapi import APIRouter, Query

from app.api.deps import AppClock, AppSettings, DbSession
from app.schemas.next_learning_action import (
    NextActionAcceptRequest,
    NextActionAcceptResponse,
    NextLearningActionRead,
)
from app.services.next_learning_action import NextLearningActionService


router = APIRouter(prefix="/next-learning-action", tags=["next learning action"])


@router.get("", response_model=NextLearningActionRead)
def get_next_learning_action(
    db: DbSession,
    settings: AppSettings,
    clock: AppClock,
    available_minutes: int | None = Query(default=None, gt=0, le=720),
) -> NextLearningActionRead:
    return NextLearningActionService(db, settings, clock).get(available_minutes)


@router.post("/accept", response_model=NextActionAcceptResponse)
def accept_next_learning_action(
    payload: NextActionAcceptRequest,
    db: DbSession,
    settings: AppSettings,
    clock: AppClock,
) -> NextActionAcceptResponse:
    return NextLearningActionService(db, settings, clock).accept(payload)
