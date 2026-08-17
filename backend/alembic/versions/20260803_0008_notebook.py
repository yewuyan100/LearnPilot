"""Add notebook notes, validated links, source snapshots and tags.

Revision ID: 20260803_0008
Revises: 20260803_0007
"""

from alembic import op
import sqlalchemy as sa


revision = "20260803_0008"
down_revision = "20260803_0007"
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
        "notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("content_markdown", sa.Text(), server_default="", nullable=False),
        sa.Column("note_type", sa.String(length=32), server_default="quick", nullable=False),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("is_pinned", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "note_type IN ('quick','study','course','knowledge_point','material','reflection')",
            name=op.f("ck_notes_note_type_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('active','archived')", name=op.f("ck_notes_note_status_valid")
        ),
    )
    op.create_index("ix_notes_note_type", "notes", ["note_type"])
    op.create_index("ix_notes_status", "notes", ["status"])
    op.create_index("ix_notes_is_pinned", "notes", ["is_pinned"])
    op.create_index("ix_notes_status_updated", "notes", ["status", "updated_at", "id"])

    op.create_table(
        "note_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("note_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=48), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("relation_type", sa.String(length=48), server_default="context", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "note_id", "entity_type", "entity_id", "relation_type",
            name="uq_note_links_note_entity_relation",
        ),
    )
    op.create_index("ix_note_links_note_id", "note_links", ["note_id"])
    op.create_index("ix_note_links_entity", "note_links", ["entity_type", "entity_id"])

    op.create_table(
        "note_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("note_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=True),
        sa.Column("chunk_id", sa.Integer(), nullable=True),
        sa.Column("source_title", sa.String(length=500), nullable=False),
        sa.Column("source_locator", sa.String(length=500), nullable=True),
        sa.Column("quoted_text", sa.Text(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["chunk_id"], ["material_chunks.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_note_sources_note_id", "note_sources", ["note_id"])
    op.create_index("ix_note_sources_material_id", "note_sources", ["material_id"])
    op.create_index("ix_note_sources_chunk_id", "note_sources", ["chunk_id"])

    op.create_table(
        "note_tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("note_id", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(length=64), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("note_id", "tag", name="uq_note_tags_note_tag"),
    )
    op.create_index("ix_note_tags_note_id", "note_tags", ["note_id"])
    op.create_index("ix_note_tags_tag", "note_tags", ["tag"])


def downgrade() -> None:
    op.drop_table("note_tags")
    op.drop_table("note_sources")
    op.drop_table("note_links")
    op.drop_table("notes")
