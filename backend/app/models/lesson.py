from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
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


LESSON_STATUSES = (
    "draft",
    "generating",
    "review_required",
    "ready",
    "published",
    "superseded",
    "archived",
)


class Lesson(TimestampMixin, Base):
    __tablename__ = "lessons"
    __table_args__ = (
        CheckConstraint("order_index >= 1", name="order_index_positive"),
        CheckConstraint("current_version_number >= 0", name="current_version_non_negative"),
        CheckConstraint(
            "status IN ('draft','generating','review_required','ready','published','superseded','archived')",
            name="status_valid",
        ),
        UniqueConstraint("public_id", name="uq_lessons_public_id"),
        UniqueConstraint("course_id", "order_index", name="uq_lessons_course_order"),
        Index("ix_lessons_course_status", "course_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    current_version_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)


class LessonVersion(TimestampMixin, Base):
    __tablename__ = "lesson_versions"
    __table_args__ = (
        CheckConstraint("version_number >= 1", name="version_number_positive"),
        CheckConstraint("estimated_minutes >= 1", name="estimated_minutes_positive"),
        CheckConstraint(
            "status IN ('draft','generating','review_required','ready','published','superseded','archived')",
            name="status_valid",
        ),
        UniqueConstraint("lesson_id", "version_number", name="uq_lesson_version_number"),
        UniqueConstraint("generation_request_id", name="uq_lesson_versions_generation_request_id"),
        Index("ix_lesson_versions_lesson_status", "lesson_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    objectives: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    examples: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    guided_practice: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    checks: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    source_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generation_request_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    quality_report: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LessonVersionKnowledgePoint(Base):
    __tablename__ = "lesson_version_knowledge_points"
    __table_args__ = (
        CheckConstraint("order_index >= 1", name="order_index_positive"),
        CheckConstraint(
            "role IN ('primary','supporting','prerequisite_context')",
            name="role_valid",
        ),
        UniqueConstraint(
            "lesson_version_id", "order_index", name="uq_lesson_version_point_order"
        ),
    )

    lesson_version_id: Mapped[int] = mapped_column(
        ForeignKey("lesson_versions.id", ondelete="CASCADE"), primary_key=True
    )
    knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)


class LessonSource(Base):
    __tablename__ = "lesson_sources"
    __table_args__ = (
        CheckConstraint(
            "source_role IN ('primary','supporting','example','prerequisite_context')",
            name="source_role_valid",
        ),
    )

    lesson_version_id: Mapped[int] = mapped_column(
        ForeignKey("lesson_versions.id", ondelete="CASCADE"), primary_key=True
    )
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    material_chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_chunks.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source_role: Mapped[str] = mapped_column(String(32), nullable=False)
    source_locator: Mapped[str] = mapped_column(String(500), primary_key=True)
    quoted_text: Mapped[str] = mapped_column(Text, nullable=False)
