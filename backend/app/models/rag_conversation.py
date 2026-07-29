from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class RagConversation(TimestampMixin, Base):
    __tablename__ = "rag_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="新建资料问答")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    default_top_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
