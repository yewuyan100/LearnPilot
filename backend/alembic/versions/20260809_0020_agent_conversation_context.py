"""Bind Agent conversations to one explicit product context.

Revision ID: 20260809_0020
Revises: 20260807_0019
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_0020"
down_revision = "20260807_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_conversations") as batch:
        batch.add_column(
            sa.Column("context_type", sa.String(length=16), nullable=False, server_default="general")
        )
        batch.add_column(sa.Column("context_id", sa.Integer(), nullable=True))
        batch.create_check_constraint(
            "ck_agent_conversation_context_valid",
            "(context_type = 'general' AND context_id IS NULL) OR "
            "(context_type IN ('goal', 'material', 'lesson') AND context_id IS NOT NULL)",
        )
    op.create_index(
        "ix_agent_conversations_context",
        "agent_conversations",
        ["context_type", "context_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_conversations_context", table_name="agent_conversations")
    with op.batch_alter_table("agent_conversations") as batch:
        batch.drop_constraint("ck_agent_conversation_context_valid", type_="check")
        batch.drop_column("context_id")
        batch.drop_column("context_type")
