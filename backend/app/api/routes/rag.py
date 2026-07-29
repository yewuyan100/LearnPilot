import json
from collections.abc import Iterator

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import StreamingResponse

from app.api.deps import AppSettings, DbSession, EmbedderDep, LLMProviderDep
from app.schemas.rag import (
    RagAnswerResponse,
    RagAskRequest,
    RagConversationCreate,
    RagConversationDetail,
    RagConversationPage,
    RagConversationRead,
    RagStatus,
)
from app.services.rag.service import RagConversationService
from app.services.vector_store.service import MaterialIndexService

router = APIRouter(prefix="/rag", tags=["rag"])


def service(db, settings, embedder, provider) -> RagConversationService:
    return RagConversationService(db, settings, embedder, provider)


@router.post(
    "/conversations",
    response_model=RagConversationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    payload: RagConversationCreate,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
):
    return service(db, settings, embedder, provider).create_conversation(
        title=payload.title,
        default_top_k=payload.default_top_k,
    )


@router.get("/conversations", response_model=RagConversationPage)
def list_conversations(
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
):
    return service(db, settings, embedder, provider).list_conversations(
        page=page, page_size=page_size, status_filter=status_filter
    )


@router.get("/conversations/{conversation_id}", response_model=RagConversationDetail)
def get_conversation(
    conversation_id: int,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
):
    return service(db, settings, embedder, provider).detail(
        conversation_id, page=page, page_size=page_size
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
def archive_conversation(
    conversation_id: int,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
) -> Response:
    service(db, settings, embedder, provider).archive(conversation_id)
    return Response(status_code=204)


@router.post(
    "/conversations/{conversation_id}/ask", response_model=RagAnswerResponse
)
def ask(
    conversation_id: int,
    payload: RagAskRequest,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
) -> RagAnswerResponse:
    return service(db, settings, embedder, provider).ask(
        conversation_id=conversation_id,
        question=payload.question,
        request_id=payload.request_id,
        top_k=payload.top_k,
        material_ids=payload.material_ids,
    )


def _event(name: str, data: object) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/conversations/{conversation_id}/stream")
def stream_answer(
    conversation_id: int,
    payload: RagAskRequest,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
) -> StreamingResponse:
    def generate() -> Iterator[str]:
        yield _event("accepted", {"request_id": payload.request_id})
        try:
            result = service(db, settings, embedder, provider).ask(
                conversation_id=conversation_id,
                question=payload.question,
                request_id=payload.request_id,
                top_k=payload.top_k,
                material_ids=payload.material_ids,
            )
            yield _event("retrieval", result.retrieval.model_dump(mode="json"))
            yield _event(
                "message_start", {"message_id": result.assistant_message.id}
            )
            content = result.assistant_message.content
            for index in range(0, len(content), 36):
                yield _event("delta", {"text": content[index : index + 36]})
            yield _event(
                "citations",
                {
                    "items": [
                        citation.model_dump(mode="json")
                        for citation in result.assistant_message.citations
                    ]
                },
            )
            yield _event(
                "done",
                {
                    "message_id": result.assistant_message.id,
                    "idempotent_replay": result.idempotent_replay,
                },
            )
        except Exception as exc:
            code = getattr(exc, "code", "stream_error")
            message = getattr(exc, "message", "资料问答暂时不可用")
            yield _event("error", {"code": code, "message": message})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/status", response_model=RagStatus)
def rag_status(
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
) -> RagStatus:
    index = MaterialIndexService(db, settings, embedder).status()
    return RagStatus(
        llm_configured=settings.llm_configured,
        provider=settings.llm_provider,
        model=settings.llm_model,
        index_available=index.available,
        index_stale=index.stale,
        index_version=index.index_version,
        rag_prompt_version=settings.rag_prompt_version,
        rewrite_prompt_version=settings.rag_rewrite_prompt_version,
    )
