from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class KnowledgeMastery(TimestampMixin, Base):
    __tablename__ = "knowledge_masteries"
    __table_args__ = (
        UniqueConstraint("knowledge_point_id", name="uq_knowledge_masteries_knowledge_point"),
        CheckConstraint(
            "mastery_score IS NULL OR (mastery_score >= 0 AND mastery_score <= 100)",
            name="mastery_score_range",
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 100",
            name="confidence_score_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mastery_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    confidence_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    mastery_level: Mapped[str] = mapped_column(String(24), default="unassessed", nullable=False, index=True)
    evidence_count: Mapped[int] = mapped_column(default=0, nullable=False)
    last_evidence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_practiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
