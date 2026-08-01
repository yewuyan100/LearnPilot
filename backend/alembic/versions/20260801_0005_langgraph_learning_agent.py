"""Add checkpointed LangGraph learning agent audit tables."""

from alembic import op
import sqlalchemy as sa

revision = "20260801_0005"
down_revision = "20260730_0004"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table("agent_conversations",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("thread_id", sa.String(64), nullable=False, unique=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True)), *timestamps())
    op.create_index("ix_agent_conversations_status", "agent_conversations", ["status"])
    op.create_table("agent_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("agent_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False), sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False), sa.Column("status", sa.String(32), nullable=False, server_default="accepted"),
        sa.Column("intent", sa.String(64)), sa.Column("prompt_versions", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("final_answer", sa.Text()), sa.Column("citations", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("error_code", sa.String(64)), sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)), *timestamps(),
        sa.UniqueConstraint("conversation_id", "request_id", name="uq_agent_runs_conversation_request"))
    op.create_index("ix_agent_runs_conversation_id", "agent_runs", ["conversation_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_runs_conversation_created", "agent_runs", ["conversation_id", "created_at", "id"])
    op.create_table("agent_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("agent_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="SET NULL")),
        sa.Column("role", sa.String(16), nullable=False), sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False, server_default="[]"), *timestamps())
    op.create_index("ix_agent_messages_conversation_id", "agent_messages", ["conversation_id"])
    op.create_index("ix_agent_messages_run_id", "agent_messages", ["run_id"])
    op.create_index("ix_agent_messages_conversation_created", "agent_messages", ["conversation_id", "created_at", "id"])
    op.create_table("agent_tool_calls",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False), sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("tool_kind", sa.String(16), nullable=False), sa.Column("arguments", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("arguments_hash", sa.String(64), nullable=False), sa.Column("status", sa.String(24), nullable=False),
        sa.Column("result", sa.JSON()), sa.Column("error_code", sa.String(64)), sa.Column("duration_ms", sa.Integer()), *timestamps(),
        sa.UniqueConstraint("run_id", "step_index", name="uq_agent_tool_calls_run_step"))
    op.create_index("ix_agent_tool_calls_run_id", "agent_tool_calls", ["run_id"])
    op.create_index("ix_agent_tool_calls_run_created", "agent_tool_calls", ["run_id", "created_at", "id"])
    op.create_table("agent_confirmations",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_call_id", sa.Integer(), sa.ForeignKey("agent_tool_calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False), sa.Column("arguments_snapshot", sa.JSON(), nullable=False),
        sa.Column("arguments_hash", sa.String(64), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("approved", sa.Boolean()), sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), *timestamps(),
        sa.UniqueConstraint("run_id", name="uq_agent_confirmations_run_id"))
    op.create_index("ix_agent_confirmations_run_id", "agent_confirmations", ["run_id"])
    op.create_index("ix_agent_confirmations_tool_call_id", "agent_confirmations", ["tool_call_id"])
    op.create_index("ix_agent_confirmations_status", "agent_confirmations", ["status"])


def downgrade() -> None:
    op.drop_table("agent_confirmations")
    op.drop_table("agent_tool_calls")
    op.drop_table("agent_messages")
    op.drop_table("agent_runs")
    op.drop_table("agent_conversations")
