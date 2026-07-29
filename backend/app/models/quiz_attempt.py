from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import AttemptStatus


class QuizAttempt(TimestampMixin, Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_quiz_attempts_request_id"),
        Index("ix_quiz_attempts_activity_created", "activity_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("learning_activities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    learning_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submission_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=AttemptStatus.in_progress, nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    graded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    total_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    earned_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    correct_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    incorrect_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    partial_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    grading_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    grading_prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
