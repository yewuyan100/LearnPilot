from collections.abc import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.material import Material
from app.models.material_chunk import MaterialChunk


class MaterialChunkRepository:
    def __init__(self, db: Session):
        self.db = db

    def replace_for_material(
        self,
        material_id: int,
        chunks: Iterable[MaterialChunk],
    ) -> list[MaterialChunk]:
        self.db.execute(
            delete(MaterialChunk).where(MaterialChunk.material_id == material_id)
        )
        items = list(chunks)
        self.db.add_all(items)
        self.db.flush()
        return items

    def count_for_material(self, material_id: int) -> int:
        return (
            self.db.scalar(
                select(func.count())
                .select_from(MaterialChunk)
                .where(MaterialChunk.material_id == material_id)
            )
            or 0
        )

    def page_for_material(
        self,
        material_id: int,
        offset: int,
        limit: int,
    ) -> tuple[list[MaterialChunk], int]:
        total = self.count_for_material(material_id)
        items = list(
            self.db.scalars(
                select(MaterialChunk)
                .where(MaterialChunk.material_id == material_id)
                .order_by(MaterialChunk.chunk_index)
                .offset(offset)
                .limit(limit)
            )
        )
        return items, total

    def list_indexable(self) -> list[MaterialChunk]:
        return list(
            self.db.scalars(
                select(MaterialChunk)
                .join(Material, Material.id == MaterialChunk.material_id)
                .where(
                    Material.ingestion_status == "completed",
                    Material.deletion_status == "active",
                )
                .order_by(MaterialChunk.id)
            )
        )

    def get_search_rows(
        self,
        chunk_ids: list[int],
        material_ids: list[int] | None = None,
    ) -> dict[int, tuple[MaterialChunk, Material]]:
        if not chunk_ids:
            return {}
        statement = (
            select(MaterialChunk, Material)
            .join(Material, Material.id == MaterialChunk.material_id)
            .where(
                MaterialChunk.id.in_(chunk_ids),
                Material.ingestion_status == "completed",
                Material.deletion_status == "active",
                Material.archived_at.is_(None),
            )
        )
        if material_ids is not None:
            statement = statement.where(Material.id.in_(material_ids))
        return {
            chunk.id: (chunk, material)
            for chunk, material in self.db.execute(statement)
        }
