"""Add knowledge point sources and persisted RAG scope metadata.

Revision ID: 20260804_0010
Revises: 20260804_0009
"""

from alembic import op
import sqlalchemy as sa


revision = "20260804_0010"
down_revision = "20260804_0009"
branch_labels = None
depends_on = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
    )


def upgrade() -> None:
    op.create_table(
        "knowledge_point_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("material_chunk_id", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_locator", sa.String(length=500), nullable=True),
        sa.Column("quoted_text", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "source_type IN ('material','chunk','manual_reference')",
            name=op.f("ck_knowledge_point_sources_source_type_valid"),
        ),
        sa.CheckConstraint(
            "source_type != 'chunk' OR material_chunk_id IS NOT NULL",
            name=op.f("ck_knowledge_point_sources_chunk_source_has_chunk"),
        ),
        sa.CheckConstraint(
            "quoted_text IS NULL OR length(quoted_text) <= 4000",
            name=op.f("ck_knowledge_point_sources_quoted_text_length"),
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"], ["knowledge_points.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["material_chunk_id"], ["material_chunks.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_knowledge_point_sources_knowledge_point_id",
        "knowledge_point_sources", ["knowledge_point_id"],
    )
    op.create_index(
        "ix_knowledge_point_sources_material_id",
        "knowledge_point_sources", ["material_id"],
    )
    op.create_index(
        "ix_knowledge_point_sources_material_chunk_id",
        "knowledge_point_sources", ["material_chunk_id"],
    )
    op.create_index(
        "ix_knowledge_point_sources_source_type",
        "knowledge_point_sources", ["source_type"],
    )
    op.create_index(
        "ix_knowledge_point_sources_point_material",
        "knowledge_point_sources", ["knowledge_point_id", "material_id"],
    )
    op.create_index(
        "uq_knowledge_point_sources_point_chunk",
        "knowledge_point_sources", ["knowledge_point_id", "material_chunk_id"],
        unique=True,
    )
    with op.batch_alter_table("rag_messages") as batch:
        batch.add_column(
            sa.Column("retrieval_scope", sa.JSON(), server_default="{}", nullable=False)
        )
    with op.batch_alter_table("rag_citations") as batch:
        batch.add_column(
            sa.Column("learning_context", sa.JSON(), server_default="{}", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("rag_citations") as batch:
        batch.drop_column("learning_context")
    with op.batch_alter_table("rag_messages") as batch:
        batch.drop_column("retrieval_scope")
    op.drop_table("knowledge_point_sources")
