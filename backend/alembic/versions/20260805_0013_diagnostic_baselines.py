"""Add course diagnostics and traceable capability baselines.

Revision ID: 20260805_0013
Revises: 20260804_0012
"""

from alembic import op
import sqlalchemy as sa


revision = "20260805_0013"
down_revision = "20260804_0012"
branch_labels = None
depends_on = None


def timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "diagnostic_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), server_default="generating", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("generation_request_id", sa.String(100), nullable=False),
        sa.Column("generation_config_hash", sa.String(64), nullable=False),
        sa.Column("submit_request_id", sa.String(100), nullable=True),
        sa.Column("submission_hash", sa.String(64), nullable=True),
        sa.Column("activity_id", sa.Integer(), nullable=True),
        sa.Column("attempt_id", sa.Integer(), nullable=True),
        sa.Column("supersedes_session_id", sa.Integer(), nullable=True),
        sa.Column("course_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=True),
        sa.Column("coverage_report", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("generation_metrics", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint("version >= 1", name=op.f("ck_diagnostic_sessions_version_positive")),
        sa.CheckConstraint(
            "status IN ('generating','pending','submitted','evidence_insufficient','generation_failed','review_required','cancelled')",
            name=op.f("ck_diagnostic_sessions_status_valid"),
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["activity_id"], ["learning_activities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["attempt_id"], ["quiz_attempts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["supersedes_session_id"], ["diagnostic_sessions.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("public_id", name="uq_diagnostic_sessions_public_id"),
        sa.UniqueConstraint("generation_request_id", name="uq_diagnostic_sessions_generation_request_id"),
        sa.UniqueConstraint("submit_request_id", name="uq_diagnostic_sessions_submit_request_id"),
        sa.UniqueConstraint("activity_id", name="uq_diagnostic_sessions_activity_id"),
        sa.UniqueConstraint("attempt_id", name="uq_diagnostic_sessions_attempt_id"),
    )
    for column in ("public_id", "course_id", "status", "generation_request_id", "submit_request_id", "activity_id", "attempt_id", "supersedes_session_id"):
        op.create_index(op.f(f"ix_diagnostic_sessions_{column}"), "diagnostic_sessions", [column])
    op.create_index("ix_diagnostic_sessions_course_status", "diagnostic_sessions", ["course_id", "status"])

    op.create_table(
        "diagnostic_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("diagnostic_session_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("material_chunk_id", sa.Integer(), nullable=False),
        sa.Column("question_type", sa.String(32), nullable=False),
        sa.Column("difficulty", sa.String(16), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=True),
        sa.Column("generation_request_id", sa.String(100), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["diagnostic_session_id"], ["diagnostic_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["activity_questions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["material_chunk_id"], ["material_chunks.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("diagnostic_session_id", "question_id", name="uq_diagnostic_item_question"),
    )
    for column in ("diagnostic_session_id", "question_id", "knowledge_point_id", "material_id", "material_chunk_id"):
        op.create_index(op.f(f"ix_diagnostic_items_{column}"), "diagnostic_items", [column])
    op.create_index("ix_diagnostic_items_session_point", "diagnostic_items", ["diagnostic_session_id", "knowledge_point_id"])

    op.create_table(
        "diagnostic_answer_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("diagnostic_item_id", sa.Integer(), nullable=False),
        sa.Column("quiz_answer_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("candidate_score", sa.Float(), nullable=True),
        sa.Column("dimensions", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("rationale", sa.Text(), server_default="", nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("recommend_manual_review", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("rubric_version", sa.String(100), nullable=True),
        sa.Column("model_name", sa.String(200), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["diagnostic_item_id"], ["diagnostic_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quiz_answer_id"], ["quiz_answers.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("diagnostic_item_id", "quiz_answer_id", name="uq_diagnostic_answer_assessment"),
    )
    for column in ("diagnostic_item_id", "quiz_answer_id", "status"):
        op.create_index(op.f(f"ix_diagnostic_answer_assessments_{column}"), "diagnostic_answer_assessments", [column])

    op.create_table(
        "diagnostic_knowledge_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("diagnostic_session_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=False),
        sa.Column("answered_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("graded_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("earned_points", sa.Float(), nullable=True),
        sa.Column("possible_points", sa.Float(), nullable=True),
        sa.Column("score_percentage", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("ability_level", sa.String(32), nullable=False),
        sa.Column("is_skill_gap", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("evidence_insufficient", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_answer_ids", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("evidence_source_ids", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("mastery_evidence_id", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        *timestamps(),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name=op.f("ck_diagnostic_knowledge_results_confidence_range")),
        sa.CheckConstraint("priority >= 0 AND priority <= 100", name=op.f("ck_diagnostic_knowledge_results_priority_range")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_diagnostic_knowledge_results_version_positive")),
        sa.ForeignKeyConstraint(["diagnostic_session_id"], ["diagnostic_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["mastery_evidence_id"], ["mastery_evidence.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("diagnostic_session_id", "knowledge_point_id", name="uq_diagnostic_session_point_result"),
    )
    for column in ("diagnostic_session_id", "knowledge_point_id", "ability_level", "is_skill_gap", "mastery_evidence_id"):
        op.create_index(op.f(f"ix_diagnostic_knowledge_results_{column}"), "diagnostic_knowledge_results", [column])

    op.create_table(
        "diagnostic_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("diagnostic_knowledge_result_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("before_value", sa.JSON(), nullable=False),
        sa.Column("after_value", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["diagnostic_knowledge_result_id"], ["diagnostic_knowledge_results.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("request_id", name="uq_diagnostic_adjustments_request_id"),
    )
    op.create_index(op.f("ix_diagnostic_adjustments_diagnostic_knowledge_result_id"), "diagnostic_adjustments", ["diagnostic_knowledge_result_id"])
    op.create_index(op.f("ix_diagnostic_adjustments_request_id"), "diagnostic_adjustments", ["request_id"])


def downgrade() -> None:
    for table in (
        "diagnostic_adjustments",
        "diagnostic_knowledge_results",
        "diagnostic_answer_assessments",
        "diagnostic_items",
        "diagnostic_sessions",
    ):
        op.drop_table(table)
