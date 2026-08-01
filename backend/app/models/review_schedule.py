from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ReviewSchedule(TimestampMixin, Base):
    __tablename__ = "review_schedules"
    __table_args__ = (
        Index("ix_review_schedules_point_status", "knowledge_point_id", "status"),
        Index("ix_review_schedules_status_due", "status", "due_at", "id"),
        Index(
            "uq_review_schedules_active_point", "knowledge_point_id", unique=True,
            sqlite_where=text("status IN ('pending','scheduled')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    priority_score: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason_summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("mastery_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    completed_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("daily_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
