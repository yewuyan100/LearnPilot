from math import ceil

from fastapi import APIRouter, File, Query, Response, UploadFile, status
from sqlalchemy import select

from app.api.deps import AppClock, AppSettings, DbSession, EmbedderDep
from app.core.errors import AppError
from app.models.material import Material
from app.repositories.material_chunks import MaterialChunkRepository
from app.repositories.materials import MaterialRepository
from app.schemas.material import MaterialArchiveBulkRequest, MaterialArchiveBulkResult, MaterialRead
from app.schemas.material_chunk import (
    MaterialChunkPage,
    MaterialIndexBuildResult,
    MaterialIndexStatus,
    MaterialSearchRequest,
    MaterialSearchResponse,
)
from app.services.crud import commit
from app.services.material_processing.pipeline import MaterialProcessingPipeline
from app.services.materials import save_upload
from app.services.material_deletion import MaterialDeletionService
from app.services.vector_store.service import MaterialIndexService


router = APIRouter(prefix="/materials", tags=["materials"])


@router.post("/upload", response_model=MaterialRead, status_code=status.HTTP_201_CREATED)
async def upload_material(
    db: DbSession,
    settings: AppSettings,
    file: UploadFile = File(...),
) -> Material:
    return await save_upload(db, file, settings)


@router.post("/search", response_model=MaterialSearchResponse)
def search_materials(
    payload: MaterialSearchRequest,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
) -> MaterialSearchResponse:
    top_k = payload.top_k or settings.search_top_k_default
    if top_k > settings.search_top_k_max:
        raise AppError(
            "top_k_too_large",
            f"top_k 不能超过 {settings.search_top_k_max}",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return MaterialIndexService(db, settings, embedder).search(
        query=payload.query,
        top_k=top_k,
        material_ids=payload.material_ids,
        min_score=payload.min_score,
    )


@router.post("/index/rebuild", response_model=MaterialIndexBuildResult)
def rebuild_material_index(
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
) -> MaterialIndexBuildResult:
    return MaterialIndexService(db, settings, embedder).rebuild()


@router.get("/index/status", response_model=MaterialIndexStatus)
def material_index_status(
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
) -> MaterialIndexStatus:
    return MaterialIndexService(db, settings, embedder).status()


@router.get("", response_model=list[MaterialRead])
def list_materials(
    db: DbSession,
    search: str | None = Query(default=None, max_length=100),
    source_type: str | None = Query(default=None, max_length=20),
) -> list[Material]:
    return MaterialRepository(db).list(search, source_type)


@router.post("/archive/bulk", response_model=MaterialArchiveBulkResult)
def archive_materials_bulk(
    payload: MaterialArchiveBulkRequest, db: DbSession, clock: AppClock
) -> MaterialArchiveBulkResult:
    unique_ids = list(dict.fromkeys(payload.material_ids))
    materials = list(db.scalars(select(Material).where(Material.id.in_(unique_ids))))
    found = {material.id for material in materials}
    missing = set(unique_ids).difference(found)
    if missing:
        raise AppError(
            "material_not_found", "One or more materials do not exist.",
            status.HTTP_404_NOT_FOUND, {"material_ids": sorted(missing)},
        )
    for material in materials:
        material.archived_at = clock.now()
    commit(db)
    return MaterialArchiveBulkResult(archived_ids=unique_ids)


@router.post("/{material_id}/archive", response_model=MaterialRead)
def archive_material(material_id: int, db: DbSession, clock: AppClock) -> Material:
    material = MaterialRepository(db).get(material_id)
    material.archived_at = clock.now()
    return commit(db, material)


@router.post("/{material_id}/unarchive", response_model=MaterialRead)
def unarchive_material(material_id: int, db: DbSession) -> Material:
    material = MaterialRepository(db).get(material_id)
    material.archived_at = None
    return commit(db, material)


@router.post("/{material_id}/process", response_model=MaterialRead)
def process_material(
    material_id: int,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
) -> Material:
    MaterialProcessingPipeline(db, settings).process(material_id)
    MaterialIndexService(db, settings, embedder).rebuild()
    return MaterialRepository(db).get(material_id)


@router.get("/{material_id}/chunks", response_model=MaterialChunkPage)
def list_material_chunks(
    material_id: int,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> MaterialChunkPage:
    MaterialRepository(db).get(material_id)
    items, total = MaterialChunkRepository(db).page_for_material(
        material_id,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return MaterialChunkPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if total else 0,
    )


@router.get("/{material_id}", response_model=MaterialRead)
def get_material(material_id: int, db: DbSession) -> Material:
    return MaterialRepository(db).get(material_id)


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material(
    material_id: int,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    clock: AppClock,
) -> Response:
    result = MaterialDeletionService(db, settings, embedder, clock).delete(material_id)
    details = result.get("result") or {}
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={
            "X-Deleted-File": str(details.get("file_path", "")),
            "X-Index-Result": str(details.get("index_result", "rebuilt")),
        },
    )


@router.post("/{material_id}/delete/retry")
def retry_material_delete(
    material_id: int,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    clock: AppClock,
) -> dict:
    return MaterialDeletionService(db, settings, embedder, clock).delete(material_id)
