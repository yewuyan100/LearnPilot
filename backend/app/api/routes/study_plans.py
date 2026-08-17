from fastapi import APIRouter, Query, status

from app.api.deps import AppClock, AppSettings, DbSession
from app.schemas.study_plan import (
    StudyPlanCancelRequest,
    StudyPlanCreateRequest,
    StudyPlanHistoryResponse,
    StudyPlanPublishRequest,
    StudyPlanPublishResult,
    StudyPlanRead,
    StudyPlanReplanRequest,
    StudyPlanVersionRead,
)
from app.services.study_plans import StudyPlanService


router = APIRouter(prefix="/study-plans", tags=["study plans"])


def service(db, settings, clock) -> StudyPlanService:
    return StudyPlanService(db, settings, clock)


@router.post("", response_model=StudyPlanRead, status_code=status.HTTP_201_CREATED)
def create_study_plan(
    payload: StudyPlanCreateRequest,
    db: DbSession,
    settings: AppSettings,
    clock: AppClock,
) -> StudyPlanRead:
    return service(db, settings, clock).create(payload)


@router.get("/active", response_model=StudyPlanRead | None)
def active_study_plan(
    db: DbSession,
    settings: AppSettings,
    clock: AppClock,
    learning_goal_id: int | None = Query(default=None, gt=0),
    course_id: int | None = Query(default=None, gt=0),
) -> StudyPlanRead | None:
    return service(db, settings, clock).active(learning_goal_id, course_id)


@router.get("/{plan_id}", response_model=StudyPlanRead)
def get_study_plan(
    plan_id: int, db: DbSession, settings: AppSettings, clock: AppClock
) -> StudyPlanRead:
    return service(db, settings, clock).get(plan_id)


@router.get("/{plan_id}/preview", response_model=StudyPlanRead)
def preview_study_plan(
    plan_id: int, db: DbSession, settings: AppSettings, clock: AppClock
) -> StudyPlanRead:
    return service(db, settings, clock).get(plan_id)


@router.post("/{plan_id}/validate", response_model=StudyPlanVersionRead)
def validate_study_plan(
    plan_id: int, db: DbSession, settings: AppSettings, clock: AppClock
) -> StudyPlanVersionRead:
    plan = service(db, settings, clock).get(plan_id)
    return plan.latest_version


@router.post("/{plan_id}/publish", response_model=StudyPlanPublishResult)
def publish_study_plan(
    plan_id: int,
    payload: StudyPlanPublishRequest,
    db: DbSession,
    settings: AppSettings,
    clock: AppClock,
) -> StudyPlanPublishResult:
    return service(db, settings, clock).publish(plan_id, payload)


@router.post("/{plan_id}/replan", response_model=StudyPlanRead)
def replan_study_plan(
    plan_id: int,
    payload: StudyPlanReplanRequest,
    db: DbSession,
    settings: AppSettings,
    clock: AppClock,
) -> StudyPlanRead:
    return service(db, settings, clock).replan(plan_id, payload)


@router.post("/{plan_id}/cancel", response_model=StudyPlanRead)
def cancel_study_plan(
    plan_id: int,
    payload: StudyPlanCancelRequest,
    db: DbSession,
    settings: AppSettings,
    clock: AppClock,
) -> StudyPlanRead:
    return service(db, settings, clock).cancel(plan_id, payload)


@router.get("/{plan_id}/versions", response_model=StudyPlanHistoryResponse)
def study_plan_versions(
    plan_id: int, db: DbSession, settings: AppSettings, clock: AppClock
) -> StudyPlanHistoryResponse:
    return service(db, settings, clock).history(plan_id)
