"""Add recoverable maintenance and material deletion state."""

from alembic import op
import sqlalchemy as sa


revision = "20260803_0007"
down_revision = "20260801_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("materials") as batch:
        batch.add_column(sa.Column("deletion_status", sa.String(24), nullable=False, server_default="active"))
        batch.add_column(sa.Column("deletion_error", sa.Text()))
        batch.add_column(sa.Column("deletion_requested_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("deletion_attempts", sa.Integer(), nullable=False, server_default="0"))
        batch.create_index("ix_materials_deletion_status", ["deletion_status"])

    op.create_table(
        "maintenance_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_type", sa.String(48), nullable=False),
        sa.Column("entity_type", sa.String(48), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("request_key", sa.String(160), nullable=False, unique=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("stage", sa.String(48), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("result", sa.JSON()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_maintenance_tasks_task_type", "maintenance_tasks", ["task_type"])
    op.create_index("ix_maintenance_tasks_status", "maintenance_tasks", ["status"])
    op.create_index("ix_maintenance_tasks_entity", "maintenance_tasks", ["entity_type", "entity_id"])
    op.create_index("ix_maintenance_tasks_status_updated", "maintenance_tasks", ["status", "updated_at"])


def downgrade() -> None:
    op.drop_table("maintenance_tasks")
    with op.batch_alter_table("materials") as batch:
        batch.drop_index("ix_materials_deletion_status")
        batch.drop_column("deletion_attempts")
        batch.drop_column("deletion_requested_at")
        batch.drop_column("deletion_error")
        batch.drop_column("deletion_status")
