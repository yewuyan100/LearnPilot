"""Add V2 material ingestion fields and persisted chunks."""

from alembic import op
import sqlalchemy as sa


revision = "20260730_0002"
down_revision = "20260729_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("materials") as batch:
        batch.add_column(
            sa.Column(
                "ingestion_status",
                sa.String(32),
                nullable=False,
                server_default="pending",
            )
        )
        batch.add_column(
            sa.Column(
                "indexing_status",
                sa.String(32),
                nullable=False,
                server_default="pending",
            )
        )
        batch.add_column(
            sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column(
                "indexed_chunk_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_materials_ingestion_status", ["ingestion_status"])
        batch.create_index("ix_materials_indexing_status", ["indexing_status"])

    op.create_table(
        "material_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "material_id",
            sa.Integer(),
            sa.ForeignKey("materials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_title", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "material_id",
            "chunk_index",
            name="uq_material_chunks_material_chunk_index",
        ),
        sa.CheckConstraint(
            "chunk_index >= 0",
            name="ck_material_chunks_chunk_index_non_negative",
        ),
        sa.CheckConstraint(
            "char_count > 0",
            name="ck_material_chunks_char_count_positive",
        ),
    )
    op.create_index(
        "ix_material_chunks_material_id",
        "material_chunks",
        ["material_id"],
    )


def downgrade() -> None:
    op.drop_table("material_chunks")
    with op.batch_alter_table("materials") as batch:
        batch.drop_index("ix_materials_indexing_status")
        batch.drop_index("ix_materials_ingestion_status")
        batch.drop_column("indexed_at")
        batch.drop_column("processed_at")
        batch.drop_column("indexed_chunk_count")
        batch.drop_column("chunk_count")
        batch.drop_column("indexing_status")
        batch.drop_column("ingestion_status")
