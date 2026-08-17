from math import ceil

from fastapi import status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, not_found
from app.models.knowledge_point import KnowledgePoint
from app.models.knowledge_point_source import KnowledgePointSource
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.schemas.knowledge_point_source import (
    KnowledgePointSourceCreate,
    KnowledgePointSourceRead,
    SourceChunkPage,
    SourceChunkRead,
)
from app.services.material_learning import MaterialScopeResolver


class KnowledgePointSourceService:
    """Validate and maintain auditable evidence for a knowledge point."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        knowledge_point_id: int,
        payload: KnowledgePointSourceCreate,
        *,
        commit: bool = True,
    ) -> KnowledgePointSourceRead:
        point = self._get_point(knowledge_point_id)
        material = self._get_material(payload.material_id)
        effective_ids = set(
            MaterialScopeResolver(self.db).resolve_effective_material_ids(
                "knowledge_point", knowledge_point_id, searchable_only=False
            )
        )
        if material.id not in effective_ids:
            raise AppError(
                "knowledge_point_source_material_out_of_scope",
                "Link the material to this learning branch before adding it as a source.",
                status.HTTP_409_CONFLICT,
                {"knowledge_point_id": knowledge_point_id, "material_id": material.id},
            )
        chunk = None
        if payload.material_chunk_id is not None:
            chunk = self.db.get(MaterialChunk, payload.material_chunk_id)
            if chunk is None:
                raise not_found("material chunk", payload.material_chunk_id)
            if chunk.material_id != material.id:
                raise AppError(
                    "knowledge_point_source_chunk_mismatch",
                    "The selected chunk does not belong to the selected material.",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    {
                        "material_id": material.id,
                        "material_chunk_id": chunk.id,
                        "chunk_material_id": chunk.material_id,
                    },
                )
            existing = self.db.scalar(
                select(KnowledgePointSource).where(
                    KnowledgePointSource.knowledge_point_id == point.id,
                    KnowledgePointSource.material_chunk_id == chunk.id,
                )
            )
            if existing is not None:
                return self._serialize(existing, point, material, chunk)
        else:
            existing = self.db.scalar(
                select(KnowledgePointSource).where(
                    KnowledgePointSource.knowledge_point_id == point.id,
                    KnowledgePointSource.material_id == material.id,
                    KnowledgePointSource.material_chunk_id.is_(None),
                    KnowledgePointSource.source_type == payload.source_type,
                    KnowledgePointSource.source_locator == payload.source_locator,
                )
            )
            if existing is not None:
                return self._serialize(existing, point, material, None)

        source = KnowledgePointSource(
            knowledge_point_id=point.id,
            material_id=material.id,
            material_chunk_id=chunk.id if chunk else None,
            source_type=payload.source_type,
            source_locator=payload.source_locator or self._locator(chunk),
            quoted_text=payload.quoted_text or (chunk.content[:4000] if chunk else None),
            note=payload.note,
        )
        self.db.add(source)
        if commit:
            self.db.commit()
            self.db.refresh(source)
        else:
            self.db.flush()
        return self._serialize(source, point, material, chunk)

    def list(self, knowledge_point_id: int) -> list[KnowledgePointSourceRead]:
        point = self._get_point(knowledge_point_id)
        rows = self.db.execute(
            select(KnowledgePointSource, Material, MaterialChunk)
            .join(Material, Material.id == KnowledgePointSource.material_id)
            .outerjoin(MaterialChunk, MaterialChunk.id == KnowledgePointSource.material_chunk_id)
            .where(KnowledgePointSource.knowledge_point_id == knowledge_point_id)
            .order_by(KnowledgePointSource.created_at.desc(), KnowledgePointSource.id.desc())
        ).all()
        return [self._serialize(source, point, material, chunk) for source, material, chunk in rows]

    def delete(self, knowledge_point_id: int, source_id: int) -> None:
        self._get_point(knowledge_point_id)
        source = self.db.scalar(
            select(KnowledgePointSource).where(
                KnowledgePointSource.id == source_id,
                KnowledgePointSource.knowledge_point_id == knowledge_point_id,
            )
        )
        if source is None:
            raise not_found("knowledge point source", source_id)
        self.db.delete(source)
        self.db.commit()

    def search_chunks(
        self,
        knowledge_point_id: int,
        material_id: int,
        search: str | None,
        page: int,
        page_size: int,
    ) -> SourceChunkPage:
        self._get_point(knowledge_point_id)
        material = self._get_material(material_id)
        effective_ids = set(
            MaterialScopeResolver(self.db).resolve_effective_material_ids(
                "knowledge_point", knowledge_point_id, searchable_only=False
            )
        )
        if material_id not in effective_ids:
            raise AppError(
                "knowledge_point_source_material_out_of_scope",
                "The selected material is not visible to this knowledge point.",
                status.HTTP_409_CONFLICT,
            )
        filters = [MaterialChunk.material_id == material_id]
        if search and search.strip():
            term = f"%{search.strip()}%"
            filters.append(
                or_(MaterialChunk.content.ilike(term), MaterialChunk.section_title.ilike(term))
            )
        total = self.db.scalar(
            select(func.count(MaterialChunk.id)).where(*filters)
        ) or 0
        chunks = list(
            self.db.scalars(
                select(MaterialChunk)
                .where(*filters)
                .order_by(MaterialChunk.chunk_index)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        indexes = [item.chunk_index for item in chunks]
        neighbor_rows = {}
        if indexes:
            neighbor_rows = {
                item.chunk_index: item.id
                for item in self.db.scalars(
                    select(MaterialChunk).where(
                        MaterialChunk.material_id == material_id,
                        MaterialChunk.chunk_index.in_(
                            set(index - 1 for index in indexes) | set(index + 1 for index in indexes)
                        ),
                    )
                )
            }
        return SourceChunkPage(
            items=[
                SourceChunkRead(
                    id=chunk.id,
                    material_id=material.id,
                    material_title=material.title,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    page_number=chunk.page_number,
                    section_title=chunk.section_title,
                    source_locator=self._locator(chunk) or f"Chunk {chunk.chunk_index + 1}",
                    previous_chunk_id=neighbor_rows.get(chunk.chunk_index - 1),
                    next_chunk_id=neighbor_rows.get(chunk.chunk_index + 1),
                )
                for chunk in chunks
            ],
            total=total,
            page=page,
            page_size=page_size,
            pages=ceil(total / page_size) if total else 0,
        )

    def _get_point(self, point_id: int) -> KnowledgePoint:
        point = self.db.get(KnowledgePoint, point_id)
        if point is None:
            raise not_found("knowledge point", point_id)
        return point

    def _get_material(self, material_id: int) -> Material:
        material = self.db.get(Material, material_id)
        if material is None:
            raise not_found("material", material_id)
        if material.deletion_status != "active":
            raise AppError(
                "material_unavailable",
                "A material pending deletion cannot be used as a source.",
                status.HTTP_409_CONFLICT,
            )
        return material

    @staticmethod
    def _locator(chunk: MaterialChunk | None) -> str | None:
        if chunk is None:
            return None
        if chunk.page_number is not None:
            return f"Page {chunk.page_number}, chunk {chunk.chunk_index + 1}"
        if chunk.section_title:
            return f"{chunk.section_title}, chunk {chunk.chunk_index + 1}"
        return f"Chunk {chunk.chunk_index + 1}"

    def _serialize(
        self,
        source: KnowledgePointSource,
        point: KnowledgePoint,
        material: Material,
        chunk: MaterialChunk | None,
    ) -> KnowledgePointSourceRead:
        query = f"?chunk={chunk.id}" if chunk else ""
        return KnowledgePointSourceRead(
            id=source.id,
            knowledge_point_id=point.id,
            knowledge_point_title=point.title,
            material_id=material.id,
            material_title=material.title,
            original_filename=material.original_filename,
            material_chunk_id=chunk.id if chunk else None,
            chunk_index=chunk.chunk_index if chunk else None,
            source_type=source.source_type,
            source_locator=source.source_locator,
            quoted_text=source.quoted_text,
            note=source.note,
            source_available=material.deletion_status == "active" and (
                source.material_chunk_id is None or chunk is not None
            ),
            context_url=f"/materials/{material.id}{query}",
            created_at=source.created_at,
            updated_at=source.updated_at,
        )
