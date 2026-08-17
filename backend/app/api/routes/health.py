from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import AppClock, AppSettings, DbSession
from app.schemas.dashboard import MetaResponse

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: DbSession) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/meta", response_model=MetaResponse)
def meta(settings: AppSettings, clock: AppClock) -> MetaResponse:
    return MetaResponse(
        backend_status="connected",
        database_type="SQLite",
        upload_directory=str(settings.upload_dir.resolve()),
        allowed_file_types=list(settings.allowed_file_extensions),
        max_file_size_mb=settings.max_upload_size_mb,
        app_version=settings.app_version,
        demo_data_enabled=settings.demo_data_enabled,
        llm_configured=settings.llm_configured,
        llm_model=settings.llm_model if settings.llm_configured else None,
        embedding_model=settings.embedding_model_name,
        embedding_device=settings.embedding_device,
        embedding_local_only=settings.embedding_local_files_only,
        index_ready=settings.faiss_index_path.is_file() and settings.faiss_manifest_path.is_file(),
        index_directory=str(settings.faiss_index_path.resolve().parent),
        server_date=clock.today(),
        server_time=clock.now(),
    )
