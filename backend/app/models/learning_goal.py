from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import GoalStatus


class LearningGoal(TimestampMixin, Base):
    __tablename__ = "learning_goals"
    __table_args__ = (
        CheckConstraint("daily_minutes >= 5 AND daily_minutes <= 1440", name="daily_minutes_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    daily_minutes: Mapped[int] = mapped_column(default=30, nullable=False)
    current_level: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=GoalStatus.active, nullable=False, index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
