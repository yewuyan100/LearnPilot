import json

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import StreamingResponse

from app.api.deps import AppClock, AppSettings, DbSession, LLMProviderDep
from app.schemas.course_architecture import (
    CourseArchitectureDraftCreate,
    CourseArchitectureDraftUpdate,
    CourseArchitectureQualityReport,
    DraftCourseCreate,
    DraftCourseUpdate,
    DraftGenerationRequest,
    DraftKnowledgePointCreate,
    DraftKnowledgePointMerge,
    DraftKnowledgePointMove,
    DraftKnowledgePointUpdate,
    DraftListResponse,
    DraftMaterialsReplace,
    DraftPrerequisiteCreate,
    DraftPublishRequest,
    DraftRead,
    DraftReorder,
    DraftSourceCreate,
    PublishResult,
    VersionedWrite,
)
from app.services.course_architecture.drafts import CourseArchitectureDraftService
from app.services.course_architecture.generation import CourseArchitectureGenerationService
from app.services.course_architecture.publishing import CourseArchitecturePublishingService
from app.services.course_architecture.validation import CourseArchitectureValidationService


router = APIRouter(prefix="/course-architecture/drafts", tags=["course-architecture"])


@router.get("", response_model=DraftListResponse)
def list_drafts(db: DbSession, clock: AppClock, include_archived: bool = False) -> DraftListResponse:
    return CourseArchitectureDraftService(db, clock).list_drafts(include_archived=include_archived)


@router.post("", response_model=DraftRead, status_code=status.HTTP_201_CREATED)
def create_draft(payload: CourseArchitectureDraftCreate, db: DbSession, clock: AppClock) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).create_draft(
        learning_goal_id=payload.learning_goal_id,
        material_ids=payload.material_ids,
        title=payload.title,
        description=payload.description,
    )


@router.get("/{draft_id}", response_model=DraftRead)
def get_draft(draft_id: int, db: DbSession, clock: AppClock) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).get_draft(draft_id)


@router.post("/{draft_id}/versions", response_model=DraftRead, status_code=status.HTTP_201_CREATED)
def create_draft_version(draft_id: int, db: DbSession, clock: AppClock) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).create_version_from_published(draft_id)


@router.patch("/{draft_id}", response_model=DraftRead)
def update_draft(
    draft_id: int, payload: CourseArchitectureDraftUpdate, db: DbSession, clock: AppClock
) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).update_draft(
        draft_id, version=payload.version, title=payload.title, description=payload.description
    )


@router.delete("/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_draft(
    draft_id: int,
    db: DbSession,
    clock: AppClock,
    version: int = Query(ge=1),
) -> Response:
    CourseArchitectureDraftService(db, clock).archive_draft(draft_id, version=version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{draft_id}/materials", response_model=DraftRead)
def replace_materials(
    draft_id: int, payload: DraftMaterialsReplace, db: DbSession, clock: AppClock
) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).replace_materials(
        draft_id, version=payload.version, material_ids=payload.material_ids
    )


@router.post("/{draft_id}/courses", response_model=DraftRead)
def add_course(draft_id: int, payload: DraftCourseCreate, db: DbSession, clock: AppClock) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).add_course(draft_id, payload)


@router.patch("/{draft_id}/courses/{course_id}", response_model=DraftRead)
def update_course(
    draft_id: int, course_id: int, payload: DraftCourseUpdate, db: DbSession, clock: AppClock
) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).update_course(draft_id, course_id, payload)


@router.delete("/{draft_id}/courses/{course_id}", response_model=DraftRead)
def delete_course(
    draft_id: int,
    course_id: int,
    db: DbSession,
    clock: AppClock,
    version: int = Query(ge=1),
) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).delete_course(draft_id, course_id, version=version)


@router.post("/{draft_id}/courses/reorder", response_model=DraftRead)
def reorder_courses(draft_id: int, payload: DraftReorder, db: DbSession, clock: AppClock) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).reorder_courses(draft_id, payload)


@router.post("/{draft_id}/knowledge-points", response_model=DraftRead)
def add_point(
    draft_id: int, payload: DraftKnowledgePointCreate, db: DbSession, clock: AppClock
) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).add_knowledge_point(draft_id, payload)


@router.patch("/{draft_id}/knowledge-points/{point_id}", response_model=DraftRead)
def update_point(
    draft_id: int,
    point_id: int,
    payload: DraftKnowledgePointUpdate,
    db: DbSession,
    clock: AppClock,
) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).update_knowledge_point(draft_id, point_id, payload)


@router.delete("/{draft_id}/knowledge-points/{point_id}", response_model=DraftRead)
def delete_point(
    draft_id: int,
    point_id: int,
    db: DbSession,
    clock: AppClock,
    version: int = Query(ge=1),
) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).delete_knowledge_point(draft_id, point_id, version=version)


@router.post("/{draft_id}/knowledge-points/reorder", response_model=DraftRead)
def reorder_points(draft_id: int, payload: DraftReorder, db: DbSession, clock: AppClock) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).reorder_knowledge_points(draft_id, payload)


@router.post("/{draft_id}/knowledge-points/move", response_model=DraftRead)
def move_point(
    draft_id: int, payload: DraftKnowledgePointMove, db: DbSession, clock: AppClock
) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).move_knowledge_point(draft_id, payload)


@router.post("/{draft_id}/knowledge-points/merge", response_model=DraftRead)
def merge_points(
    draft_id: int, payload: DraftKnowledgePointMerge, db: DbSession, clock: AppClock
) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).merge_knowledge_points(draft_id, payload)


@router.post("/{draft_id}/knowledge-points/{point_id}/sources", response_model=DraftRead)
def add_source(
    draft_id: int, point_id: int, payload: DraftSourceCreate, db: DbSession, clock: AppClock
) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).add_source(draft_id, point_id, payload)


@router.delete("/{draft_id}/sources/{source_id}", response_model=DraftRead)
def delete_source(
    draft_id: int,
    source_id: int,
    db: DbSession,
    clock: AppClock,
    version: int = Query(ge=1),
) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).delete_source(draft_id, source_id, version=version)


@router.post("/{draft_id}/prerequisites", response_model=DraftRead)
def add_prerequisite(
    draft_id: int, payload: DraftPrerequisiteCreate, db: DbSession, clock: AppClock
) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).add_prerequisite(draft_id, payload)


@router.delete("/{draft_id}/prerequisites/{edge_id}", response_model=DraftRead)
def delete_prerequisite(
    draft_id: int,
    edge_id: int,
    db: DbSession,
    clock: AppClock,
    version: int = Query(ge=1),
) -> DraftRead:
    return CourseArchitectureDraftService(db, clock).delete_prerequisite(draft_id, edge_id, version=version)


@router.get("/{draft_id}/quality-report", response_model=CourseArchitectureQualityReport)
def quality_report(draft_id: int, db: DbSession, settings: AppSettings) -> CourseArchitectureQualityReport:
    return CourseArchitectureValidationService(db, settings).build_report(draft_id)


@router.post("/{draft_id}/validate", response_model=DraftRead)
def validate_draft(
    draft_id: int, payload: VersionedWrite, db: DbSession, settings: AppSettings, clock: AppClock
) -> DraftRead:
    CourseArchitectureValidationService(db, settings).validate_draft(draft_id, version=payload.version)
    return CourseArchitectureDraftService(db, clock).get_draft(draft_id)


@router.post("/{draft_id}/generate", response_model=DraftRead)
def generate_draft(
    draft_id: int,
    payload: DraftGenerationRequest,
    db: DbSession,
    settings: AppSettings,
    clock: AppClock,
    provider: LLMProviderDep,
) -> DraftRead:
    # A sync FastAPI route already runs in the worker pool; the SQLAlchemy Session stays in that worker.
    return CourseArchitectureGenerationService(db, settings, clock, provider).generate(
        draft_id, version=payload.version, request_id=payload.request_id
    )


@router.post("/{draft_id}/generate/cancel", response_model=DraftRead)
def cancel_generation(
    draft_id: int,
    payload: VersionedWrite,
    db: DbSession,
    settings: AppSettings,
    clock: AppClock,
    provider: LLMProviderDep,
) -> DraftRead:
    return CourseArchitectureGenerationService(db, settings, clock, provider).request_cancel(
        draft_id, version=payload.version
    )


@router.get("/{draft_id}/events")
def generation_events(draft_id: int, db: DbSession, clock: AppClock) -> StreamingResponse:
    draft = CourseArchitectureDraftService(db, clock).get_draft(draft_id)

    def stream():
        for event in draft.generation_progress.get("events", []):
            name = str(event.get("event") or "progress")
            yield f"event: {name}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield f"event: run.completed\ndata: {json.dumps({'status': draft.generation_status, 'version': draft.version})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{draft_id}/publish", response_model=PublishResult)
def publish_draft(
    draft_id: int,
    payload: DraftPublishRequest,
    db: DbSession,
    settings: AppSettings,
    clock: AppClock,
) -> PublishResult:
    return CourseArchitecturePublishingService(db, settings, clock).publish(
        draft_id,
        version=payload.version,
        publish_request_id=payload.publish_request_id,
        confirmed=payload.confirmed,
    )
