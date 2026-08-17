from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import KnowledgePointStatus


class KnowledgePoint(TimestampMixin, Base):
    __tablename__ = "knowledge_points"
    __table_args__ = (
        UniqueConstraint(
            "course_id",
            "order_index",
            name="uq_knowledge_points_course_order",
        ),
        CheckConstraint("estimated_minutes >= 1", name="estimated_minutes_positive"),
        CheckConstraint(
            "lifecycle_status IN ('active','archived','superseded')",
            name="lifecycle_status_valid",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    order_index: Mapped[int] = mapped_column(default=0, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(default=20, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=KnowledgePointStatus.not_started, nullable=False, index=True
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(32), default="active", server_default="active", nullable=False, index=True
    )
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    lifecycle_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)


class KnowledgePointLifecycleChange(TimestampMixin, Base):
    """Durable idempotency and audit record for one lifecycle transition."""

    __tablename__ = "knowledge_point_lifecycle_changes"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_knowledge_point_lifecycle_changes_request_id"),
        CheckConstraint("resulting_version >= 1", name="resulting_version_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    request_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    arguments_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="RESTRICT"), nullable=True
    )
    expected_version: Mapped[int] = mapped_column(Integer, nullable=False)
    resulting_version: Mapped[int] = mapped_column(Integer, nullable=False)
    impact_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
