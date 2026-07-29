from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import ActivityStatus


class LearningActivity(TimestampMixin, Base):
    __tablename__ = "learning_activities"
    __table_args__ = (
        Index("ix_learning_activities_created", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    activity_type: Mapped[str] = mapped_column(String(32), default="quiz", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=ActivityStatus.draft, nullable=False, index=True
    )
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    knowledge_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_scope: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_points: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    generation_request_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    generation_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    validation_warnings: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
