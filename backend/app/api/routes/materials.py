from fastapi import APIRouter, File, Query, Response, UploadFile, status
from sqlalchemy import select

from app.api.deps import AppSettings, DbSession
from app.models.material import Material
from app.schemas.material import MaterialRead
from app.services.crud import commit, get_or_404
from app.services.materials import delete_material_file, save_upload

router = APIRouter(prefix="/materials", tags=["materials"])


@router.post("/upload", response_model=MaterialRead, status_code=status.HTTP_201_CREATED)
async def upload_material(
    db: DbSession, settings: AppSettings, file: UploadFile = File(...)
) -> Material:
    return await save_upload(db, file, settings)


@router.get("", response_model=list[MaterialRead])
def list_materials(
    db: DbSession,
    search: str | None = Query(default=None, max_length=100),
    source_type: str | None = Query(default=None, max_length=20),
) -> list[Material]:
    statement = select(Material)
    if search:
        statement = statement.where(Material.original_filename.ilike(f"%{search}%"))
    if source_type:
        statement = statement.where(Material.source_type == source_type)
    return list(db.scalars(statement.order_by(Material.created_at.desc())))


@router.get("/{material_id}", response_model=MaterialRead)
def get_material(material_id: int, db: DbSession) -> Material:
    return get_or_404(db, Material, material_id, "资料")


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material(material_id: int, db: DbSession) -> Response:
    material = get_or_404(db, Material, material_id, "资料")
    path = material.file_path
    db.delete(material)
    commit(db)
    delete_material_file(material)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"X-Deleted-File": path})

