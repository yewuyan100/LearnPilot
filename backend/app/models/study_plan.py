from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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


class StudyPlan(TimestampMixin, Base):
    __tablename__ = "study_plans"
    __table_args__ = (
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("current_version_number >= 1", name="current_version_positive"),
        CheckConstraint(
            "status IN ('draft','validating','ready','infeasible','active','superseded','completed','cancelled')",
            name="status_valid",
        ),
        UniqueConstraint("public_id", name="uq_study_plans_public_id"),
        UniqueConstraint("generation_request_id", name="uq_study_plans_generation_request_id"),
        UniqueConstraint("cancel_request_id", name="uq_study_plans_cancel_request_id"),
        Index("ix_study_plans_goal_course_status", "learning_goal_id", "course_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    learning_goal_id: Mapped[int] = mapped_column(
        ForeignKey("learning_goals.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    active_version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_request_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    generation_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    cancel_request_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StudyPlanVersion(TimestampMixin, Base):
    __tablename__ = "study_plan_versions"
    __table_args__ = (
        CheckConstraint("version_number >= 1", name="version_number_positive"),
        CheckConstraint(
            "status IN ('draft','validating','ready','infeasible','active','superseded','completed','cancelled')",
            name="status_valid",
        ),
        UniqueConstraint("study_plan_id", "version_number", name="uq_study_plan_version_number"),
        UniqueConstraint("generation_request_id", name="uq_study_plan_versions_generation_request_id"),
        UniqueConstraint("replan_request_id", name="uq_study_plan_versions_replan_request_id"),
        UniqueConstraint("publish_request_id", name="uq_study_plan_versions_publish_request_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    study_plan_id: Mapped[int] = mapped_column(
        ForeignKey("study_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    generation_request_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    replan_request_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    publish_request_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False)
    course_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    diagnostic_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("diagnostic_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    required_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    available_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    gap_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conflicts: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    suggestions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    quality_report: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    stale_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    stale_source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    stale_source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class StudyPlanItem(TimestampMixin, Base):
    __tablename__ = "study_plan_items"
    __table_args__ = (
        CheckConstraint("estimated_minutes >= 1", name="estimated_minutes_positive"),
        CheckConstraint("order_index >= 1", name="order_index_positive"),
        UniqueConstraint("study_plan_version_id", "logical_key", name="uq_study_plan_item_logical_key"),
        UniqueConstraint("study_plan_version_id", "order_index", name="uq_study_plan_item_order"),
        Index("ix_study_plan_items_version_date", "study_plan_version_id", "scheduled_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    study_plan_version_id: Mapped[int] = mapped_column(
        ForeignKey("study_plan_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    learning_goal_id: Mapped[int] = mapped_column(
        ForeignKey("learning_goals.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    knowledge_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    lesson_id: Mapped[int | None] = mapped_column(
        ForeignKey("lessons.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    logical_key: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduling_reason: Mapped[str] = mapped_column(Text, nullable=False)
    prerequisite_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_due_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("review_schedules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    diagnostic_result_id: Mapped[int | None] = mapped_column(
        ForeignKey("diagnostic_knowledge_results.id", ondelete="SET NULL"), nullable=True, index=True
    )
    daily_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("daily_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
