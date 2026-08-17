from fastapi import APIRouter, status

from app.api.deps import AppClock, AppSettings, DbSession, LLMProviderDep
from app.schemas.diagnostic import (
    DiagnosticAdjustmentRequest,
    DiagnosticAnswerSave,
    DiagnosticHistoryResponse,
    DiagnosticKnowledgeResultRead,
    DiagnosticCreateRequest,
    DiagnosticSessionRead,
    DiagnosticSubmitRequest,
)
from app.services.diagnostics import DiagnosticService


router = APIRouter(tags=["diagnostics"])


def service(db, settings, provider, clock) -> DiagnosticService:
    return DiagnosticService(db, settings, provider, clock)


@router.post(
    "/courses/{course_id}/diagnostics",
    response_model=DiagnosticSessionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_diagnostic(
    course_id: int,
    payload: DiagnosticCreateRequest,
    db: DbSession,
    settings: AppSettings,
    provider: LLMProviderDep,
    clock: AppClock,
) -> DiagnosticSessionRead:
    return service(db, settings, provider, clock).create(course_id, payload)


@router.post(
    "/courses/{course_id}/diagnostics/reassess",
    response_model=DiagnosticSessionRead,
    status_code=status.HTTP_201_CREATED,
)
def reassess_course(
    course_id: int,
    payload: DiagnosticCreateRequest,
    db: DbSession,
    settings: AppSettings,
    provider: LLMProviderDep,
    clock: AppClock,
) -> DiagnosticSessionRead:
    return service(db, settings, provider, clock).create(course_id, payload)


@router.get(
    "/courses/{course_id}/diagnostics/history",
    response_model=DiagnosticHistoryResponse,
)
def diagnostic_history(
    course_id: int,
    db: DbSession,
    settings: AppSettings,
    provider: LLMProviderDep,
    clock: AppClock,
) -> DiagnosticHistoryResponse:
    return service(db, settings, provider, clock).history(course_id)


@router.get(
    "/courses/{course_id}/diagnostics/latest",
    response_model=DiagnosticSessionRead | None,
)
def latest_diagnostic(
    course_id: int,
    db: DbSession,
    settings: AppSettings,
    provider: LLMProviderDep,
    clock: AppClock,
) -> DiagnosticSessionRead | None:
    return service(db, settings, provider, clock).latest(course_id)


@router.get("/diagnostics/{session_id}", response_model=DiagnosticSessionRead)
def get_diagnostic(
    session_id: int,
    db: DbSession,
    settings: AppSettings,
    provider: LLMProviderDep,
    clock: AppClock,
) -> DiagnosticSessionRead:
    return service(db, settings, provider, clock).get(session_id)


@router.put(
    "/diagnostics/{session_id}/answers/{question_id}",
    response_model=DiagnosticSessionRead,
)
def save_diagnostic_answer(
    session_id: int,
    question_id: int,
    payload: DiagnosticAnswerSave,
    db: DbSession,
    settings: AppSettings,
    provider: LLMProviderDep,
    clock: AppClock,
) -> DiagnosticSessionRead:
    return service(db, settings, provider, clock).save_answer(session_id, question_id, payload)


@router.post(
    "/diagnostics/{session_id}/submit",
    response_model=DiagnosticSessionRead,
)
def submit_diagnostic(
    session_id: int,
    payload: DiagnosticSubmitRequest,
    db: DbSession,
    settings: AppSettings,
    provider: LLMProviderDep,
    clock: AppClock,
) -> DiagnosticSessionRead:
    return service(db, settings, provider, clock).submit(session_id, payload)


@router.post(
    "/diagnostic-results/{result_id}/adjustments",
    response_model=DiagnosticKnowledgeResultRead,
)
def adjust_diagnostic_result(
    result_id: int,
    payload: DiagnosticAdjustmentRequest,
    db: DbSession,
    settings: AppSettings,
    provider: LLMProviderDep,
    clock: AppClock,
) -> DiagnosticKnowledgeResultRead:
    return service(db, settings, provider, clock).adjust(result_id, payload)
