from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ActivityQuestion(TimestampMixin, Base):
    __tablename__ = "activity_questions"
    __table_args__ = (
        UniqueConstraint("activity_id", "question_index", name="uq_activity_questions_activity_index"),
        CheckConstraint("points > 0", name="points_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("learning_activities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    correct_answer_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    grading_rubric_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    points: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
