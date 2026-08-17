from fastapi import APIRouter, Query, Response, status

from app.api.deps import AppClock, AppSettings, DbSession
from app.schemas.note import (
    NoteCreate,
    NoteLinkCreate,
    NoteLinkRead,
    NotePage,
    NoteRead,
    NoteSourceCreate,
    NoteSourceRead,
    NoteUpdate,
)
from app.services.notes import NoteService


router = APIRouter(prefix="/notes", tags=["notes"])


def service(db: DbSession, settings: AppSettings, clock: AppClock) -> NoteService:
    return NoteService(db, settings, clock)


@router.get("", response_model=NotePage)
def list_notes(
    db: DbSession,
    settings: AppSettings,
    clock: AppClock,
    q: str | None = Query(default=None, max_length=300),
    note_type: str | None = None,
    tag: str | None = Query(default=None, max_length=64),
    entity_type: str | None = None,
    entity_id: int | None = Query(default=None, gt=0),
    pinned: bool | None = None,
    archived: bool | None = False,
    sort: str = Query(default="updated_desc", pattern="^(updated_desc|updated_asc|created_desc|title)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> NotePage:
    return service(db, settings, clock).page(
        query=q, note_type=note_type, tag=tag,
        entity_type=entity_type, entity_id=entity_id, pinned=pinned,
        archived=archived, sort=sort, page=page, page_size=page_size,
    )


@router.post("", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(
    payload: NoteCreate, db: DbSession, settings: AppSettings, clock: AppClock
) -> NoteRead:
    return service(db, settings, clock).create(payload)


@router.get("/{note_id}", response_model=NoteRead)
def get_note(
    note_id: int, db: DbSession, settings: AppSettings, clock: AppClock
) -> NoteRead:
    return service(db, settings, clock).detail(note_id)


@router.patch("/{note_id}", response_model=NoteRead)
def update_note(
    note_id: int, payload: NoteUpdate,
    db: DbSession, settings: AppSettings, clock: AppClock,
) -> NoteRead:
    return service(db, settings, clock).update(note_id, payload)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: int, db: DbSession, settings: AppSettings, clock: AppClock,
    permanent: bool = False, confirmed: bool = False,
) -> Response:
    service(db, settings, clock).archive_or_delete(
        note_id, permanent=permanent, confirmed=confirmed
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{note_id}/links", response_model=NoteLinkRead, status_code=status.HTTP_201_CREATED)
def add_note_link(
    note_id: int, payload: NoteLinkCreate,
    db: DbSession, settings: AppSettings, clock: AppClock,
) -> NoteLinkRead:
    return service(db, settings, clock).add_link(note_id, payload)


@router.delete("/{note_id}/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note_link(
    note_id: int, link_id: int,
    db: DbSession, settings: AppSettings, clock: AppClock,
) -> Response:
    service(db, settings, clock).delete_link(note_id, link_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{note_id}/sources", response_model=NoteSourceRead, status_code=status.HTTP_201_CREATED)
def add_note_source(
    note_id: int, payload: NoteSourceCreate,
    db: DbSession, settings: AppSettings, clock: AppClock,
) -> NoteSourceRead:
    return service(db, settings, clock).add_source(note_id, payload)


@router.delete("/{note_id}/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note_source(
    note_id: int, source_id: int,
    db: DbSession, settings: AppSettings, clock: AppClock,
) -> Response:
    service(db, settings, clock).delete_source(note_id, source_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
