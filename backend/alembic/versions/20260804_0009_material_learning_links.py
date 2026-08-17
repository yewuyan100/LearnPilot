"""Add direct material links to learning goals, courses and knowledge points.

Revision ID: 20260804_0009
Revises: 20260803_0008
"""

from alembic import op
import sqlalchemy as sa


revision = "20260804_0009"
down_revision = "20260803_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "material_learning_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("learning_goal_id", sa.Integer(), nullable=True),
        sa.Column("course_id", sa.Integer(), nullable=True),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=True),
        sa.Column(
            "relation_type", sa.String(length=32), server_default="reference", nullable=False
        ),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.CheckConstraint(
            "(learning_goal_id IS NOT NULL) + (course_id IS NOT NULL) + "
            "(knowledge_point_id IS NOT NULL) = 1",
            name=op.f("ck_material_learning_links_exactly_one_target"),
        ),
        sa.CheckConstraint(
            "(target_type = 'learning_goal' AND learning_goal_id IS NOT NULL "
            "AND course_id IS NULL AND knowledge_point_id IS NULL) OR "
            "(target_type = 'course' AND course_id IS NOT NULL "
            "AND learning_goal_id IS NULL AND knowledge_point_id IS NULL) OR "
            "(target_type = 'knowledge_point' AND knowledge_point_id IS NOT NULL "
            "AND learning_goal_id IS NULL AND course_id IS NULL)",
            name=op.f("ck_material_learning_links_target_type_matches_foreign_key"),
        ),
        sa.CheckConstraint(
            "relation_type IN ('reference','primary_source','supplementary',"
            "'prerequisite','practice_source')",
            name=op.f("ck_material_learning_links_relation_type_valid"),
        ),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["learning_goal_id"], ["learning_goals.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"], ["knowledge_points.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_material_learning_links_material_id", "material_learning_links", ["material_id"]
    )
    op.create_index(
        "ix_material_learning_links_target_type", "material_learning_links", ["target_type"]
    )
    op.create_index(
        "ix_material_learning_links_learning_goal_id",
        "material_learning_links", ["learning_goal_id"],
    )
    op.create_index(
        "ix_material_learning_links_course_id", "material_learning_links", ["course_id"]
    )
    op.create_index(
        "ix_material_learning_links_knowledge_point_id",
        "material_learning_links", ["knowledge_point_id"],
    )
    op.create_index(
        "ix_material_learning_links_relation_type",
        "material_learning_links", ["relation_type"],
    )
    op.create_index(
        "ix_material_learning_links_material_target",
        "material_learning_links", ["material_id", "target_type"],
    )
    op.create_index(
        "uq_material_learning_links_material_goal",
        "material_learning_links", ["material_id", "learning_goal_id"],
        unique=True, sqlite_where=sa.text("learning_goal_id IS NOT NULL"),
    )
    op.create_index(
        "uq_material_learning_links_material_course",
        "material_learning_links", ["material_id", "course_id"],
        unique=True, sqlite_where=sa.text("course_id IS NOT NULL"),
    )
    op.create_index(
        "uq_material_learning_links_material_point",
        "material_learning_links", ["material_id", "knowledge_point_id"],
        unique=True, sqlite_where=sa.text("knowledge_point_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("material_learning_links")
