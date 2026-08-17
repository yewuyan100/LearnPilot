from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DiagnosticSession(TimestampMixin, Base):
    __tablename__ = "diagnostic_sessions"
    __table_args__ = (
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "status IN ('generating','pending','submitted','evidence_insufficient',"
            "'generation_failed','review_required','cancelled')",
            name="status_valid",
        ),
        UniqueConstraint("public_id", name="uq_diagnostic_sessions_public_id"),
        UniqueConstraint(
            "generation_request_id", name="uq_diagnostic_sessions_generation_request_id"
        ),
        UniqueConstraint("submit_request_id", name="uq_diagnostic_sessions_submit_request_id"),
        UniqueConstraint("activity_id", name="uq_diagnostic_sessions_activity_id"),
        UniqueConstraint("attempt_id", name="uq_diagnostic_sessions_attempt_id"),
        Index("ix_diagnostic_sessions_course_status", "course_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="generating", nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    generation_request_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    generation_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    submit_request_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    submission_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_activities.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("quiz_attempts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    supersedes_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("diagnostic_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    course_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    coverage_report: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    generation_metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DiagnosticItem(TimestampMixin, Base):
    __tablename__ = "diagnostic_items"
    __table_args__ = (
        UniqueConstraint("diagnostic_session_id", "question_id", name="uq_diagnostic_item_question"),
        Index("ix_diagnostic_items_session_point", "diagnostic_session_id", "knowledge_point_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    diagnostic_session_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("activity_questions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    material_chunk_id: Mapped[int] = mapped_column(
        ForeignKey("material_chunks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    question_type: Mapped[str] = mapped_column(String(32), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    generation_request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)


class DiagnosticAnswerAssessment(TimestampMixin, Base):
    __tablename__ = "diagnostic_answer_assessments"
    __table_args__ = (
        UniqueConstraint("diagnostic_item_id", "quiz_answer_id", name="uq_diagnostic_answer_assessment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    diagnostic_item_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quiz_answer_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_answers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    candidate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    dimensions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, default="", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommend_manual_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rubric_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)


class DiagnosticKnowledgeResult(TimestampMixin, Base):
    __tablename__ = "diagnostic_knowledge_results"
    __table_args__ = (
        UniqueConstraint(
            "diagnostic_session_id", "knowledge_point_id", name="uq_diagnostic_session_point_result"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint("priority >= 0 AND priority <= 100", name="priority_range"),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    diagnostic_session_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    answered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    graded_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    earned_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    possible_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    ability_level: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    is_skill_gap: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    evidence_insufficient: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_answer_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    evidence_source_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    mastery_evidence_id: Mapped[int | None] = mapped_column(
        ForeignKey("mastery_evidence.id", ondelete="SET NULL"), nullable=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class DiagnosticAdjustment(TimestampMixin, Base):
    __tablename__ = "diagnostic_adjustments"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_diagnostic_adjustments_request_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    diagnostic_knowledge_result_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_knowledge_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    request_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    before_value: Mapped[dict] = mapped_column(JSON, nullable=False)
    after_value: Mapped[dict] = mapped_column(JSON, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
