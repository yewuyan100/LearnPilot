from app.core.config import Settings
from app.core.errors import AppError
from app.models.material import Material
from app.services.embedding.base import Embedder
from app.services.rag.types import RagSource
from app.services.vector_store.service import MaterialIndexService
from fastapi import status
from sqlalchemy.orm import Session


def _overlaps(left: str, right: str) -> bool:
    a = " ".join(left.lower().split())
    b = " ".join(right.lower().split())
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return False
    return len(tokens_a & tokens_b) / min(len(tokens_a), len(tokens_b)) >= 0.85


def retrieve_activity_sources(
    *,
    db: Session,
    settings: Settings,
    embedder: Embedder,
    query: str,
    material_ids: list[int] | None,
) -> list[RagSource]:
    if material_ids:
        materials = [db.get(Material, material_id) for material_id in material_ids]
        if any(material is None for material in materials):
            missing = material_ids[materials.index(None)]
            raise AppError(
                "material_not_found",
                "资料不存在",
                status.HTTP_404_NOT_FOUND,
                {"id": missing},
            )
        unusable = [
            material.id
            for material in materials
            if material.ingestion_status != "completed"
            or material.indexing_status != "completed"
        ]
        if unusable:
            raise AppError(
                "material_not_indexed",
                "所选资料尚未完成解析和索引",
                status.HTTP_409_CONFLICT,
                {"material_ids": unusable},
            )
    candidate_count = min(
        settings.search_top_k_max,
        max(settings.activity_max_sources * 3, settings.activity_max_sources),
    )
    response = MaterialIndexService(db, settings, embedder).search(
        query=query,
        top_k=candidate_count,
        material_ids=material_ids,
        min_score=None,
    )
    ranked = sorted(
        response.results,
        key=lambda item: (-item.score, item.material_id, item.chunk_index, item.chunk_id),
    )
    selected = []
    for item in ranked:
        if item.score < settings.rag_min_score:
            continue
        if any(_overlaps(item.content, prior.content) for prior in selected):
            continue
        selected.append(item)
        if len(selected) >= settings.activity_max_sources:
            break
    sources: list[RagSource] = []
    used_chars = 0
    for item in selected:
        remaining = settings.activity_max_context_chars - used_chars
        if remaining <= 0:
            break
        content = item.content[: settings.activity_max_chunk_chars][:remaining].strip()
        if not content:
            continue
        sources.append(
            RagSource(
                source_label=f"S{len(sources) + 1}",
                rank=len(sources) + 1,
                score=item.score,
                chunk_id=item.chunk_id,
                material_id=item.material_id,
                original_filename=item.original_filename,
                chunk_index=item.chunk_index,
                content=content,
                page_number=item.page_number,
                section_title=item.section_title,
            )
        )
        used_chars += len(content)
    if not sources:
        raise AppError(
            "insufficient_source_evidence",
            "当前资料范围没有足够可靠的片段用于生成题目",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return sources
