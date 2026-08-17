from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


NOTE_TYPES = ("quick", "study", "course", "knowledge_point", "material", "reflection")


class Note(TimestampMixin, Base):
    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint(
            "note_type IN ('quick','study','course','knowledge_point','material','reflection')",
            name="note_type_valid",
        ),
        CheckConstraint("status IN ('active','archived')", name="note_status_valid"),
        Index("ix_notes_status_updated", "status", "updated_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, default="", nullable=False)
    note_type: Mapped[str] = mapped_column(String(32), default="quick", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False, index=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
