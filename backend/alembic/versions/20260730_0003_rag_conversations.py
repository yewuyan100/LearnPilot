"""Add grounded RAG conversations, messages, and citation snapshots."""

from alembic import op
import sqlalchemy as sa


revision = "20260730_0003"
down_revision = "20260730_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rag_conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("default_top_k", sa.Integer(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rag_conversations_status", "rag_conversations", ["status"])

    op.create_table(
        "rag_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("rag_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reply_to_message_id", sa.Integer(), sa.ForeignKey("rag_messages.id", ondelete="CASCADE"), nullable=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("original_query", sa.String(2000), nullable=True),
        sa.Column("retrieval_query", sa.String(2000), nullable=True),
        sa.Column("answerable", sa.Boolean(), nullable=True),
        sa.Column("refusal_reason", sa.String(64), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("model_name", sa.String(255), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("conversation_id", "request_id", name="uq_rag_messages_conversation_request_id"),
    )
    op.create_index("ix_rag_messages_conversation_id", "rag_messages", ["conversation_id"])
    op.create_index(
        "ix_rag_messages_conversation_created",
        "rag_messages",
        ["conversation_id", "created_at", "id"],
    )

    op.create_table(
        "rag_citations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assistant_message_id", sa.Integer(), sa.ForeignKey("rag_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_label", sa.String(16), nullable=False),
        sa.Column("chunk_id", sa.Integer(), sa.ForeignKey("material_chunks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("material_id", sa.Integer(), sa.ForeignKey("materials.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_title", sa.String(500), nullable=True),
        sa.Column("content_excerpt", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("assistant_message_id", "source_label", name="uq_rag_citations_message_source_label"),
    )
    op.create_index("ix_rag_citations_assistant_message_id", "rag_citations", ["assistant_message_id"])


def downgrade() -> None:
    op.drop_table("rag_citations")
    op.drop_table("rag_messages")
    op.drop_table("rag_conversations")
