from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MasterySnapshot(Base):
    __tablename__ = "mastery_snapshots"
    __table_args__ = (
        CheckConstraint(
            "mastery_score IS NULL OR (mastery_score >= 0 AND mastery_score <= 100)",
            name="mastery_score_range",
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 100",
            name="confidence_score_range",
        ),
        Index("ix_mastery_snapshots_point_calculated", "knowledge_point_id", "calculated_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mastery_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    confidence_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    mastery_level: Mapped[str] = mapped_column(String(24), nullable=False)
    evidence_count: Mapped[int] = mapped_column(nullable=False)
    evidence_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trigger_source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
