from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LearningEvent(Base):
    """Append-only record of a learning runtime fact that already occurred."""

    __tablename__ = "learning_events"
    __table_args__ = (
        CheckConstraint("schema_version >= 1", name="schema_version_positive"),
        Index("ix_learning_events_aggregate", "aggregate_type", "aggregate_id"),
        Index("ix_learning_events_correlation", "correlation_id", "occurred_at"),
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(default=1, nullable=False)
    actor_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    causation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    harness_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("harness_runs.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
