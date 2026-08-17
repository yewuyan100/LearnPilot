import logging

from app.core.config import Settings
from app.core.errors import AppError
from app.services.embedding.base import Embedder
from app.services.rag.types import RagSource, RetrievalResult
from app.services.rag.reranker import (
    RerankCandidate,
    RerankerGateway,
    RerankerUnavailable,
    build_reranker_provider,
)
from app.services.vector_store.service import MaterialIndexService

logger = logging.getLogger("personal_learning.rag.retrieval")


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
    reranker_provider: RerankerGateway | None = None,
) -> RetrievalResult:
    candidate_limit = settings.rag_candidate_top_k
    try:
        response = MaterialIndexService(db, settings, embedder).search(
            query=query,
            top_k=candidate_limit,
            material_ids=material_ids,
            min_score=None,
        )
    except AppError as exc:
        if exc.code in {"index_unavailable", "index_stale", "search_unavailable"}:
            return RetrievalResult(
                query=query,
                sources=[],
                candidate_count=0,
                index_version=None,
                duration_ms=0,
                unavailable_reason=exc.code,
            )
        raise
    ranked = sorted(
        response.results,
        key=lambda item: (-item.score, item.material_id, item.chunk_index, item.chunk_id),
    )
    above_threshold = [item for item in ranked if item.score >= settings.rag_min_score]
    ordered_for_governance = above_threshold
    retrieval_mode = "dense_only"
    reranker_status = "disabled"
    reranker_device = None
    reranker_dtype = None
    reranker_batch_count = 0
    reranker_fallback_reason = None
    if settings.rag_reranker_enabled and above_threshold:
        provider = reranker_provider or build_reranker_provider(settings)
        try:
            if provider is None:
                raise RerankerUnavailable("reranker_provider_missing")
            dense_ranks = {id(item): rank for rank, item in enumerate(ranked, start=1)}
            by_identity = {
                f"{item.material_id}:{item.chunk_id}": item for item in above_threshold
            }
            batch = provider.rerank(
                query,
                [
                    RerankCandidate(
                        identity=f"{item.material_id}:{item.chunk_id}",
                        dense_rank=dense_ranks[id(item)],
                        text=item.content,
                    )
                    for item in above_threshold
                ],
            )
            ordered_for_governance = [
                by_identity[score.identity] for score in batch.scores
            ]
            retrieval_mode = "dense_rerank"
            reranker_status = "active"
            reranker_device = batch.device
            reranker_dtype = batch.dtype
            reranker_batch_count = batch.batch_count
        except RerankerUnavailable as exc:
            retrieval_mode = "dense_fallback"
            reranker_status = "degraded"
            reranker_fallback_reason = exc.reason
            logger.warning(
                "rag_reranker_degraded reason=%s candidate_count=%s",
                exc.reason,
                len(above_threshold),
            )
    unique = []
    for item in ordered_for_governance:
        if any(
            prior.material_id == item.material_id
            and abs(prior.chunk_index - item.chunk_index) <= 1
            and _substantial_overlap(prior.content, item.content)
            for prior in unique
        ):
            continue
        unique.append(item)
    per_material_cap = settings.rag_max_sources_per_material
    final_context_limit = min(top_k, settings.rag_final_context_top_k)
    selected = []
    counts: dict[int, int] = {}
    for item in unique:
        if counts.get(item.material_id, 0) >= per_material_cap:
            continue
        selected.append(item)
        counts[item.material_id] = counts.get(item.material_id, 0) + 1
        if len(selected) >= final_context_limit:
            break
    if len(selected) < final_context_limit:
        for item in unique:
            if item in selected:
                continue
            selected.append(item)
            if len(selected) >= final_context_limit:
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
        retrieved_count=response.retrieved_count,
        filtered_count=response.filtered_count,
        final_count=len(sources),
        retrieval_mode=retrieval_mode,
        reranker_status=reranker_status,
        reranker_device=reranker_device,
        reranker_dtype=reranker_dtype,
        reranker_batch_count=reranker_batch_count,
        reranker_fallback_reason=reranker_fallback_reason,
    )
