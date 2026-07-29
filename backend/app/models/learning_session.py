from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import LearningSessionStatus


class LearningSession(TimestampMixin, Base):
    __tablename__ = "learning_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    learning_goal_id: Mapped[int] = mapped_column(
        ForeignKey("learning_goals.id", ondelete="CASCADE"), index=True, nullable=False
    )
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), index=True, nullable=True
    )
    knowledge_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="SET NULL"), index=True, nullable=True
    )
    daily_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("daily_tasks.id", ondelete="SET NULL"), index=True, nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=LearningSessionStatus.active, nullable=False, index=True
    )
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

