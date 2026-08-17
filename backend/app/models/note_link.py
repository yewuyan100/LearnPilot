from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class NoteLink(TimestampMixin, Base):
    __tablename__ = "note_links"
    __table_args__ = (
        UniqueConstraint(
            "note_id", "entity_type", "entity_id", "relation_type",
            name="uq_note_links_note_entity_relation",
        ),
        Index("ix_note_links_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(48), default="context", nullable=False)
