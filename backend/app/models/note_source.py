from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class NoteSource(TimestampMixin, Base):
    __tablename__ = "note_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material_id: Mapped[int | None] = mapped_column(
        ForeignKey("materials.id", ondelete="SET NULL"), nullable=True, index=True
    )
    chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_chunks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_locator: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quoted_text: Mapped[str] = mapped_column(Text, nullable=False)
