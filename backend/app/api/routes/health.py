from datetime import date, datetime

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import AppSettings, DbSession
from app.schemas.dashboard import MetaResponse

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: DbSession) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/meta", response_model=MetaResponse)
def meta(settings: AppSettings) -> MetaResponse:
    return MetaResponse(
        backend_status="connected",
        database_type="SQLite",
        upload_directory=str(settings.upload_dir.resolve()),
        allowed_file_types=list(settings.allowed_file_extensions),
        max_file_size_mb=settings.max_upload_size_mb,
        app_version=settings.app_version,
        demo_data_enabled=settings.demo_data_enabled,
        server_date=date.today(),
        server_time=datetime.now(),
    )

