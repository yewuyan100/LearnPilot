"""Add immutable Lesson runtime records.

Revision ID: 20260807_0018
Revises: 20260807_0017
"""

from alembic import op
import sqlalchemy as sa


revision = "20260807_0018"
down_revision = "20260807_0017"
branch_labels = None
depends_on = None


def timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.create_table(
        "lessons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("current_version_number", sa.Integer(), server_default="0", nullable=False),
        sa.Column("active_version_number", sa.Integer(), nullable=True),
        *timestamps(),
        sa.CheckConstraint("order_index >= 1", name=op.f("ck_lessons_order_index_positive")),
        sa.CheckConstraint(
            "current_version_number >= 0",
            name=op.f("ck_lessons_current_version_non_negative"),
        ),
        sa.CheckConstraint(
            "status IN ('draft','generating','review_required','ready','published','superseded','archived')",
            name=op.f("ck_lessons_status_valid"),
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("public_id", name="uq_lessons_public_id"),
        sa.UniqueConstraint("course_id", "order_index", name="uq_lessons_course_order"),
    )
    for column in ("public_id", "course_id", "status"):
        op.create_index(op.f(f"ix_lessons_{column}"), "lessons", [column])
    op.create_index("ix_lessons_course_status", "lessons", ["course_id", "status"])

    op.create_table(
        "lesson_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("objectives", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("examples", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("guided_practice", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("checks", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("generation_request_id", sa.String(100), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("quality_report", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "version_number >= 1",
            name=op.f("ck_lesson_versions_version_number_positive"),
        ),
        sa.CheckConstraint(
            "estimated_minutes >= 1",
            name=op.f("ck_lesson_versions_estimated_minutes_positive"),
        ),
        sa.CheckConstraint(
            "status IN ('draft','generating','review_required','ready','published','superseded','archived')",
            name=op.f("ck_lesson_versions_status_valid"),
        ),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("lesson_id", "version_number", name="uq_lesson_version_number"),
        sa.UniqueConstraint(
            "generation_request_id", name="uq_lesson_versions_generation_request_id"
        ),
    )
    for column in ("lesson_id", "status", "generation_request_id"):
        op.create_index(op.f(f"ix_lesson_versions_{column}"), "lesson_versions", [column])
    op.create_index(
        "ix_lesson_versions_lesson_status", "lesson_versions", ["lesson_id", "status"]
    )

    op.create_table(
        "lesson_version_knowledge_points",
        sa.Column("lesson_version_id", sa.Integer(), primary_key=True),
        sa.Column("knowledge_point_id", sa.Integer(), primary_key=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "order_index >= 1",
            name=op.f("ck_lesson_version_knowledge_points_order_index_positive"),
        ),
        sa.CheckConstraint(
            "role IN ('primary','supporting','prerequisite_context')",
            name=op.f("ck_lesson_version_knowledge_points_role_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["lesson_version_id"], ["lesson_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"], ["knowledge_points.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "lesson_version_id", "order_index", name="uq_lesson_version_point_order"
        ),
    )
    op.create_index(
        op.f("ix_lesson_version_knowledge_points_knowledge_point_id"),
        "lesson_version_knowledge_points",
        ["knowledge_point_id"],
    )

    op.create_table(
        "lesson_sources",
        sa.Column("lesson_version_id", sa.Integer(), primary_key=True),
        sa.Column("material_id", sa.Integer(), primary_key=True),
        sa.Column("material_chunk_id", sa.Integer(), nullable=True),
        sa.Column("source_role", sa.String(32), nullable=False),
        sa.Column("source_locator", sa.String(500), primary_key=True),
        sa.Column("quoted_text", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "source_role IN ('primary','supporting','example','prerequisite_context')",
            name=op.f("ck_lesson_sources_source_role_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["lesson_version_id"], ["lesson_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["material_chunk_id"], ["material_chunks.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        op.f("ix_lesson_sources_material_id"), "lesson_sources", ["material_id"]
    )
    op.create_index(
        op.f("ix_lesson_sources_material_chunk_id"),
        "lesson_sources",
        ["material_chunk_id"],
    )

    with op.batch_alter_table("learning_sessions") as batch:
        batch.add_column(sa.Column("lesson_version_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_learning_sessions_lesson_version_id_lesson_versions"),
            "lesson_versions",
            ["lesson_version_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index(
            op.f("ix_learning_sessions_lesson_version_id"), ["lesson_version_id"]
        )

    with op.batch_alter_table("study_plan_items") as batch:
        batch.add_column(sa.Column("lesson_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_study_plan_items_lesson_id_lessons"),
            "lessons",
            ["lesson_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index(op.f("ix_study_plan_items_lesson_id"), ["lesson_id"])


def downgrade() -> None:
    with op.batch_alter_table("study_plan_items") as batch:
        batch.drop_index(op.f("ix_study_plan_items_lesson_id"))
        batch.drop_constraint(
            op.f("fk_study_plan_items_lesson_id_lessons"), type_="foreignkey"
        )
        batch.drop_column("lesson_id")

    with op.batch_alter_table("learning_sessions") as batch:
        batch.drop_index(op.f("ix_learning_sessions_lesson_version_id"))
        batch.drop_constraint(
            op.f("fk_learning_sessions_lesson_version_id_lesson_versions"),
            type_="foreignkey",
        )
        batch.drop_column("lesson_version_id")

    op.drop_table("lesson_sources")
    op.drop_table("lesson_version_knowledge_points")
    op.drop_table("lesson_versions")
    op.drop_table("lessons")
