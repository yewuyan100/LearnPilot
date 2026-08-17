from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class LearningProposal(TimestampMixin, Base):
    """A pending-decision envelope; domain drafts remain owned by domain modules."""

    __tablename__ = "learning_proposals"
    __table_args__ = (
        UniqueConstraint("public_id", name="uq_learning_proposals_public_id"),
        UniqueConstraint(
            "generation_request_id",
            name="uq_learning_proposals_generation_request_id",
        ),
        UniqueConstraint("decision_request_id", name="uq_learning_proposals_decision_request_id"),
        CheckConstraint(
            "status IN ('pending','review_required','accepted','rejected','expired')",
            name="status_valid",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    proposal_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    generation_request_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    source_harness_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("harness_runs.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("learning_events.event_id", ondelete="RESTRICT"), nullable=True, index=True
    )
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    context_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    domain_draft_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    domain_draft_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, default="", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
