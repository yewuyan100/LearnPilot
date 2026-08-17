"""Add idempotent acceptance audit for computed next actions.

Revision ID: 20260805_0015
Revises: 20260805_0014
"""

from alembic import op
import sqlalchemy as sa


revision = "20260805_0015"
down_revision = "20260805_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "next_action_acceptances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("action_signature", sa.String(64), nullable=False),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("original_target_kind", sa.String(32), nullable=False),
        sa.Column("original_target_id", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.JSON(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.UniqueConstraint("request_id", name="uq_next_action_acceptances_request_id"),
    )
    for column in ("request_id", "action_signature", "action_type"):
        op.create_index(
            op.f(f"ix_next_action_acceptances_{column}"),
            "next_action_acceptances",
            [column],
        )


def downgrade() -> None:
    op.drop_table("next_action_acceptances")
