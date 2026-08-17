from collections import Counter
import logging
from threading import Lock
from time import perf_counter
from uuid import uuid4

from fastapi import status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.clock import clock_from_settings
from app.core.errors import AppError
from app.repositories.material_chunks import MaterialChunkRepository
from app.repositories.materials import MaterialRepository
from app.schemas.material_chunk import (
    MaterialIndexBuildResult,
    MaterialIndexStatus,
    MaterialSearchResponse,
    MaterialSearchResult,
)
from app.services.embedding.base import Embedder, EmbeddingError
from app.services.vector_store.faiss_store import FaissStore, VectorStoreError
from app.services.vector_store.manifest import FaissManifest, chunks_checksum
from app.services.material_state import touch_material


logger = logging.getLogger("personal_learning.knowledge_index")
INDEX_BUILD_LOCK = Lock()


class MaterialIndexService:
    def __init__(self, db: Session, settings: Settings, embedder: Embedder):
        self.db = db
        self.settings = settings
        self.embedder = embedder
        self.clock = clock_from_settings(settings)
        self.materials = MaterialRepository(db)
        self.chunks = MaterialChunkRepository(db)
        self.store = FaissStore(
            settings.faiss_index_path,
            settings.faiss_manifest_path,
        )

    @staticmethod
    def is_building() -> bool:
        return INDEX_BUILD_LOCK.locked()

    def rebuild(self) -> MaterialIndexBuildResult:
        if not INDEX_BUILD_LOCK.acquire(blocking=False):
            raise AppError(
                "index_build_in_progress",
                "资料索引正在构建，请稍后重试。",
                status.HTTP_409_CONFLICT,
            )
        started = perf_counter()
        materials = self.materials.list_ingested()
        try:
            chunks = self.chunks.list_indexable()
            if not chunks:
                self.store.clear()
                now = self.clock.now()
                for material in materials:
                    material.indexing_status = "completed"
                    material.indexed_chunk_count = 0
                    material.indexed_at = now
                    material.error_message = None
                    touch_material(material, now)
                self.db.commit()
                return MaterialIndexBuildResult(
                    index_version=None,
                    chunk_count=0,
                    model_name=self.settings.embedding_model_name,
                    embedding_dimension=None,
                    built_at=now,
                )

            indexing_started_at = self.clock.now()
            for material in materials:
                material.indexing_status = "indexing"
                material.error_message = None
                touch_material(material, indexing_started_at)
            self.db.commit()

            vectors = self.embedder.embed_documents([chunk.content for chunk in chunks])
            built_at = self.clock.now()
            manifest = FaissManifest(
                index_version=uuid4().hex,
                model_name=self.embedder.model_name,
                model_revision=self.embedder.model_revision,
                embedding_dimension=int(vectors.shape[1]),
                normalized=self.embedder.normalized,
                chunk_count=len(chunks),
                chunk_ids=[chunk.id for chunk in chunks],
                built_at=built_at,
                content_checksum=chunks_checksum(chunks),
            )
            manifest = self.store.save(vectors, manifest)

            counts = Counter(chunk.material_id for chunk in chunks)
            for material in materials:
                material.indexing_status = "completed"
                material.indexed_chunk_count = counts.get(material.id, 0)
                material.indexed_at = built_at
                material.error_message = None
                touch_material(material, built_at)
            self.db.commit()
            logger.info(
                "material_index_built embedding_model=%s embedding_dimension=%s "
                "index_chunk_count=%s index_version=%s index_build_duration_ms=%s",
                manifest.model_name,
                manifest.embedding_dimension,
                manifest.chunk_count,
                manifest.index_version,
                round((perf_counter() - started) * 1000),
            )
            return MaterialIndexBuildResult(
                index_version=manifest.index_version,
                chunk_count=manifest.chunk_count,
                model_name=manifest.model_name,
                embedding_dimension=manifest.embedding_dimension,
                built_at=manifest.built_at,
            )
        except Exception as exc:
            self.db.rollback()
            for material in self.materials.list_ingested():
                material.indexing_status = "failed"
                material.error_message = (
                    str(exc)
                    if isinstance(exc, (EmbeddingError, VectorStoreError))
                    else "资料索引构建失败，请查看后端日志。"
                )
                touch_material(material, self.clock.now())
            self.db.commit()
            logger.exception(
                "material_index_build_failed error_type=%s index_build_duration_ms=%s",
                type(exc).__name__,
                round((perf_counter() - started) * 1000),
            )
            if isinstance(exc, (EmbeddingError, VectorStoreError)):
                raise AppError(
                    "index_build_failed",
                    str(exc),
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                ) from exc
            raise AppError(
                "index_build_failed",
                "资料索引构建失败，请查看后端日志。",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ) from exc
        finally:
            INDEX_BUILD_LOCK.release()

    def status(self) -> MaterialIndexStatus:
        chunks = self.chunks.list_indexable()
        try:
            manifest = self.store.read_manifest()
            if manifest is None:
                return MaterialIndexStatus(
                    available=False,
                    building=self.is_building(),
                    model_name=self.settings.embedding_model_name,
                    embedding_dimension=None,
                    chunk_count=0,
                    built_at=None,
                    index_version=None,
                    stale=bool(chunks),
                    error_message=None,
                )
            _, manifest = self.store.load(
                model_name=self.settings.embedding_model_name,
                model_revision=self.settings.embedding_model_revision,
                normalized=self.settings.embedding_normalize,
            )
            assert manifest is not None
            return MaterialIndexStatus(
                available=manifest.chunk_count > 0,
                building=self.is_building(),
                model_name=manifest.model_name,
                embedding_dimension=manifest.embedding_dimension,
                chunk_count=manifest.chunk_count,
                built_at=manifest.built_at,
                index_version=manifest.index_version,
                stale=manifest.content_checksum != chunks_checksum(chunks),
                error_message=None,
            )
        except VectorStoreError as exc:
            return MaterialIndexStatus(
                available=False,
                building=self.is_building(),
                model_name=self.settings.embedding_model_name,
                embedding_dimension=None,
                chunk_count=0,
                built_at=None,
                index_version=None,
                stale=True,
                error_message=str(exc),
            )

    def search(
        self,
        *,
        query: str,
        top_k: int,
        material_ids: list[int] | None,
        min_score: float | None,
    ) -> MaterialSearchResponse:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise AppError(
                "empty_search_query",
                "检索问题不能为空。",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if material_ids is not None:
            for material_id in sorted(set(material_ids)):
                self.materials.get(material_id)

        started = perf_counter()
        try:
            manifest = self.store.read_manifest()
            if manifest is None:
                raise AppError(
                    "index_unavailable",
                    "尚未建立可用的资料索引，请先处理资料或重建索引。",
                    status.HTTP_409_CONFLICT,
                )
            if manifest.content_checksum != chunks_checksum(
                self.chunks.list_indexable()
            ):
                raise AppError(
                    "index_stale",
                    "资料内容与当前索引不一致，请先重新构建索引。",
                    status.HTTP_409_CONFLICT,
                )
            query_vector = self.embedder.embed_query(cleaned_query)
            candidate_limit = max(manifest.chunk_count, top_k)
            hits, manifest = self.store.search(
                query_vector,
                candidate_limit,
                model_name=self.embedder.model_name,
                model_revision=self.embedder.model_revision,
                normalized=self.embedder.normalized,
            )
            rows = self.chunks.get_search_rows(
                [hit.chunk_id for hit in hits],
                material_ids,
            )
            retrieved_count = len(hits)
            filtered_count = len(hits) - len(rows)
            candidates = [
                (hit, rows[hit.chunk_id])
                for hit in hits
                if hit.chunk_id in rows
                and (min_score is None or hit.score >= min_score)
            ]
            candidates.sort(key=lambda item: (-item[0].score, item[0].chunk_id))
            candidates = candidates[:top_k]
            duration_ms = round((perf_counter() - started) * 1000)
            results = [
                MaterialSearchResult(
                    rank=rank,
                    score=hit.score,
                    chunk_id=chunk.id,
                    material_id=material.id,
                    original_filename=material.original_filename,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    page_number=chunk.page_number,
                    section_title=chunk.section_title,
                )
                for rank, (hit, (chunk, material)) in enumerate(candidates, start=1)
            ]
            logger.info(
                "material_search embedding_model=%s index_version=%s search_top_k=%s "
                "result_count=%s search_duration_ms=%s",
                manifest.model_name,
                manifest.index_version,
                top_k,
                len(results),
                duration_ms,
            )
            return MaterialSearchResponse(
                query=cleaned_query,
                model_name=manifest.model_name,
                index_version=manifest.index_version,
                results=results,
                duration_ms=duration_ms,
                retrieved_count=retrieved_count,
                filtered_count=filtered_count,
            )
        except AppError:
            raise
        except (EmbeddingError, VectorStoreError) as exc:
            raise AppError(
                "search_unavailable",
                str(exc),
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from exc
