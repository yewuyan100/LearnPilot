from math import ceil

from app.core.config import Settings
from app.core.errors import AppError
from app.services.embedding.base import Embedder
from app.services.rag.types import RagSource, RetrievalResult
from app.services.vector_store.service import MaterialIndexService


def _substantial_overlap(left: str, right: str) -> bool:
    a = " ".join(left.split())
    b = " ".join(right.split())
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    max_width = min(240, len(a), len(b))
    for width in range(max_width, 59, -1):
        if a[-width:] == b[:width] or b[-width:] == a[:width]:
            return True
    return False


def retrieve_sources(
    *,
    db,
    settings: Settings,
    embedder: Embedder,
    query: str,
    top_k: int,
    material_ids: list[int] | None,
) -> RetrievalResult:
    candidate_limit = min(settings.search_top_k_max, max(top_k * 3, top_k))
    try:
        response = MaterialIndexService(db, settings, embedder).search(
            query=query,
            top_k=candidate_limit,
            material_ids=material_ids,
            min_score=None,
        )
    except AppError as exc:
        if exc.code in {"index_unavailable", "index_stale", "search_unavailable"}:
            return RetrievalResult(query, [], 0, None, 0, exc.code)
        raise
    ranked = sorted(
        response.results,
        key=lambda item: (-item.score, item.material_id, item.chunk_index, item.chunk_id),
    )
    above_threshold = [item for item in ranked if item.score >= settings.rag_min_score]
    unique = []
    for item in above_threshold:
        if any(
            prior.material_id == item.material_id
            and abs(prior.chunk_index - item.chunk_index) <= 1
            and _substantial_overlap(prior.content, item.content)
            for prior in unique
        ):
            continue
        unique.append(item)
    per_material_cap = max(1, ceil(settings.rag_max_sources / 2))
    selected = []
    counts: dict[int, int] = {}
    for item in unique:
        if counts.get(item.material_id, 0) >= per_material_cap:
            continue
        selected.append(item)
        counts[item.material_id] = counts.get(item.material_id, 0) + 1
        if len(selected) >= min(top_k, settings.rag_max_sources):
            break
    if len(selected) < min(top_k, settings.rag_max_sources):
        for item in unique:
            if item in selected:
                continue
            selected.append(item)
            if len(selected) >= min(top_k, settings.rag_max_sources):
                break
    sources: list[RagSource] = []
    context_chars = 0
    for item in selected:
        content = item.content[: settings.rag_max_chunk_chars]
        remaining = settings.rag_max_context_chars - context_chars
        if remaining <= 0:
            break
        content = content[:remaining]
        if not content.strip():
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
        context_chars += len(content)
    reason = None
    if not ranked:
        reason = "no_retrieval_results"
    elif not above_threshold:
        reason = "below_score_threshold"
    elif not sources:
        reason = "empty_context"
    return RetrievalResult(
        query=query,
        sources=sources,
        candidate_count=len(ranked),
        index_version=response.index_version,
        duration_ms=response.duration_ms,
        unavailable_reason=reason,
    )
