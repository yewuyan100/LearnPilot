from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class RagMessage(TimestampMixin, Base):
    __tablename__ = "rag_messages"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "request_id",
            name="uq_rag_messages_conversation_request_id",
        ),
        Index(
            "ix_rag_messages_conversation_created",
            "conversation_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("rag_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reply_to_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("rag_messages.id", ondelete="CASCADE"),
        nullable=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    original_query: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    retrieval_query: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    answerable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    refusal_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
