"""Add the V11D curriculum proposal lifecycle fields.

Revision ID: 20260807_0019
Revises: 20260807_0018
"""

from alembic import op
import sqlalchemy as sa


revision = "20260807_0019"
down_revision = "20260807_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("learning_proposals") as batch:
        batch.add_column(
            sa.Column("generation_request_id", sa.String(length=100), nullable=True)
        )
        batch.create_unique_constraint(
            "uq_learning_proposals_generation_request_id",
            ["generation_request_id"],
        )
        batch.drop_constraint(
            op.f("ck_learning_proposals_status_valid"),
            type_="check",
        )
        batch.create_check_constraint(
            op.f("ck_learning_proposals_status_valid"),
            "status IN ('pending','review_required','accepted','rejected','expired')",
        )
    op.create_index(
        op.f("ix_learning_proposals_generation_request_id"),
        "learning_proposals",
        ["generation_request_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_learning_proposals_generation_request_id"),
        table_name="learning_proposals",
    )
    with op.batch_alter_table("learning_proposals") as batch:
        batch.drop_constraint(
            op.f("ck_learning_proposals_status_valid"),
            type_="check",
        )
        batch.create_check_constraint(
            op.f("ck_learning_proposals_status_valid"),
            "status IN ('pending','accepted','rejected','expired')",
        )
        batch.drop_constraint(
            "uq_learning_proposals_generation_request_id",
            type_="unique",
        )
        batch.drop_column("generation_request_id")
