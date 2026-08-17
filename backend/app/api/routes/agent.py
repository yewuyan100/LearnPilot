import json

from typing import Literal

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api.deps import AppSettings, DbSession, EmbedderDep, LLMProviderDep
from app.core.errors import AppError
from app.models.agent import AgentConversation
from app.schemas.agent import AgentConfirmRequest, AgentConversationContext, AgentConversationCreate, AgentConversationDetail, AgentConversationRead, AgentRunCreate, AgentRunRead, AgentStatusRead
from app.services.agent.public_errors import public_agent_error
from app.services.agent.service import AgentService
from app.services.agent.tools import READ_TOOLS, WRITE_TOOLS

router=APIRouter(prefix="/agent",tags=["learning-agent"])

def _service(request:Request,db,settings,embedder,provider):
    return AgentService(
        db, settings, embedder, provider,
        request.app.state.agent_runtime.checkpointer,
        request.app.state.clock,
    )

def _sse(event:str,data)->str:
    return f"event: {event}\ndata: {json.dumps(data,ensure_ascii=False,default=str)}\n\n"

def _events(run: AgentRunRead):
    for call in run.tool_calls:
        yield _sse("step.started", {"run_id": run.id, "kind": call.tool_kind})
        if call.status in {"completed","failed"}:
            yield _sse("step.completed", {
                "run_id": run.id,
                "kind": call.tool_kind,
                "success": bool((call.result or {}).get("success")),
                "summary": (call.result or {}).get("user_summary", ""),
            })
    if run.status=="awaiting_confirmation" and run.confirmation:
        yield _sse("approval.required",{
            **run.confirmation.model_dump(mode="json"),
            "run_id": run.id,
        })
        yield _sse("run.completed",{"run_id":run.id,"status":run.status})
        return
    if run.final_answer:
        yield _sse("answer.completed", {"run_id": run.id, "text": run.final_answer})
    if run.citations:
        yield _sse("artifact.created", {"run_id": run.id, "kind": "citations", "items": run.citations})
    if run.status=="failed":
        error = run.error or public_agent_error(run.error_code)
        yield _sse("run.failed", {"run_id": run.id, **error.model_dump()})
    yield _sse("run.completed",{"run_id":run.id,"status":run.status})

@router.get("/status",response_model=AgentStatusRead)
def agent_status(settings:AppSettings,provider:LLMProviderDep):
    return AgentStatusRead(enabled=settings.agent_enabled,checkpoint_enabled=settings.agent_checkpoint_enabled,llm_configured=provider is not None,
        model=getattr(provider,"model_name",None),max_steps=settings.agent_max_steps,read_tools=list(READ_TOOLS),write_tools=list(WRITE_TOOLS))

@router.post("/conversations",response_model=AgentConversationRead,status_code=status.HTTP_201_CREATED)
def create_conversation(payload:AgentConversationCreate,request:Request,db:DbSession,settings:AppSettings,embedder:EmbedderDep,provider:LLMProviderDep):
    return _service(request,db,settings,embedder,provider).create_conversation(payload.title, payload.context)

@router.get("/conversations",response_model=list[AgentConversationRead])
def list_conversations(request:Request,db:DbSession,settings:AppSettings,embedder:EmbedderDep,provider:LLMProviderDep,
        context_type:Literal["general","goal","material","lesson"]="general",context_id:int|None=Query(default=None,gt=0)):
    if (context_type == "general") != (context_id is None):
        raise AppError("agent_context_invalid", "会话上下文参数不完整", status.HTTP_422_UNPROCESSABLE_ENTITY)
    context = AgentConversationContext(context_type=context_type, context_id=context_id)
    return _service(request,db,settings,embedder,provider).list_conversations(context)

@router.get("/conversations/{conversation_id}",response_model=AgentConversationDetail)
def get_conversation(conversation_id:int,request:Request,db:DbSession,settings:AppSettings,embedder:EmbedderDep,provider:LLMProviderDep):
    return _service(request,db,settings,embedder,provider).detail(conversation_id)

@router.post("/conversations/{conversation_id}/archive",response_model=AgentConversationRead)
def archive_conversation(conversation_id:int,request:Request,db:DbSession,settings:AppSettings,embedder:EmbedderDep,provider:LLMProviderDep):
    return _service(request,db,settings,embedder,provider).archive(conversation_id)

@router.post("/conversations/{conversation_id}/runs",response_model=AgentRunRead,status_code=status.HTTP_202_ACCEPTED)
def create_run(conversation_id:int,payload:AgentRunCreate,request:Request,db:DbSession,settings:AppSettings,embedder:EmbedderDep,provider:LLMProviderDep):
    conversation=db.get(AgentConversation,conversation_id); key=conversation.thread_id if conversation else str(conversation_id)
    with request.app.state.agent_runtime.lock(key):
        return _service(request,db,settings,embedder,provider).start_run(conversation_id,payload.input,payload.request_id)

@router.post("/conversations/{conversation_id}/runs/stream")
def stream_run(conversation_id:int,payload:AgentRunCreate,request:Request,db:DbSession,settings:AppSettings,embedder:EmbedderDep,provider:LLMProviderDep):
    def generate():
        yield _sse("run.started", {"request_id": payload.request_id})
        try:
            run = create_run(conversation_id,payload,request,db,settings,embedder,provider)
            yield from _events(run)
        except Exception as exc:
            error = public_agent_error(getattr(exc, "code", "agent_execution_failed"))
            yield _sse("run.failed", error.model_dump())
    return StreamingResponse(generate(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@router.get("/runs/{run_id}",response_model=AgentRunRead)
def get_run(run_id:int,request:Request,db:DbSession,settings:AppSettings,embedder:EmbedderDep,provider:LLMProviderDep):
    return _service(request,db,settings,embedder,provider).get_run(run_id)

@router.post("/runs/{run_id}/confirm",response_model=AgentRunRead)
def confirm_run(run_id:int,payload:AgentConfirmRequest,request:Request,db:DbSession,settings:AppSettings,embedder:EmbedderDep,provider:LLMProviderDep):
    service=_service(request,db,settings,embedder,provider); run=service.get_run(run_id); conversation=db.get(AgentConversation,run.conversation_id)
    with request.app.state.agent_runtime.lock(conversation.thread_id):
        return service.confirm(run_id,payload.decision)

@router.post("/runs/{run_id}/confirm/stream")
def stream_confirm(run_id:int,payload:AgentConfirmRequest,request:Request,db:DbSession,settings:AppSettings,embedder:EmbedderDep,provider:LLMProviderDep):
    def generate():
        yield _sse("run.started", {"run_id": run_id, "resume": True})
        try:
            run = confirm_run(run_id,payload,request,db,settings,embedder,provider)
            yield from _events(run)
        except Exception as exc:
            error = public_agent_error(getattr(exc, "code", "agent_resume_failed"))
            yield _sse("run.failed", {"run_id": run_id, **error.model_dump()})
    return StreamingResponse(generate(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})
