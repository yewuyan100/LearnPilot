import logging
from math import ceil

from fastapi import APIRouter, File, Query, Response, UploadFile, status

from app.api.deps import AppSettings, DbSession, EmbedderDep
from app.core.errors import AppError
from app.models.material import Material
from app.repositories.material_chunks import MaterialChunkRepository
from app.repositories.materials import MaterialRepository
from app.schemas.material import MaterialRead
from app.schemas.material_chunk import (
    MaterialChunkPage,
    MaterialIndexBuildResult,
    MaterialIndexStatus,
    MaterialSearchRequest,
    MaterialSearchResponse,
)
from app.services.crud import commit
from app.services.material_processing.pipeline import MaterialProcessingPipeline
from app.services.materials import delete_material_file, save_upload
from app.services.vector_store.service import MaterialIndexService


logger = logging.getLogger("personal_learning.materials_api")
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
) -> Response:
    material = MaterialRepository(db).get(material_id)
    path = material.file_path
    db.delete(material)
    commit(db)
    delete_material_file(material)

    index_result = "rebuilt"
    try:
        MaterialIndexService(db, settings, embedder).rebuild()
    except AppError as exc:
        index_result = "stale"
        logger.warning(
            "material_deleted_index_rebuild_failed material_id=%s error_code=%s",
            material_id,
            exc.code,
        )
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={
            "X-Deleted-File": path,
            "X-Index-Result": index_result,
        },
    )
