from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AgentConversation(TimestampMixin, Base):
    __tablename__ = "agent_conversations"
    __table_args__ = (
        CheckConstraint(
            "(context_type = 'general' AND context_id IS NULL) OR "
            "(context_type IN ('goal', 'material', 'lesson') AND context_id IS NOT NULL)",
            name="ck_agent_conversation_context_valid",
        ),
        Index("ix_agent_conversations_context", "context_type", "context_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    thread_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    context_type: Mapped[str] = mapped_column(String(16), default="general", nullable=False)
    context_id: Mapped[int | None] = mapped_column(nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AgentMessage(TimestampMixin, Base):
    __tablename__ = "agent_messages"
    __table_args__ = (Index("ix_agent_messages_conversation_created", "conversation_id", "created_at", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("agent_conversations.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


class AgentRun(TimestampMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("conversation_id", "request_id", name="uq_agent_runs_conversation_request"),
        Index("ix_agent_runs_conversation_created", "conversation_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    harness_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("harness_runs.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    conversation_id: Mapped[int] = mapped_column(ForeignKey("agent_conversations.id", ondelete="CASCADE"), index=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="accepted", index=True)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_versions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    citations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AgentToolCall(TimestampMixin, Base):
    __tablename__ = "agent_tool_calls"
    __table_args__ = (
        UniqueConstraint("run_id", "step_index", name="uq_agent_tool_calls_run_step"),
        Index("ix_agent_tool_calls_run_created", "run_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    step_index: Mapped[int] = mapped_column(nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    arguments: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    arguments_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)


class AgentConfirmation(TimestampMixin, Base):
    __tablename__ = "agent_confirmations"
    __table_args__ = (UniqueConstraint("run_id", name="uq_agent_confirmations_run_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    tool_call_id: Mapped[int] = mapped_column(ForeignKey("agent_tool_calls.id", ondelete="CASCADE"), index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    arguments_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    arguments_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
