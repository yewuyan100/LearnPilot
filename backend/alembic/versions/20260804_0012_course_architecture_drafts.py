"""Add course architecture drafts and formal knowledge point prerequisites.

Revision ID: 20260804_0012
Revises: 20260804_0011
"""

from alembic import op
import sqlalchemy as sa


revision = "20260804_0012"
down_revision = "20260804_0011"
branch_labels = None
depends_on = None


def timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "course_architecture_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("learning_goal_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("generation_status", sa.String(32), server_default="not_started", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("source_snapshot_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("generation_mode", sa.String(32), server_default="manual", nullable=False),
        sa.Column("model_name", sa.String(200), nullable=True),
        sa.Column("prompt_version", sa.String(100), nullable=True),
        sa.Column("generation_request_id", sa.String(100), nullable=True),
        sa.Column("generation_progress", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("quality_status", sa.String(32), server_default="not_checked", nullable=False),
        sa.Column("quality_report", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("publish_request_id", sa.String(100), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint("version >= 1", name=op.f("ck_course_architecture_drafts_version_positive")),
        sa.CheckConstraint(
            "status IN ('draft','generating','review_required','ready','publishing','published','failed','archived')",
            name=op.f("ck_course_architecture_drafts_status_valid"),
        ),
        sa.ForeignKeyConstraint(["learning_goal_id"], ["learning_goals.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("public_id", name=op.f("uq_course_architecture_drafts_public_id")),
        sa.UniqueConstraint("generation_request_id", name=op.f("uq_course_architecture_drafts_generation_request_id")),
        sa.UniqueConstraint("publish_request_id", name=op.f("uq_course_architecture_drafts_publish_request_id")),
    )
    for column in ("public_id", "learning_goal_id", "status", "generation_status", "generation_request_id", "quality_status", "publish_request_id"):
        op.create_index(op.f(f"ix_course_architecture_drafts_{column}"), "course_architecture_drafts", [column])
    op.create_index("ix_course_architecture_drafts_goal_status", "course_architecture_drafts", ["learning_goal_id", "status"])

    op.create_table(
        "course_architecture_draft_materials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("draft_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("material_updated_at_snapshot", sa.DateTime(timezone=True), nullable=False),
        sa.Column("chunk_count_snapshot", sa.Integer(), nullable=False),
        sa.Column("index_state_snapshot", sa.String(32), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["draft_id"], ["course_architecture_drafts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("draft_id", "material_id", name="uq_draft_material"),
        sa.UniqueConstraint("draft_id", "order_index", name="uq_draft_material_order"),
    )
    for column in ("draft_id", "material_id", "order_index"):
        op.create_index(op.f(f"ix_course_architecture_draft_materials_{column}"), "course_architecture_draft_materials", [column])

    op.create_table(
        "course_architecture_draft_courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("draft_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("learning_outcomes", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("origin", sa.String(20), server_default="manual", nullable=False),
        sa.Column("is_locked", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("user_modified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("published_course_id", sa.Integer(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["draft_id"], ["course_architecture_drafts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_course_id"], ["courses.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("published_course_id", name=op.f("uq_course_architecture_draft_courses_published_course_id")),
    )
    op.create_index(op.f("ix_course_architecture_draft_courses_draft_id"), "course_architecture_draft_courses", ["draft_id"])
    op.create_index(op.f("ix_course_architecture_draft_courses_order_index"), "course_architecture_draft_courses", ["order_index"])
    op.create_index("ix_draft_courses_draft_order", "course_architecture_draft_courses", ["draft_id", "order_index"])

    op.create_table(
        "course_architecture_draft_knowledge_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("draft_course_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("learning_objectives", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("key_terms", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("granularity_label", sa.String(40), nullable=True),
        sa.Column("difficulty_label", sa.String(40), nullable=True),
        sa.Column("origin", sa.String(20), server_default="manual", nullable=False),
        sa.Column("is_locked", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("user_modified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("source_status", sa.String(32), server_default="missing", nullable=False),
        sa.Column("validation_status", sa.String(32), server_default="unchecked", nullable=False),
        sa.Column("published_knowledge_point_id", sa.Integer(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["draft_course_id"], ["course_architecture_draft_courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_knowledge_point_id"], ["knowledge_points.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("published_knowledge_point_id", name=op.f("uq_course_architecture_draft_knowledge_points_published_knowledge_point_id")),
    )
    op.create_index(op.f("ix_course_architecture_draft_knowledge_points_draft_course_id"), "course_architecture_draft_knowledge_points", ["draft_course_id"])
    op.create_index(op.f("ix_course_architecture_draft_knowledge_points_order_index"), "course_architecture_draft_knowledge_points", ["order_index"])
    op.create_index("ix_draft_points_course_order", "course_architecture_draft_knowledge_points", ["draft_course_id", "order_index"])

    op.create_table(
        "course_architecture_draft_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("draft_knowledge_point_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("material_chunk_id", sa.Integer(), nullable=False),
        sa.Column("source_locator", sa.String(500), nullable=True),
        sa.Column("quoted_text", sa.Text(), nullable=True),
        sa.Column("source_role", sa.String(32), server_default="primary", nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("origin", sa.String(20), server_default="manual", nullable=False),
        *timestamps(),
        sa.CheckConstraint("source_role IN ('primary','supporting','example','prerequisite_context')", name=op.f("ck_course_architecture_draft_sources_source_role_valid")),
        sa.CheckConstraint("quoted_text IS NULL OR length(quoted_text) <= 2000", name=op.f("ck_course_architecture_draft_sources_quoted_text_length")),
        sa.ForeignKeyConstraint(["draft_knowledge_point_id"], ["course_architecture_draft_knowledge_points.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_chunk_id"], ["material_chunks.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("draft_knowledge_point_id", "material_chunk_id", "source_role", name="uq_draft_source_point_chunk_role"),
    )
    for column in ("draft_knowledge_point_id", "material_id", "material_chunk_id"):
        op.create_index(op.f(f"ix_course_architecture_draft_sources_{column}"), "course_architecture_draft_sources", [column])
    op.create_index("ix_draft_sources_material_chunk", "course_architecture_draft_sources", ["material_id", "material_chunk_id"])

    op.create_table(
        "course_architecture_draft_prerequisites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("draft_id", sa.Integer(), nullable=False),
        sa.Column("prerequisite_knowledge_point_id", sa.Integer(), nullable=False),
        sa.Column("dependent_knowledge_point_id", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("origin", sa.String(20), server_default="manual", nullable=False),
        sa.Column("validation_status", sa.String(32), server_default="valid", nullable=False),
        *timestamps(),
        sa.CheckConstraint("prerequisite_knowledge_point_id != dependent_knowledge_point_id", name=op.f("ck_course_architecture_draft_prerequisites_not_self")),
        sa.ForeignKeyConstraint(["draft_id"], ["course_architecture_drafts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prerequisite_knowledge_point_id"], ["course_architecture_draft_knowledge_points.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dependent_knowledge_point_id"], ["course_architecture_draft_knowledge_points.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("draft_id", "prerequisite_knowledge_point_id", "dependent_knowledge_point_id", name="uq_draft_prerequisite_edge"),
    )
    for column in ("draft_id", "prerequisite_knowledge_point_id", "dependent_knowledge_point_id"):
        op.create_index(op.f(f"ix_course_architecture_draft_prerequisites_{column}"), "course_architecture_draft_prerequisites", [column])

    op.create_table(
        "course_architecture_draft_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("draft_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(100), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["draft_id"], ["course_architecture_drafts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("draft_id", "version", name="uq_draft_version"),
    )
    op.create_index(op.f("ix_course_architecture_draft_versions_draft_id"), "course_architecture_draft_versions", ["draft_id"])

    op.create_table(
        "knowledge_point_prerequisites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prerequisite_knowledge_point_id", sa.Integer(), nullable=False),
        sa.Column("dependent_knowledge_point_id", sa.Integer(), nullable=False),
        sa.Column("relation_type", sa.String(32), server_default="prerequisite", nullable=False),
        sa.Column("source", sa.String(32), server_default="course_architecture", nullable=False),
        *timestamps(),
        sa.CheckConstraint("prerequisite_knowledge_point_id != dependent_knowledge_point_id", name=op.f("ck_knowledge_point_prerequisites_not_self")),
        sa.ForeignKeyConstraint(["prerequisite_knowledge_point_id"], ["knowledge_points.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dependent_knowledge_point_id"], ["knowledge_points.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("prerequisite_knowledge_point_id", "dependent_knowledge_point_id", name="uq_knowledge_point_prerequisite_edge"),
    )
    op.create_index(op.f("ix_knowledge_point_prerequisites_prerequisite_knowledge_point_id"), "knowledge_point_prerequisites", ["prerequisite_knowledge_point_id"])
    op.create_index(op.f("ix_knowledge_point_prerequisites_dependent_knowledge_point_id"), "knowledge_point_prerequisites", ["dependent_knowledge_point_id"])


def downgrade() -> None:
    for table in (
        "knowledge_point_prerequisites",
        "course_architecture_draft_versions",
        "course_architecture_draft_prerequisites",
        "course_architecture_draft_sources",
        "course_architecture_draft_knowledge_points",
        "course_architecture_draft_courses",
        "course_architecture_draft_materials",
        "course_architecture_drafts",
    ):
        op.drop_table(table)
