from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class HarnessRun(TimestampMixin, Base):
    """One top-level LearningRuntime request lifecycle and its audit summary."""

    __tablename__ = "harness_runs"
    __table_args__ = (
        UniqueConstraint("public_id", name="uq_harness_runs_public_id"),
        UniqueConstraint("actor_key", "request_id", name="uq_harness_runs_actor_request"),
        CheckConstraint(
            "status IN ('accepted','running','awaiting_confirmation','completed','failed')",
            name="status_valid",
        ),
        Index("ix_harness_runs_actor_status", "actor_key", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    actor_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("agent_conversations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    surface_context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    context_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    selected_agent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="accepted", nullable=False, index=True)
    result_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    citations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
