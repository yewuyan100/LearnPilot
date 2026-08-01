from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MasteryEvidence(Base):
    __tablename__ = "mastery_evidence"
    __table_args__ = (
        UniqueConstraint(
            "source_type", "source_id", "evidence_type",
            name="uq_mastery_evidence_source_type_id_kind",
        ),
        CheckConstraint(
            "normalized_score >= 0 AND normalized_score <= 100",
            name="normalized_score_range",
        ),
        CheckConstraint("weight > 0 AND weight <= 1", name="weight_range"),
        Index("ix_mastery_evidence_point_occurred", "knowledge_point_id", "occurred_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    raw_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
