from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RagCitation(Base):
    __tablename__ = "rag_citations"
    __table_args__ = (
        UniqueConstraint(
            "assistant_message_id",
            "source_label",
            name="uq_rag_citations_message_source_label",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assistant_message_id: Mapped[int] = mapped_column(
        ForeignKey("rag_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_label: Mapped[str] = mapped_column(String(16), nullable=False)
    chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_chunks.id", ondelete="SET NULL"),
        nullable=True,
    )
    material_id: Mapped[int | None] = mapped_column(
        ForeignKey("materials.id", ondelete="SET NULL"),
        nullable=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    learning_context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
