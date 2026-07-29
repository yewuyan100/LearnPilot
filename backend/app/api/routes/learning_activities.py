from fastapi import APIRouter, Query, Response, status

from app.api.deps import AppSettings, DbSession, EmbedderDep, LLMProviderDep
from app.schemas.learning_activity import (
    ActivityDetail,
    ActivityGenerateRequest,
    ActivityPage,
    ActivityUpdate,
    AttemptStartRequest,
    QuestionReorderRequest,
    QuizAttemptRead,
)
from app.services.learning_activities.service import ActivityGenerationService
from app.services.quiz_attempts import QuizAttemptService


router = APIRouter(prefix="/learning-activities", tags=["learning-activities"])


def service(db, settings, embedder, provider) -> ActivityGenerationService:
    return ActivityGenerationService(db, settings, embedder, provider)


@router.post(
    "/generate",
    response_model=ActivityDetail,
    status_code=status.HTTP_201_CREATED,
)
def generate_activity(
    payload: ActivityGenerateRequest,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
) -> ActivityDetail:
    return service(db, settings, embedder, provider).generate(payload)


@router.get("", response_model=ActivityPage)
def list_activities(
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    course_id: int | None = Query(default=None, gt=0),
    knowledge_point_id: int | None = Query(default=None, gt=0),
) -> ActivityPage:
    return ActivityPage.model_validate(
        service(db, settings, embedder, provider).list(
            page=page,
            page_size=page_size,
            status_filter=status_filter,
            course_id=course_id,
            knowledge_point_id=knowledge_point_id,
        )
    )


@router.get("/{activity_id}", response_model=ActivityDetail)
def get_activity(
    activity_id: int,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
) -> ActivityDetail:
    return service(db, settings, embedder, provider).detail(activity_id)


@router.patch("/{activity_id}", response_model=ActivityDetail)
def update_activity(
    activity_id: int,
    payload: ActivityUpdate,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
) -> ActivityDetail:
    return service(db, settings, embedder, provider).update(activity_id, payload)


@router.delete(
    "/{activity_id}/questions/{question_id}",
    response_model=ActivityDetail,
)
def delete_question(
    activity_id: int,
    question_id: int,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
) -> ActivityDetail:
    return service(db, settings, embedder, provider).delete_question(
        activity_id, question_id
    )


@router.post("/{activity_id}/questions/reorder", response_model=ActivityDetail)
def reorder_questions(
    activity_id: int,
    payload: QuestionReorderRequest,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
) -> ActivityDetail:
    return service(db, settings, embedder, provider).reorder(activity_id, payload)


@router.post("/{activity_id}/publish", response_model=ActivityDetail)
def publish_activity(
    activity_id: int,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
) -> ActivityDetail:
    return service(db, settings, embedder, provider).publish(activity_id)


@router.post(
    "/{activity_id}/attempts",
    response_model=QuizAttemptRead,
    status_code=status.HTTP_201_CREATED,
)
def start_attempt(
    activity_id: int,
    payload: AttemptStartRequest,
    db: DbSession,
    settings: AppSettings,
    provider: LLMProviderDep,
) -> QuizAttemptRead:
    return QuizAttemptService(db, settings, provider).start(
        activity_id, payload.learning_session_id
    )
