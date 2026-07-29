from sqlalchemy import Float, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import GradingStatus


class QuizAnswer(TimestampMixin, Base):
    __tablename__ = "quiz_answers"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_quiz_answers_attempt_question"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("activity_questions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    answer_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(nullable=True)
    grading_status: Mapped[str] = mapped_column(
        String(16), default=GradingStatus.pending, nullable=False, index=True
    )
    earned_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_points: Mapped[float] = mapped_column(Float, nullable=False)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_rubric_items_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    missing_rubric_items_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    grader_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
