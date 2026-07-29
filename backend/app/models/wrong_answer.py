from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import WrongAnswerStatus


class WrongAnswer(TimestampMixin, Base):
    __tablename__ = "wrong_answers"
    __table_args__ = (
        UniqueConstraint("attempt_id", "answer_id", name="uq_wrong_answers_attempt_answer"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("activity_questions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_attempts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    answer_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_answers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    knowledge_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), default=WrongAnswerStatus.active, nullable=False, index=True
    )
    error_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
