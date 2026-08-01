import json

from fastapi import APIRouter, Request, status
from fastapi.responses import StreamingResponse

from app.api.deps import AppSettings, DbSession, EmbedderDep, LLMProviderDep
from app.models.agent import AgentConversation
from app.schemas.agent import AgentConfirmRequest, AgentConversationCreate, AgentConversationDetail, AgentConversationRead, AgentRunCreate, AgentRunRead, AgentStatusRead
from app.services.agent.service import AgentService
from app.services.agent.tools import READ_TOOLS, WRITE_TOOLS

router=APIRouter(prefix="/agent",tags=["learning-agent"])

def _service(request:Request,db,settings,embedder,provider):
    return AgentService(db,settings,embedder,provider,request.app.state.agent_runtime.checkpointer)

def _sse(event:str,data)->str:
    return f"event: {event}\ndata: {json.dumps(data,ensure_ascii=False,default=str)}\n\n"

def _events(run:AgentRunRead,chunk_chars:int):
    yield _sse("accepted",{"run_id":run.id,"status":run.status})
    yield _sse("status",{"run_id":run.id,"status":run.status})
    for call in run.tool_calls:
        yield _sse("tool_start",{"tool":call.tool_name,"kind":call.tool_kind})
        if call.status in {"completed","failed"}:
            yield _sse("tool_result",{"tool":call.tool_name,"success":bool((call.result or {}).get("success")),"user_summary":(call.result or {}).get("user_summary","")})
    if run.status=="awaiting_confirmation" and run.confirmation:
        yield _sse("confirmation_required",run.confirmation.model_dump(mode="json")); yield _sse("done",{"run_id":run.id,"status":run.status}); return
    yield _sse("message_start",{"run_id":run.id})
    text=run.final_answer or ""
    for start in range(0,len(text),chunk_chars): yield _sse("delta",{"text":text[start:start+chunk_chars]})
    if run.citations: yield _sse("citations",run.citations)
    if run.status=="failed": yield _sse("error",{"code":run.error_code or "agent_failed","message":text})
    yield _sse("done",{"run_id":run.id,"status":run.status})

@router.get("/status",response_model=AgentStatusRead)
def agent_status(settings:AppSettings,provider:LLMProviderDep):
    return AgentStatusRead(enabled=settings.agent_enabled,checkpoint_enabled=settings.agent_checkpoint_enabled,llm_configured=provider is not None,
        model=getattr(provider,"model_name",None),max_steps=settings.agent_max_steps,read_tools=list(READ_TOOLS),write_tools=list(WRITE_TOOLS))

@router.post("/conversations",response_model=AgentConversationRead,status_code=status.HTTP_201_CREATED)
def create_conversation(payload:AgentConversationCreate,request:Request,db:DbSession,settings:AppSettings,embedder:EmbedderDep,provider:LLMProviderDep):
    return _service(request,db,settings,embedder,provider).create_conversation(payload.title)

@router.get("/conversations",response_model=list[AgentConversationRead])
def list_conversations(request:Request,db:DbSession,settings:AppSettings,embedder:EmbedderDep,provider:LLMProviderDep):
    return _service(request,db,settings,embedder,provider).list_conversations()

@router.get("/conversations/{conversation_id}",response_model=AgentConversationDetail)
def get_conversation(conversation_id:int,request:Request,db:DbSession,settings:AppSettings,embedder:EmbedderDep,provider:LLMProviderDep):
    return _service(request,db,settings,embedder,provider).detail(conversation_id)

@router.post("/conversations/{conversation_id}/archive",response_model=AgentConversationRead)
def archive_conversation(conversation_id:int,request:Request,db:DbSession,settings:AppSettings,embedder:EmbedderDep,provider:LLMProviderDep):
    return _service(request,db,settings,embedder,provider).archive(conversation_id)

@router.post("/conversations/{conversation_id}/runs",response_model=AgentRunRead,status_code=status.HTTP_202_ACCEPTED)
async def create_run(conversation_id:int,payload:AgentRunCreate,request:Request,db:DbSession,settings:AppSettings,embedder:EmbedderDep,provider:LLMProviderDep):
    conversation=db.get(AgentConversation,conversation_id); key=conversation.thread_id if conversation else str(conversation_id)
    async with request.app.state.agent_runtime.lock(key):
        return _service(request,db,settings,embedder,provider).start_run(conversation_id,payload.input,payload.request_id)

@router.post("/conversations/{conversation_id}/runs/stream")
async def stream_run(conversation_id:int,payload:AgentRunCreate,request:Request,db:DbSession,settings:AppSettings,embedder:EmbedderDep,provider:LLMProviderDep):
    run=await create_run(conversation_id,payload,request,db,settings,embedder,provider)
    return StreamingResponse(_events(run,settings.agent_stream_chunk_chars),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@router.get("/runs/{run_id}",response_model=AgentRunRead)
def get_run(run_id:int,request:Request,db:DbSession,settings:AppSettings,embedder:EmbedderDep,provider:LLMProviderDep):
    return _service(request,db,settings,embedder,provider).get_run(run_id)

@router.post("/runs/{run_id}/confirm",response_model=AgentRunRead)
async def confirm_run(run_id:int,payload:AgentConfirmRequest,request:Request,db:DbSession,settings:AppSettings,embedder:EmbedderDep,provider:LLMProviderDep):
    service=_service(request,db,settings,embedder,provider); run=service.get_run(run_id); conversation=db.get(AgentConversation,run.conversation_id)
    async with request.app.state.agent_runtime.lock(conversation.thread_id): return service.confirm(run_id,payload.decision)

@router.post("/runs/{run_id}/confirm/stream")
async def stream_confirm(run_id:int,payload:AgentConfirmRequest,request:Request,db:DbSession,settings:AppSettings,embedder:EmbedderDep,provider:LLMProviderDep):
    run=await confirm_run(run_id,payload,request,db,settings,embedder,provider)
    return StreamingResponse(_events(run,settings.agent_stream_chunk_chars),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})
