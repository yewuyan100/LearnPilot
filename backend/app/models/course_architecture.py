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


class CourseArchitectureDraft(TimestampMixin, Base):
    __tablename__ = "course_architecture_drafts"
    __table_args__ = (
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "status IN ('draft','generating','review_required','ready','publishing',"
            "'published','failed','archived')",
            name="status_valid",
        ),
        UniqueConstraint("public_id", name="uq_course_architecture_drafts_public_id"),
        UniqueConstraint(
            "generation_request_id",
            name="uq_course_architecture_drafts_generation_request_id",
        ),
        UniqueConstraint(
            "publish_request_id",
            name="uq_course_architecture_drafts_publish_request_id",
        ),
        Index("ix_course_architecture_drafts_goal_status", "learning_goal_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    learning_goal_id: Mapped[int] = mapped_column(
        ForeignKey("learning_goals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    generation_status: Mapped[str] = mapped_column(
        String(32), default="not_started", nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    source_snapshot_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    generation_mode: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    generation_request_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    generation_progress: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_status: Mapped[str] = mapped_column(
        String(32), default="not_checked", nullable=False, index=True
    )
    quality_report: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    publish_request_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CourseArchitectureDraftMaterial(TimestampMixin, Base):
    __tablename__ = "course_architecture_draft_materials"
    __table_args__ = (
        UniqueConstraint("draft_id", "material_id", name="uq_draft_material"),
        UniqueConstraint("draft_id", "order_index", name="uq_draft_material_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[int] = mapped_column(
        ForeignKey("course_architecture_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    material_updated_at_snapshot: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    chunk_count_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    index_state_snapshot: Mapped[str] = mapped_column(String(32), nullable=False)


class CourseArchitectureDraftCourse(TimestampMixin, Base):
    __tablename__ = "course_architecture_draft_courses"
    __table_args__ = (
        Index("ix_draft_courses_draft_order", "draft_id", "order_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[int] = mapped_column(
        ForeignKey("course_architecture_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    learning_outcomes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    origin: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_modified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), unique=True, nullable=True
    )


class CourseArchitectureDraftKnowledgePoint(TimestampMixin, Base):
    __tablename__ = "course_architecture_draft_knowledge_points"
    __table_args__ = (
        Index("ix_draft_points_course_order", "draft_course_id", "order_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_course_id: Mapped[int] = mapped_column(
        ForeignKey("course_architecture_draft_courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    learning_objectives: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    key_terms: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    granularity_label: Mapped[str | None] = mapped_column(String(40), nullable=True)
    difficulty_label: Mapped[str | None] = mapped_column(String(40), nullable=True)
    origin: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_modified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_status: Mapped[str] = mapped_column(String(32), default="missing", nullable=False)
    validation_status: Mapped[str] = mapped_column(String(32), default="unchecked", nullable=False)
    published_knowledge_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="SET NULL"), unique=True, nullable=True
    )


class CourseArchitectureDraftSource(TimestampMixin, Base):
    __tablename__ = "course_architecture_draft_sources"
    __table_args__ = (
        CheckConstraint(
            "source_role IN ('primary','supporting','example','prerequisite_context')",
            name="source_role_valid",
        ),
        CheckConstraint(
            "quoted_text IS NULL OR length(quoted_text) <= 2000",
            name="quoted_text_length",
        ),
        UniqueConstraint(
            "draft_knowledge_point_id",
            "material_chunk_id",
            "source_role",
            name="uq_draft_source_point_chunk_role",
        ),
        Index("ix_draft_sources_material_chunk", "material_id", "material_chunk_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("course_architecture_draft_knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material_chunk_id: Mapped[int] = mapped_column(
        ForeignKey("material_chunks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_locator: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quoted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_role: Mapped[str] = mapped_column(String(32), default="primary", nullable=False)
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    origin: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)


class CourseArchitectureDraftPrerequisite(TimestampMixin, Base):
    __tablename__ = "course_architecture_draft_prerequisites"
    __table_args__ = (
        CheckConstraint(
            "prerequisite_knowledge_point_id != dependent_knowledge_point_id",
            name="not_self",
        ),
        UniqueConstraint(
            "draft_id",
            "prerequisite_knowledge_point_id",
            "dependent_knowledge_point_id",
            name="uq_draft_prerequisite_edge",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[int] = mapped_column(
        ForeignKey("course_architecture_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    prerequisite_knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("course_architecture_draft_knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dependent_knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("course_architecture_draft_knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    origin: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    validation_status: Mapped[str] = mapped_column(String(32), default="valid", nullable=False)


class CourseArchitectureDraftVersion(TimestampMixin, Base):
    __tablename__ = "course_architecture_draft_versions"
    __table_args__ = (
        UniqueConstraint("draft_id", "version", name="uq_draft_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[int] = mapped_column(
        ForeignKey("course_architecture_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)


class KnowledgePointPrerequisite(TimestampMixin, Base):
    __tablename__ = "knowledge_point_prerequisites"
    __table_args__ = (
        CheckConstraint(
            "prerequisite_knowledge_point_id != dependent_knowledge_point_id",
            name="not_self",
        ),
        UniqueConstraint(
            "prerequisite_knowledge_point_id",
            "dependent_knowledge_point_id",
            name="uq_knowledge_point_prerequisite_edge",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    prerequisite_knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dependent_knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(
        String(32), default="prerequisite", nullable=False
    )
    source: Mapped[str] = mapped_column(String(32), default="course_architecture", nullable=False)
