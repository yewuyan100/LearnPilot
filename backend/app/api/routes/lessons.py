from fastapi import APIRouter, status

from app.api.deps import AppClock, AppSettings, DbSession, EmbedderDep, LLMProviderDep
from app.learning.agents.lesson.module import LessonAgent
from app.learning.agents.tutor import ScopedTutorRetrieval
from app.learning.lessons.module import LessonModule
from app.learning.lessons.schemas import (
    LessonArchiveRequest,
    LessonCreate,
    LessonGenerateRequest,
    LessonPublishRequest,
    LessonRead,
    LessonVersionRead,
)


router = APIRouter(tags=["lessons"])


def _module(db, settings, embedder, provider, clock) -> LessonModule:
    return LessonModule(
        db,
        LessonAgent(ScopedTutorRetrieval(db, settings, embedder), provider),
        clock,
    )


@router.post(
    "/courses/{course_id}/lessons",
    response_model=LessonRead,
    status_code=status.HTTP_201_CREATED,
)
def create_lesson(
    course_id: int,
    payload: LessonCreate,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
    clock: AppClock,
) -> LessonRead:
    return _module(db, settings, embedder, provider, clock).create(course_id, payload)


@router.get("/courses/{course_id}/lessons", response_model=list[LessonRead])
def list_lessons(
    course_id: int,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
    clock: AppClock,
) -> list[LessonRead]:
    return _module(db, settings, embedder, provider, clock).list_for_course(course_id)


@router.get("/lessons/{lesson_id}", response_model=LessonRead)
def get_lesson(
    lesson_id: int,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
    clock: AppClock,
) -> LessonRead:
    return _module(db, settings, embedder, provider, clock).get(lesson_id)


@router.get("/lessons/{lesson_id}/versions", response_model=list[LessonVersionRead])
def list_lesson_versions(
    lesson_id: int,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
    clock: AppClock,
) -> list[LessonVersionRead]:
    return _module(db, settings, embedder, provider, clock).versions(lesson_id)


@router.post("/lessons/{lesson_id}/generate", response_model=LessonRead)
def generate_lesson_version(
    lesson_id: int,
    payload: LessonGenerateRequest,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
    clock: AppClock,
) -> LessonRead:
    return _module(db, settings, embedder, provider, clock).generate(lesson_id, payload)


@router.post(
    "/lessons/{lesson_id}/versions/{version_number}/publish",
    response_model=LessonRead,
)
def publish_lesson_version(
    lesson_id: int,
    version_number: int,
    payload: LessonPublishRequest,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
    clock: AppClock,
) -> LessonRead:
    return _module(db, settings, embedder, provider, clock).publish(
        lesson_id,
        version_number,
        payload,
    )


@router.post("/lessons/{lesson_id}/archive", response_model=LessonRead)
def archive_lesson(
    lesson_id: int,
    payload: LessonArchiveRequest,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
    clock: AppClock,
) -> LessonRead:
    return _module(db, settings, embedder, provider, clock).archive(lesson_id, payload)
