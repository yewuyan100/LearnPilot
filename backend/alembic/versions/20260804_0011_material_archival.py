"""Add a single archival state for inbox materials.

Revision ID: 20260804_0011
Revises: 20260804_0010
"""

from alembic import op
import sqlalchemy as sa


revision = "20260804_0011"
down_revision = "20260804_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("materials") as batch:
        batch.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_materials_archived_at", ["archived_at"])


def downgrade() -> None:
    with op.batch_alter_table("materials") as batch:
        batch.drop_index("ix_materials_archived_at")
        batch.drop_column("archived_at")
