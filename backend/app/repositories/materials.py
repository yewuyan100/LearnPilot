from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.models.material import Material


class MaterialRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, material_id: int) -> Material:
        material = self.db.get(Material, material_id)
        if material is None:
            raise not_found("资料", material_id)
        return material

    def list(
        self,
        search: str | None = None,
        source_type: str | None = None,
    ) -> list[Material]:
        statement = select(Material)
        if search:
            statement = statement.where(Material.original_filename.ilike(f"%{search}%"))
        if source_type:
            statement = statement.where(Material.source_type == source_type)
        return list(self.db.scalars(statement.order_by(Material.created_at.desc())))

    def list_ingested(self) -> list[Material]:
        return list(
            self.db.scalars(
                select(Material)
                .where(Material.ingestion_status == "completed")
                .order_by(Material.id)
            )
        )
