"""Add deterministic versioned study plans linked to daily tasks.

Revision ID: 20260805_0014
Revises: 20260805_0013
"""

from alembic import op
import sqlalchemy as sa


revision = "20260805_0014"
down_revision = "20260805_0013"
branch_labels = None
depends_on = None


def timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "study_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("learning_goal_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("current_version_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("active_version_number", sa.Integer(), nullable=True),
        sa.Column("generation_request_id", sa.String(100), nullable=False),
        sa.Column("generation_config_hash", sa.String(64), nullable=False),
        sa.Column("cancel_request_id", sa.String(100), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint("version >= 1", name=op.f("ck_study_plans_version_positive")),
        sa.CheckConstraint("current_version_number >= 1", name=op.f("ck_study_plans_current_version_positive")),
        sa.CheckConstraint(
            "status IN ('draft','validating','ready','infeasible','active','superseded','completed','cancelled')",
            name=op.f("ck_study_plans_status_valid"),
        ),
        sa.ForeignKeyConstraint(["learning_goal_id"], ["learning_goals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("public_id", name="uq_study_plans_public_id"),
        sa.UniqueConstraint("generation_request_id", name="uq_study_plans_generation_request_id"),
        sa.UniqueConstraint("cancel_request_id", name="uq_study_plans_cancel_request_id"),
    )
    for column in ("public_id", "learning_goal_id", "course_id", "status", "generation_request_id", "cancel_request_id"):
        op.create_index(op.f(f"ix_study_plans_{column}"), "study_plans", [column])
    op.create_index("ix_study_plans_goal_course_status", "study_plans", ["learning_goal_id", "course_id", "status"])

    op.create_table(
        "study_plan_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("study_plan_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("generation_request_id", sa.String(100), nullable=True),
        sa.Column("replan_request_id", sa.String(100), nullable=True),
        sa.Column("publish_request_id", sa.String(100), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("course_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("diagnostic_session_id", sa.Integer(), nullable=True),
        sa.Column("required_minutes", sa.Integer(), nullable=False),
        sa.Column("available_minutes", sa.Integer(), nullable=False),
        sa.Column("gap_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("conflicts", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("suggestions", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("quality_report", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint("version_number >= 1", name=op.f("ck_study_plan_versions_version_number_positive")),
        sa.CheckConstraint(
            "status IN ('draft','validating','ready','infeasible','active','superseded','completed','cancelled')",
            name=op.f("ck_study_plan_versions_status_valid"),
        ),
        sa.ForeignKeyConstraint(["study_plan_id"], ["study_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["diagnostic_session_id"], ["diagnostic_sessions.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("study_plan_id", "version_number", name="uq_study_plan_version_number"),
        sa.UniqueConstraint("generation_request_id", name="uq_study_plan_versions_generation_request_id"),
        sa.UniqueConstraint("replan_request_id", name="uq_study_plan_versions_replan_request_id"),
        sa.UniqueConstraint("publish_request_id", name="uq_study_plan_versions_publish_request_id"),
    )
    for column in ("study_plan_id", "status", "generation_request_id", "replan_request_id", "publish_request_id", "diagnostic_session_id"):
        op.create_index(op.f(f"ix_study_plan_versions_{column}"), "study_plan_versions", [column])

    op.create_table(
        "study_plan_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("study_plan_version_id", sa.Integer(), nullable=False),
        sa.Column("learning_goal_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=True),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("logical_key", sa.String(160), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("activity_type", sa.String(32), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("scheduling_reason", sa.Text(), nullable=False),
        sa.Column("prerequisite_ids", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("is_due_review", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("review_schedule_id", sa.Integer(), nullable=True),
        sa.Column("diagnostic_result_id", sa.Integer(), nullable=True),
        sa.Column("daily_task_id", sa.Integer(), nullable=True),
        *timestamps(),
        sa.CheckConstraint("estimated_minutes >= 1", name=op.f("ck_study_plan_items_estimated_minutes_positive")),
        sa.CheckConstraint("order_index >= 1", name=op.f("ck_study_plan_items_order_index_positive")),
        sa.ForeignKeyConstraint(["study_plan_version_id"], ["study_plan_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["learning_goal_id"], ["learning_goals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["review_schedule_id"], ["review_schedules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["diagnostic_result_id"], ["diagnostic_knowledge_results.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["daily_task_id"], ["daily_tasks.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("study_plan_version_id", "logical_key", name="uq_study_plan_item_logical_key"),
        sa.UniqueConstraint("study_plan_version_id", "order_index", name="uq_study_plan_item_order"),
    )
    for column in ("study_plan_version_id", "learning_goal_id", "course_id", "knowledge_point_id", "scheduled_date", "review_schedule_id", "diagnostic_result_id", "daily_task_id"):
        op.create_index(op.f(f"ix_study_plan_items_{column}"), "study_plan_items", [column])
    op.create_index("ix_study_plan_items_version_date", "study_plan_items", ["study_plan_version_id", "scheduled_date"])


def downgrade() -> None:
    op.drop_table("study_plan_items")
    op.drop_table("study_plan_versions")
    op.drop_table("study_plans")
