from datetime import date

from sqlalchemy import Date, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AdaptiveRecommendation(TimestampMixin, Base):
    __tablename__ = "adaptive_recommendations"
    __table_args__ = (
        Index("ix_adaptive_recommendations_status_date", "status", "suggested_date", "id"),
        Index("ix_adaptive_recommendations_point_status", "knowledge_point_id", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_type: Mapped[str] = mapped_column(String(32), default="review_task", nullable=False)
    knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_details_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    suggested_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    suggested_minutes: Mapped[int] = mapped_column(nullable=False)
    source_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("mastery_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    created_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("daily_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
