from typing import Protocol

from app.core.config import Settings
from app.learning.context.schemas import MaterialScopeContext
from app.services.embedding.base import Embedder
from app.services.rag.retrieval import retrieve_sources
from app.services.rag.types import RetrievalResult


class TutorRetrievalInterface(Protocol):
    """Scoped retrieval Seam used by the Tutor Module."""

    def retrieve(
        self,
        *,
        question: str,
        material_scope: MaterialScopeContext,
    ) -> RetrievalResult: ...


class ScopedTutorRetrieval:
    """Production Adapter from Effective Material Scope to the existing RAG service."""

    def __init__(self, db, settings: Settings, embedder: Embedder):
        self.db = db
        self.settings = settings
        self.embedder = embedder

    @staticmethod
    def _empty(question: str, reason: str) -> RetrievalResult:
        return RetrievalResult(
            query=question,
            sources=[],
            candidate_count=0,
            index_version=None,
            duration_ms=0,
            unavailable_reason=reason,
        )

    def retrieve(
        self,
        *,
        question: str,
        material_scope: MaterialScopeContext,
    ) -> RetrievalResult:
        if not material_scope.scoped:
            return self._empty(question, "unscoped_learning_context")
        if material_scope.empty or not material_scope.material_ids:
            return self._empty(question, "empty_material_scope")
        return retrieve_sources(
            db=self.db,
            settings=self.settings,
            embedder=self.embedder,
            query=question,
            top_k=self.settings.rag_final_context_top_k,
            material_ids=material_scope.material_ids,
        )
