from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import DailyTaskStatus


class DailyTask(TimestampMixin, Base):
    __tablename__ = "daily_tasks"
    __table_args__ = (
        CheckConstraint("estimated_minutes >= 1", name="estimated_minutes_positive"),
    )

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
    activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_activities.id", ondelete="SET NULL"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    task_type: Mapped[str] = mapped_column(String(32), default="learning", nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(default=20, nullable=False)
    scheduled_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=DailyTaskStatus.pending, nullable=False, index=True
    )
