from math import ceil
from time import perf_counter
import logging

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.clock import clock_from_settings
from app.core.errors import AppError
from app.models.rag_citation import RagCitation
from app.models.rag_conversation import RagConversation
from app.models.rag_message import RagMessage
from app.repositories.rag import RagRepository
from app.schemas.rag import (
    RagAnswerResponse,
    RagCitationRead,
    RagConversationDetail,
    RagConversationPage,
    RagConversationRead,
    RagMessageRead,
    RagModelSummary,
    RagRetrievalSummary,
)
from app.services.embedding.base import Embedder
from app.services.llm.base import LLMProvider
from app.services.llm.errors import LLMError
from app.services.rag.grounding import (
    GroundedAnswerInvalidError,
    generate_grounded_answer,
)
from app.services.rag.query_rewriter import rewrite_query
from app.services.rag.retrieval import retrieve_sources
from app.services.rag.reranker import RerankerGateway, build_reranker_provider
from app.services.rag.types import RagSource, RetrievalResult
from app.services.rag.validation import is_prompt_injection_request
from app.services.material_learning import MaterialScopeResolver

REFUSAL_TEXT = "当前资料不足以可靠回答这个问题。请补充相关资料，或缩小问题范围后重试。"
logger = logging.getLogger("personal_learning.rag")


class RagConversationService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        embedder: Embedder,
        provider: LLMProvider | None,
        reranker_provider: RerankerGateway | None = None,
    ):
        self.db = db
        self.settings = settings
        self.embedder = embedder
        self.provider = provider
        self.reranker_provider = (
            reranker_provider
            if reranker_provider is not None
            else build_reranker_provider(settings)
        )
        self.clock = clock_from_settings(settings)
        self.repo = RagRepository(db, self.clock)

    def create_conversation(
        self, *, title: str, default_top_k: int | None
    ) -> RagConversation:
        if default_top_k is not None and default_top_k > self.settings.rag_top_k_max:
            raise AppError(
                "top_k_too_large",
                f"top_k 不能超过 {self.settings.rag_top_k_max}",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        conversation = RagConversation(
            title=title.strip(),
            status="active",
            default_top_k=default_top_k,
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def list_conversations(
        self, *, page: int, page_size: int, status_filter: str | None
    ) -> RagConversationPage:
        items, total = self.repo.list_conversations(
            status_filter=status_filter,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return RagConversationPage(
            items=[RagConversationRead.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=ceil(total / page_size) if total else 0,
        )

    def detail(
        self, conversation_id: int, *, page: int = 1, page_size: int = 100
    ) -> RagConversationDetail:
        conversation = self.repo.get_conversation(conversation_id)
        messages, total = self.repo.messages(
            conversation_id,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        base = RagConversationRead.model_validate(conversation).model_dump()
        return RagConversationDetail(
            **base,
            messages=[self._message_read(item) for item in messages],
            message_total=total,
            message_page=page,
            message_page_size=page_size,
            message_pages=ceil(total / page_size) if total else 0,
        )

    def archive(self, conversation_id: int) -> RagConversation:
        conversation = self.repo.get_conversation(conversation_id)
        conversation.status = "archived"
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def ask(
        self,
        *,
        conversation_id: int,
        question: str,
        request_id: str,
        top_k: int | None,
        material_ids: list[int] | None,
        learning_goal_id: int | None = None,
        course_id: int | None = None,
        knowledge_point_id: int | None = None,
    ) -> RagAnswerResponse:
        conversation = self.repo.get_conversation(conversation_id)
        if conversation.status != "active":
            raise AppError(
                "rag_conversation_archived",
                "该资料问答会话已归档",
                status.HTTP_409_CONFLICT,
            )
        scope = MaterialScopeResolver(self.db).resolve_combined_scope(
            learning_goal_id=learning_goal_id,
            course_id=course_id,
            knowledge_point_id=knowledge_point_id,
            material_ids=material_ids,
            searchable_only=True,
        )
        existing = self.repo.find_by_request(conversation_id, request_id)
        if existing is not None:
            if (
                existing.original_query != question
                or existing.retrieval_scope.get("requested_scope") != scope.requested_scope
            ):
                raise AppError(
                    "request_id_conflict",
                    "相同 request_id 已用于其他问题",
                    status.HTTP_409_CONFLICT,
                )
            return self._response_for(existing, idempotent_replay=True)
        resolved_top_k = (
            top_k
            or conversation.default_top_k
            or self.settings.rag_final_context_top_k
        )
        if resolved_top_k > self.settings.rag_top_k_max:
            raise AppError(
                "top_k_too_large",
                f"top_k 不能超过 {self.settings.rag_top_k_max}",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        history_rows = self.repo.recent_completed_messages(
            conversation_id, limit=self.settings.rag_history_messages
        )
        history = [(item.role, item.content) for item in history_rows]
        rewrite = rewrite_query(
            question=question,
            history=history,
            settings=self.settings,
            provider=self.provider,
        )
        if scope.empty:
            retrieval = RetrievalResult(
                query=rewrite.query,
                sources=[],
                candidate_count=0,
                index_version=None,
                duration_ms=0,
                unavailable_reason="empty_material_scope",
            )
        else:
            retrieval = retrieve_sources(
                db=self.db,
                settings=self.settings,
                embedder=self.embedder,
                query=rewrite.query,
                top_k=resolved_top_k,
                material_ids=scope.resolved_material_ids,
                reranker_provider=self.reranker_provider,
            )
        scope_record = {
            "requested_scope": scope.requested_scope,
            "resolved_material_ids": scope.resolved_material_ids,
            "scoped": scope.scoped,
            "retrieved_count": retrieval.retrieved_count,
            "filtered_count": retrieval.filtered_count,
            "final_count": retrieval.final_count,
            "retrieval_mode": retrieval.retrieval_mode,
            "reranker_status": retrieval.reranker_status,
            "reranker_device": retrieval.reranker_device,
            "reranker_dtype": retrieval.reranker_dtype,
            "reranker_batch_count": retrieval.reranker_batch_count,
            "reranker_fallback_reason": retrieval.reranker_fallback_reason,
        }
        user = RagMessage(
            conversation_id=conversation_id,
            role="user",
            content=question,
            status="completed",
            original_query=question,
        )
        assistant = RagMessage(
            conversation_id=conversation_id,
            role="assistant",
            content="",
            status="pending",
            request_id=request_id,
            original_query=question,
            retrieval_query=rewrite.query,
            retrieval_scope=scope_record,
            prompt_version=self.settings.rag_prompt_version,
        )
        self.db.add(user)
        self.db.flush()
        assistant.reply_to_message_id = user.id
        self.db.add(assistant)
        self.repo.touch(conversation)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            existing = self.repo.find_by_request(conversation_id, request_id)
            if existing is not None:
                return self._response_for(existing, idempotent_replay=True)
            raise

        started = perf_counter()
        fallback_used = False
        if is_prompt_injection_request(question):
            self._apply_refusal(assistant, "prompt_injection_request")
        elif not retrieval.sources:
            self._apply_refusal(
                assistant,
                retrieval.unavailable_reason or "insufficient_sources",
            )
        elif self.provider is None:
            assistant.status = "failed"
            assistant.error_message = "LLM 尚未配置"
            self.db.commit()
            raise AppError(
                "llm_not_configured",
                "已找到相关资料，但 LLM 尚未配置，无法生成回答",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        else:
            try:
                grounded = generate_grounded_answer(
                    provider=self.provider,
                    question=question,
                    sources=retrieval.sources,
                )
                answer = grounded.answer
                fallback_used = grounded.repair_attempted
                assistant.model_name = grounded.model_name
                assistant.input_tokens = grounded.usage.input_tokens
                assistant.output_tokens = grounded.usage.output_tokens
                if not answer.answerable:
                    self._apply_refusal(
                        assistant, answer.refusal_reason or "model_reported_insufficient"
                    )
                else:
                    assistant.content = answer.answer_markdown.strip()
                    assistant.status = "completed"
                    assistant.answerable = True
                    self._add_citations(
                        assistant,
                        retrieval.sources,
                        answer.cited_source_ids,
                        scope_record,
                    )
            except GroundedAnswerInvalidError as exc:
                logger.info(
                    "rag_grounding_failed initial_reason=%s final_reason=%s",
                    exc.initial_reason,
                    exc.reason,
                )
                self._apply_refusal(assistant, "grounded_answer_invalid")
                fallback_used = True
            except LLMError as exc:
                assistant.status = "failed"
                assistant.error_message = exc.code
                self.db.commit()
                raise AppError(
                    exc.code,
                    "模型服务暂时不可用，请稍后重试",
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                ) from exc
        assistant.latency_ms = round((perf_counter() - started) * 1000)
        self.db.commit()
        self.db.refresh(user)
        self.db.refresh(assistant)
        response = self._build_response(
            user=user,
            assistant=assistant,
            retrieval=retrieval,
            top_k=resolved_top_k,
            fallback_used=fallback_used,
            idempotent_replay=False,
        )
        logger.info(
            "rag_request_completed conversation_id=%s request_id=%s answerable=%s "
            "refusal_reason=%s resolved_material_count=%s retrieved_count=%s "
            "filtered_count=%s final_count=%s retrieval_mode=%s reranker_status=%s "
            "reranker_device=%s reranker_fallback_reason=%s retrieval_duration_ms=%s "
            "total_duration_ms=%s",
            conversation_id,
            request_id,
            assistant.answerable,
            assistant.refusal_reason,
            len(scope.resolved_material_ids or []),
            retrieval.retrieved_count,
            retrieval.filtered_count,
            retrieval.final_count,
            retrieval.retrieval_mode,
            retrieval.reranker_status,
            retrieval.reranker_device,
            retrieval.reranker_fallback_reason,
            retrieval.duration_ms,
            assistant.latency_ms,
        )
        return response

    @staticmethod
    def _apply_refusal(assistant: RagMessage, reason: str) -> None:
        assistant.content = REFUSAL_TEXT
        assistant.status = "completed"
        assistant.answerable = False
        assistant.refusal_reason = reason

    def _add_citations(
        self,
        assistant: RagMessage,
        sources: list[RagSource],
        source_ids: list[str],
        scope_record: dict,
    ) -> None:
        by_id = {source.source_label: source for source in sources}
        source_ids = list(dict.fromkeys(source_ids))
        unknown = [source_id for source_id in source_ids if source_id not in by_id]
        if unknown:
            raise ValueError(f"citation sources were not retrieved: {unknown}")
        material_contexts = MaterialScopeResolver(self.db).material_link_contexts(
            [source.material_id for source in sources]
        )
        for source_id in source_ids:
            source = by_id[source_id]
            self.db.add(
                RagCitation(
                    assistant_message_id=assistant.id,
                    source_label=source.source_label,
                    chunk_id=source.chunk_id,
                    material_id=source.material_id,
                    rank=source.rank,
                    score=source.score,
                    original_filename=source.original_filename,
                    chunk_index=source.chunk_index,
                    page_number=source.page_number,
                    section_title=source.section_title,
                    content_excerpt=source.content[
                        : self.settings.rag_citation_excerpt_chars
                    ],
                    learning_context={
                        "requested_scope": scope_record.get("requested_scope", {}),
                        "material_links": material_contexts.get(source.material_id, []),
                    },
                )
            )

    def _message_read(self, message: RagMessage) -> RagMessageRead:
        citations = self.repo.citations(message.id) if message.role == "assistant" else []
        return RagMessageRead(
            id=message.id,
            conversation_id=message.conversation_id,
            reply_to_message_id=message.reply_to_message_id,
            role=message.role,
            content=message.content,
            status=message.status,
            request_id=message.request_id,
            original_query=message.original_query,
            retrieval_query=message.retrieval_query,
            retrieval_scope=message.retrieval_scope or {},
            answerable=message.answerable,
            refusal_reason=message.refusal_reason,
            prompt_version=message.prompt_version,
            model_name=message.model_name,
            latency_ms=message.latency_ms,
            created_at=message.created_at,
            updated_at=message.updated_at,
            citations=[
                RagCitationRead(
                    id=item.id,
                    source_label=item.source_label,
                    chunk_id=item.chunk_id,
                    material_id=item.material_id,
                    rank=item.rank,
                    score=item.score,
                    original_filename=item.original_filename,
                    chunk_index=item.chunk_index,
                    page_number=item.page_number,
                    section_title=item.section_title,
                    content_excerpt=item.content_excerpt,
                    source_available=item.chunk_id is not None
                    and item.material_id is not None,
                    learning_context=item.learning_context or {},
                    created_at=item.created_at,
                )
                for item in citations
            ],
        )

    def _response_for(
        self, assistant: RagMessage, *, idempotent_replay: bool
    ) -> RagAnswerResponse:
        user = self.db.get(RagMessage, assistant.reply_to_message_id)
        assert user is not None
        citations = self.repo.citations(assistant.id)
        return RagAnswerResponse(
            conversation_id=assistant.conversation_id,
            user_message=self._message_read(user),
            assistant_message=self._message_read(assistant),
            retrieval=RagRetrievalSummary(
                query=assistant.retrieval_query or assistant.original_query or "",
                top_k=0,
                candidate_count=len(citations),
                source_count=len(citations),
                min_score=self.settings.rag_min_score,
                index_version=None,
                duration_ms=0,
                requested_scope=assistant.retrieval_scope.get("requested_scope", {}),
                resolved_material_ids=assistant.retrieval_scope.get("resolved_material_ids"),
                retrieved_count=assistant.retrieval_scope.get("retrieved_count", 0),
                filtered_count=assistant.retrieval_scope.get("filtered_count", 0),
                final_count=assistant.retrieval_scope.get("final_count", len(citations)),
                retrieval_mode=assistant.retrieval_scope.get(
                    "retrieval_mode", "dense_only"
                ),
                reranker_status=assistant.retrieval_scope.get(
                    "reranker_status", "disabled"
                ),
                reranker_device=assistant.retrieval_scope.get("reranker_device"),
                reranker_dtype=assistant.retrieval_scope.get("reranker_dtype"),
                reranker_batch_count=assistant.retrieval_scope.get(
                    "reranker_batch_count", 0
                ),
                reranker_fallback_reason=assistant.retrieval_scope.get(
                    "reranker_fallback_reason"
                ),
            ),
            model=RagModelSummary(
                provider=self.settings.llm_provider,
                model=assistant.model_name,
                fallback_used=assistant.refusal_reason
                in {"llm_output_invalid", "citation_validation_failed"},
            ),
            idempotent_replay=idempotent_replay,
        )

    def _build_response(
        self,
        *,
        user: RagMessage,
        assistant: RagMessage,
        retrieval: RetrievalResult,
        top_k: int,
        fallback_used: bool,
        idempotent_replay: bool,
    ) -> RagAnswerResponse:
        return RagAnswerResponse(
            conversation_id=assistant.conversation_id,
            user_message=self._message_read(user),
            assistant_message=self._message_read(assistant),
            retrieval=RagRetrievalSummary(
                query=retrieval.query,
                top_k=top_k,
                candidate_count=retrieval.candidate_count,
                source_count=len(retrieval.sources),
                min_score=self.settings.rag_min_score,
                index_version=retrieval.index_version,
                duration_ms=retrieval.duration_ms,
                requested_scope=assistant.retrieval_scope.get("requested_scope", {}),
                resolved_material_ids=assistant.retrieval_scope.get("resolved_material_ids"),
                retrieved_count=retrieval.retrieved_count,
                filtered_count=retrieval.filtered_count,
                final_count=retrieval.final_count,
                retrieval_mode=retrieval.retrieval_mode,
                reranker_status=retrieval.reranker_status,
                reranker_device=retrieval.reranker_device,
                reranker_dtype=retrieval.reranker_dtype,
                reranker_batch_count=retrieval.reranker_batch_count,
                reranker_fallback_reason=retrieval.reranker_fallback_reason,
            ),
            model=RagModelSummary(
                provider=self.settings.llm_provider,
                model=assistant.model_name,
                fallback_used=fallback_used,
            ),
            idempotent_replay=idempotent_replay,
        )
