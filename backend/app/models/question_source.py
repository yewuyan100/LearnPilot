from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class QuestionSource(TimestampMixin, Base):
    __tablename__ = "question_sources"
    __table_args__ = (
        UniqueConstraint("question_id", "source_label", name="uq_question_sources_question_label"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("activity_questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_label: Mapped[str] = mapped_column(String(16), nullable=False)
    material_id: Mapped[int | None] = mapped_column(
        ForeignKey("materials.id", ondelete="SET NULL"), nullable=True
    )
    chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_chunks.id", ondelete="SET NULL"), nullable=True
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
