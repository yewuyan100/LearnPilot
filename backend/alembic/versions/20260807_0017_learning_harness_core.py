"""Add the V11B Learning Harness core audit records.

Revision ID: 20260807_0017
Revises: 20260807_0016
"""

from alembic import op
import sqlalchemy as sa


revision = "20260807_0017"
down_revision = "20260807_0016"
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
        "harness_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("actor_key", sa.String(200), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("surface_context", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("context_version", sa.String(64), nullable=True),
        sa.Column("selected_agent", sa.String(32), nullable=True),
        sa.Column("status", sa.String(32), server_default="accepted", nullable=False),
        sa.Column("result_summary", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("citations", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('accepted','running','awaiting_confirmation','completed','failed')",
            name=op.f("ck_harness_runs_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["agent_conversations.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("public_id", name="uq_harness_runs_public_id"),
        sa.UniqueConstraint("actor_key", "request_id", name="uq_harness_runs_actor_request"),
    )
    for column in ("public_id", "actor_key", "conversation_id", "status"):
        op.create_index(op.f(f"ix_harness_runs_{column}"), "harness_runs", [column])
    op.create_index("ix_harness_runs_actor_status", "harness_runs", ["actor_key", "status"])

    op.create_table(
        "learning_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("actor_key", sa.String(200), nullable=False),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", sa.String(100), nullable=False),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        sa.Column("causation_id", sa.String(100), nullable=True),
        sa.Column("harness_run_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "schema_version >= 1",
            name=op.f("ck_learning_events_schema_version_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["harness_run_id"], ["harness_runs.id"], ondelete="RESTRICT"
        ),
    )
    for column in ("event_type", "actor_key", "harness_run_id", "occurred_at"):
        op.create_index(op.f(f"ix_learning_events_{column}"), "learning_events", [column])
    op.create_index(
        "ix_learning_events_aggregate",
        "learning_events",
        ["aggregate_type", "aggregate_id"],
    )
    op.create_index(
        "ix_learning_events_correlation",
        "learning_events",
        ["correlation_id", "occurred_at"],
    )

    op.create_table(
        "learning_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column("proposal_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("source_harness_run_id", sa.Integer(), nullable=True),
        sa.Column("source_event_id", sa.String(36), nullable=True),
        sa.Column("target_type", sa.String(64), nullable=True),
        sa.Column("target_id", sa.String(100), nullable=True),
        sa.Column("context_version", sa.String(64), nullable=True),
        sa.Column("domain_draft_type", sa.String(64), nullable=True),
        sa.Column("domain_draft_id", sa.String(100), nullable=True),
        sa.Column("summary", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("rationale", sa.Text(), server_default="", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_request_id", sa.String(100), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('pending','accepted','rejected','expired')",
            name=op.f("ck_learning_proposals_status_valid"),
        ),
        sa.CheckConstraint(
            "version >= 1",
            name=op.f("ck_learning_proposals_version_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["source_harness_run_id"], ["harness_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_event_id"], ["learning_events.event_id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("public_id", name="uq_learning_proposals_public_id"),
        sa.UniqueConstraint(
            "decision_request_id", name="uq_learning_proposals_decision_request_id"
        ),
    )
    for column in (
        "public_id",
        "proposal_type",
        "status",
        "source_harness_run_id",
        "source_event_id",
    ):
        op.create_index(
            op.f(f"ix_learning_proposals_{column}"),
            "learning_proposals",
            [column],
        )

    with op.batch_alter_table("agent_runs") as batch:
        batch.add_column(sa.Column("harness_run_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_agent_runs_harness_run_id_harness_runs"),
            "harness_runs",
            ["harness_run_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index(op.f("ix_agent_runs_harness_run_id"), ["harness_run_id"])


def downgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_index(op.f("ix_agent_runs_harness_run_id"))
        batch.drop_constraint(
            op.f("fk_agent_runs_harness_run_id_harness_runs"), type_="foreignkey"
        )
        batch.drop_column("harness_run_id")

    op.drop_table("learning_proposals")
    op.drop_table("learning_events")
    op.drop_table("harness_runs")
