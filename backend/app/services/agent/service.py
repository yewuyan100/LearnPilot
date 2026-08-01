from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4
import logging

from fastapi import status
from langgraph.types import Command
from sqlalchemy import select

from app.core.errors import AppError
from app.models.agent import AgentConfirmation, AgentConversation, AgentMessage, AgentRun, AgentToolCall
from app.schemas.agent import (
    AgentConfirmationRead, AgentConversationDetail, AgentConversationRead,
    AgentMessageRead, AgentRunRead, AgentToolCallRead,
)
from app.services.agent.graph import GraphContext, build_graph
from app.services.agent.tools import ToolRegistry

logger = logging.getLogger("personal_learning.agent")


class AgentService:
    def __init__(self, db, settings, embedder, provider, checkpointer):
        self.db, self.settings, self.embedder, self.provider = db, settings, embedder, provider
        self.checkpointer = checkpointer

    def _conversation(self, conversation_id: int) -> AgentConversation:
        row = self.db.get(AgentConversation, conversation_id)
        if row is None:
            raise AppError("agent_conversation_not_found", "学习助手会话不存在", status.HTTP_404_NOT_FOUND)
        return row

    def create_conversation(self, title: str) -> AgentConversationRead:
        row = AgentConversation(title=title.strip(), status="active", thread_id=uuid4().hex)
        self.db.add(row); self.db.commit(); self.db.refresh(row)
        return AgentConversationRead.model_validate(row, from_attributes=True)

    def list_conversations(self) -> list[AgentConversationRead]:
        rows = self.db.scalars(select(AgentConversation).order_by(AgentConversation.updated_at.desc(), AgentConversation.id.desc())).all()
        return [AgentConversationRead.model_validate(x, from_attributes=True) for x in rows]

    def detail(self, conversation_id: int) -> AgentConversationDetail:
        row = self._conversation(conversation_id)
        messages = self.db.scalars(select(AgentMessage).where(AgentMessage.conversation_id == row.id).order_by(AgentMessage.created_at, AgentMessage.id)).all()
        base = AgentConversationRead.model_validate(row, from_attributes=True).model_dump()
        return AgentConversationDetail(**base, messages=[AgentMessageRead.model_validate(x, from_attributes=True) for x in messages])

    def archive(self, conversation_id: int) -> AgentConversationRead:
        row = self._conversation(conversation_id); row.status="archived"; self.db.commit(); self.db.refresh(row)
        return AgentConversationRead.model_validate(row, from_attributes=True)

    def start_run(self, conversation_id: int, user_input: str, request_id: str) -> AgentRunRead:
        conversation = self._conversation(conversation_id)
        if conversation.status != "active":
            raise AppError("agent_conversation_archived", "该会话已归档", status.HTTP_409_CONFLICT)
        digest = sha256(user_input.strip().encode()).hexdigest()
        existing = self.db.scalar(select(AgentRun).where(AgentRun.conversation_id == conversation_id, AgentRun.request_id == request_id))
        if existing:
            if existing.input_hash != digest:
                raise AppError("request_id_conflict", "相同 request_id 已用于不同请求", status.HTTP_409_CONFLICT)
            return self.serialize_run(existing, idempotent=True)
        pending = self.db.scalar(select(AgentRun).where(
            AgentRun.conversation_id == conversation_id,
            AgentRun.status == "awaiting_confirmation",
        ))
        if pending is not None:
            raise AppError(
                "agent_confirmation_pending",
                "请先处理当前待确认操作，再发送新的请求",
                status.HTTP_409_CONFLICT,
            )
        now = datetime.now(timezone.utc)
        run = AgentRun(conversation_id=conversation_id, request_id=request_id, input_text=user_input.strip(), input_hash=digest,
            status="accepted", started_at=now, prompt_versions={"classification":self.settings.agent_classification_prompt_version,
            "planning":self.settings.agent_planning_prompt_version,"response":self.settings.agent_response_prompt_version})
        self.db.add(run); self.db.flush()
        self.db.add(AgentMessage(conversation_id=conversation_id, run_id=run.id, role="user", content=user_input.strip(), citations=[]))
        conversation.last_message_at=now; self.db.commit(); self.db.refresh(run)
        initial = {"conversation_id":conversation_id,"run_id":run.id,"thread_id":conversation.thread_id,"request_id":request_id,
            "user_input":user_input.strip(),"history":[],"plan":[],"current_step":0,"completed_steps":[],"tool_results":[],
            "errors":[],"citations":[],"status":"accepted","step_count":0,"max_steps":self.settings.agent_max_steps,
            "fast_route_used":False,"planner_skipped":False,"composer_skipped":True,"llm_call_count":0}
        graph = build_graph(GraphContext(self.db,self.settings,self.provider,ToolRegistry(self.db,self.settings,self.embedder,self.provider)), self.checkpointer)
        try:
            graph.invoke(initial, config={"configurable":{"thread_id":conversation.thread_id},"recursion_limit":self.settings.agent_recursion_limit})
        except Exception:
            logger.exception("agent_run_failed run_id=%s", run.id)
            self.db.rollback(); run=self.db.get(AgentRun,run.id); run.status="failed"; run.error_code="agent_execution_failed"; run.completed_at=datetime.now(timezone.utc); self.db.commit()
        return self.serialize_run(self.db.get(AgentRun, run.id))

    def confirm(self, run_id: int, decision: str) -> AgentRunRead:
        run = self.db.get(AgentRun, run_id)
        if run is None: raise AppError("agent_run_not_found", "Agent 运行不存在", status.HTTP_404_NOT_FOUND)
        confirmation = self.db.scalar(select(AgentConfirmation).where(AgentConfirmation.run_id == run_id))
        if confirmation is None: raise AppError("confirmation_not_found", "该运行没有待确认操作", status.HTTP_409_CONFLICT)
        approved = decision == "approve"
        if confirmation.status != "pending":
            if confirmation.approved == approved: return self.serialize_run(run, idempotent=True)
            raise AppError("confirmation_already_decided", "该确认已作出相反决定", status.HTTP_409_CONFLICT)
        expires = confirmation.expires_at
        if expires.tzinfo is None: expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            confirmation.status="expired"; run.status="failed"; run.error_code="confirmation_expired"; self.db.commit()
            raise AppError("confirmation_expired", "确认已过期", status.HTTP_409_CONFLICT)
        call=self.db.get(AgentToolCall,confirmation.tool_call_id)
        if call.arguments_hash != confirmation.arguments_hash or call.arguments != confirmation.arguments_snapshot:
            raise AppError("confirmation_snapshot_mismatch", "待确认参数已变化，已拒绝执行", status.HTTP_409_CONFLICT)
        confirmation.approved=approved; confirmation.status="approved" if approved else "rejected"; confirmation.decided_at=datetime.now(timezone.utc); self.db.commit()
        conversation=self._conversation(run.conversation_id)
        graph=build_graph(GraphContext(self.db,self.settings,self.provider,ToolRegistry(self.db,self.settings,self.embedder,self.provider)),self.checkpointer)
        try:
            graph.invoke(Command(resume=decision), config={"configurable":{"thread_id":conversation.thread_id},"recursion_limit":self.settings.agent_recursion_limit})
        except Exception:
            logger.exception("agent_resume_failed run_id=%s", run_id)
            self.db.rollback(); run=self.db.get(AgentRun,run_id); run.status="failed"; run.error_code="agent_resume_failed"; run.completed_at=datetime.now(timezone.utc); self.db.commit()
        return self.serialize_run(self.db.get(AgentRun,run_id))

    def get_run(self, run_id: int) -> AgentRunRead:
        run=self.db.get(AgentRun,run_id)
        if run is None: raise AppError("agent_run_not_found","Agent 运行不存在",status.HTTP_404_NOT_FOUND)
        return self.serialize_run(run)

    def serialize_run(self, run: AgentRun, idempotent: bool=False) -> AgentRunRead:
        calls=self.db.scalars(select(AgentToolCall).where(AgentToolCall.run_id==run.id).order_by(AgentToolCall.step_index)).all()
        confirmation=self.db.scalar(select(AgentConfirmation).where(AgentConfirmation.run_id==run.id))
        confirmation_read=None
        if confirmation:
            call=next((x for x in calls if x.id==confirmation.tool_call_id),None)
            confirmation_read=AgentConfirmationRead(id=confirmation.id,summary=confirmation.summary,tool_name=call.tool_name if call else "",
                arguments=confirmation.arguments_snapshot,status=confirmation.status,expires_at=confirmation.expires_at)
        performance = dict((run.prompt_versions or {}).get("performance") or {})
        if run.started_at and run.completed_at:
            started = run.started_at.replace(tzinfo=timezone.utc) if run.started_at.tzinfo is None else run.started_at
            completed = run.completed_at.replace(tzinfo=timezone.utc) if run.completed_at.tzinfo is None else run.completed_at
            performance["total_latency_ms"] = round((completed - started).total_seconds() * 1000)
        performance["tool_latency_ms"] = sum(x.duration_ms or 0 for x in calls)
        return AgentRunRead(id=run.id,conversation_id=run.conversation_id,request_id=run.request_id,input=run.input_text,status=run.status,
            intent=run.intent,final_answer=run.final_answer,citations=run.citations or [],error_code=run.error_code,idempotent_replay=idempotent,
            confirmation=confirmation_read,performance=performance,tool_calls=[AgentToolCallRead(id=x.id,step_index=x.step_index,tool_name=x.tool_name,tool_kind=x.tool_kind,
            arguments=x.arguments,status=x.status,result=x.result,duration_ms=x.duration_ms) for x in calls],created_at=run.created_at,updated_at=run.updated_at)
