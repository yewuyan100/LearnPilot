from fastapi import APIRouter

from app.api.deps import AppSettings, DbSession, LLMProviderDep
from app.schemas.learning_activity import (
    AnswerPayload,
    AttemptSubmitRequest,
    QuizAttemptRead,
)
from app.services.quiz_attempts import QuizAttemptService


router = APIRouter(prefix="/quiz-attempts", tags=["quiz-attempts"])


@router.get("/{attempt_id}", response_model=QuizAttemptRead)
def get_attempt(
    attempt_id: int,
    db: DbSession,
    settings: AppSettings,
    provider: LLMProviderDep,
) -> QuizAttemptRead:
    attempt_service = QuizAttemptService(db, settings, provider)
    return attempt_service.serialize(attempt_service._attempt(attempt_id))


@router.put("/{attempt_id}/answers/{question_id}", response_model=QuizAttemptRead)
def save_answer(
    attempt_id: int,
    question_id: int,
    payload: AnswerPayload,
    db: DbSession,
    settings: AppSettings,
    provider: LLMProviderDep,
) -> QuizAttemptRead:
    return QuizAttemptService(db, settings, provider).save_answer(
        attempt_id, question_id, payload
    )


@router.post("/{attempt_id}/submit", response_model=QuizAttemptRead)
def submit_attempt(
    attempt_id: int,
    payload: AttemptSubmitRequest,
    db: DbSession,
    settings: AppSettings,
    provider: LLMProviderDep,
) -> QuizAttemptRead:
    return QuizAttemptService(db, settings, provider).submit(attempt_id, payload)
