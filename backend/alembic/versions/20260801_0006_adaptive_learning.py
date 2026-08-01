"""Add deterministic mastery, review scheduling and adaptive recommendations."""

from alembic import op
import sqlalchemy as sa


revision = "20260801_0006"
down_revision = "20260801_0005"
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "knowledge_masteries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("knowledge_point_id", sa.Integer(), sa.ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mastery_score", sa.Numeric(5, 2)),
        sa.Column("confidence_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("mastery_level", sa.String(24), nullable=False, server_default="unassessed"),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_evidence_at", sa.DateTime(timezone=True)),
        sa.Column("last_practiced_at", sa.DateTime(timezone=True)),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("next_review_at", sa.DateTime(timezone=True)),
        sa.Column("algorithm_version", sa.String(32), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        *timestamps(),
        sa.CheckConstraint("mastery_score IS NULL OR (mastery_score >= 0 AND mastery_score <= 100)", name="ck_knowledge_masteries_mastery_score_range"),
        sa.CheckConstraint("confidence_score >= 0 AND confidence_score <= 100", name="ck_knowledge_masteries_confidence_score_range"),
        sa.UniqueConstraint("knowledge_point_id", name="uq_knowledge_masteries_knowledge_point"),
    )
    op.create_index("ix_knowledge_masteries_knowledge_point_id", "knowledge_masteries", ["knowledge_point_id"])
    op.create_index("ix_knowledge_masteries_mastery_level", "knowledge_masteries", ["mastery_level"])
    op.create_index("ix_knowledge_masteries_next_review_at", "knowledge_masteries", ["next_review_at"])
    op.create_index("ix_knowledge_masteries_calculated_at", "knowledge_masteries", ["calculated_at"])

    op.create_table(
        "mastery_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("knowledge_point_id", sa.Integer(), sa.ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_type", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_value", sa.Float()),
        sa.Column("normalized_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("weight", sa.Numeric(5, 4), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("normalized_score >= 0 AND normalized_score <= 100", name="ck_mastery_evidence_normalized_score_range"),
        sa.CheckConstraint("weight > 0 AND weight <= 1", name="ck_mastery_evidence_weight_range"),
        sa.UniqueConstraint("source_type", "source_id", "evidence_type", name="uq_mastery_evidence_source_type_id_kind"),
        sa.UniqueConstraint("content_hash", name="uq_mastery_evidence_content_hash"),
    )
    op.create_index("ix_mastery_evidence_knowledge_point_id", "mastery_evidence", ["knowledge_point_id"])
    op.create_index("ix_mastery_evidence_evidence_type", "mastery_evidence", ["evidence_type"])
    op.create_index("ix_mastery_evidence_occurred_at", "mastery_evidence", ["occurred_at"])
    op.create_index("ix_mastery_evidence_point_occurred", "mastery_evidence", ["knowledge_point_id", "occurred_at", "id"])

    op.create_table(
        "mastery_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("knowledge_point_id", sa.Integer(), sa.ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mastery_score", sa.Numeric(5, 2)),
        sa.Column("confidence_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("mastery_level", sa.String(24), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("evidence_summary_json", sa.JSON(), nullable=False),
        sa.Column("algorithm_version", sa.String(32), nullable=False),
        sa.Column("trigger_type", sa.String(32), nullable=False),
        sa.Column("trigger_source_id", sa.String(64)),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("mastery_score IS NULL OR (mastery_score >= 0 AND mastery_score <= 100)", name="ck_mastery_snapshots_mastery_score_range"),
        sa.CheckConstraint("confidence_score >= 0 AND confidence_score <= 100", name="ck_mastery_snapshots_confidence_score_range"),
    )
    op.create_index("ix_mastery_snapshots_knowledge_point_id", "mastery_snapshots", ["knowledge_point_id"])
    op.create_index("ix_mastery_snapshots_trigger_type", "mastery_snapshots", ["trigger_type"])
    op.create_index("ix_mastery_snapshots_point_calculated", "mastery_snapshots", ["knowledge_point_id", "calculated_at", "id"])

    op.create_table(
        "review_schedules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("knowledge_point_id", sa.Integer(), sa.ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("priority_score", sa.Float(), nullable=False),
        sa.Column("recommended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("reason_summary", sa.Text(), nullable=False),
        sa.Column("source_snapshot_id", sa.Integer(), sa.ForeignKey("mastery_snapshots.id", ondelete="SET NULL")),
        sa.Column("completed_task_id", sa.Integer(), sa.ForeignKey("daily_tasks.id", ondelete="SET NULL")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *timestamps(),
    )
    op.create_index("ix_review_schedules_knowledge_point_id", "review_schedules", ["knowledge_point_id"])
    op.create_index("ix_review_schedules_status", "review_schedules", ["status"])
    op.create_index("ix_review_schedules_due_at", "review_schedules", ["due_at"])
    op.create_index("ix_review_schedules_reason_code", "review_schedules", ["reason_code"])
    op.create_index("ix_review_schedules_completed_task_id", "review_schedules", ["completed_task_id"])
    op.create_index("ix_review_schedules_point_status", "review_schedules", ["knowledge_point_id", "status"])
    op.create_index("ix_review_schedules_status_due", "review_schedules", ["status", "due_at", "id"])
    op.create_index("uq_review_schedules_active_point", "review_schedules", ["knowledge_point_id"], unique=True, sqlite_where=sa.text("status IN ('pending','scheduled')"))

    op.create_table(
        "adaptive_recommendations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recommendation_type", sa.String(32), nullable=False, server_default="review_task"),
        sa.Column("knowledge_point_id", sa.Integer(), sa.ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("reason_details_json", sa.JSON(), nullable=False),
        sa.Column("suggested_date", sa.Date(), nullable=False),
        sa.Column("suggested_minutes", sa.Integer(), nullable=False),
        sa.Column("source_snapshot_id", sa.Integer(), sa.ForeignKey("mastery_snapshots.id", ondelete="SET NULL")),
        sa.Column("created_task_id", sa.Integer(), sa.ForeignKey("daily_tasks.id", ondelete="SET NULL")),
        *timestamps(),
    )
    op.create_index("ix_adaptive_recommendations_knowledge_point_id", "adaptive_recommendations", ["knowledge_point_id"])
    op.create_index("ix_adaptive_recommendations_status", "adaptive_recommendations", ["status"])
    op.create_index("ix_adaptive_recommendations_priority", "adaptive_recommendations", ["priority"])
    op.create_index("ix_adaptive_recommendations_suggested_date", "adaptive_recommendations", ["suggested_date"])
    op.create_index("ix_adaptive_recommendations_created_task_id", "adaptive_recommendations", ["created_task_id"])
    op.create_index("ix_adaptive_recommendations_status_date", "adaptive_recommendations", ["status", "suggested_date", "id"])
    op.create_index("ix_adaptive_recommendations_point_status", "adaptive_recommendations", ["knowledge_point_id", "status"])


def downgrade() -> None:
    op.drop_table("adaptive_recommendations")
    op.drop_table("review_schedules")
    op.drop_table("mastery_snapshots")
    op.drop_table("mastery_evidence")
    op.drop_table("knowledge_masteries")
