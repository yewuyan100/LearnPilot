from fastapi import APIRouter, Query, status

from app.api.deps import AppSettings, DbSession, LLMProviderDep
from app.schemas.learning_activity import (
    QuizAttemptRead,
    WrongAnswerPage,
    WrongAnswerRead,
    WrongAnswerReviewRequest,
    WrongAnswerUpdate,
)
from app.services.quiz_attempts import QuizAttemptService
from app.services.wrong_answers import WrongAnswerService


router = APIRouter(prefix="/wrong-answers", tags=["wrong-answers"])


@router.get("", response_model=WrongAnswerPage)
def list_wrong_answers(
    db: DbSession,
    settings: AppSettings,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    course_id: int | None = Query(default=None, gt=0),
    knowledge_point_id: int | None = Query(default=None, gt=0),
    question_type: str | None = Query(default=None),
) -> WrongAnswerPage:
    return WrongAnswerService(db, settings).list(
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        course_id=course_id,
        knowledge_point_id=knowledge_point_id,
        question_type=question_type,
    )


@router.post(
    "/review",
    response_model=QuizAttemptRead,
    status_code=status.HTTP_201_CREATED,
)
def create_review(
    payload: WrongAnswerReviewRequest,
    db: DbSession,
    settings: AppSettings,
    provider: LLMProviderDep,
) -> QuizAttemptRead:
    attempt = WrongAnswerService(db, settings).create_review_attempt(
        wrong_answer_ids=payload.wrong_answer_ids,
        request_id=payload.request_id,
    )
    return QuizAttemptService(db, settings, provider).serialize(attempt)


@router.get("/{wrong_answer_id}", response_model=WrongAnswerRead)
def get_wrong_answer(
    wrong_answer_id: int,
    db: DbSession,
    settings: AppSettings,
) -> WrongAnswerRead:
    return WrongAnswerService(db, settings).detail(wrong_answer_id)


@router.patch("/{wrong_answer_id}", response_model=WrongAnswerRead)
def update_wrong_answer(
    wrong_answer_id: int,
    payload: WrongAnswerUpdate,
    db: DbSession,
    settings: AppSettings,
) -> WrongAnswerRead:
    return WrongAnswerService(db, settings).update_status(
        wrong_answer_id, payload.status
    )
