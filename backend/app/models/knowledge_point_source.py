from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class KnowledgePointSource(TimestampMixin, Base):
    __tablename__ = "knowledge_point_sources"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('material','chunk','manual_reference')",
            name="source_type_valid",
        ),
        CheckConstraint(
            "source_type != 'chunk' OR material_chunk_id IS NOT NULL",
            name="chunk_source_has_chunk",
        ),
        CheckConstraint(
            "quoted_text IS NULL OR length(quoted_text) <= 4000",
            name="quoted_text_length",
        ),
        Index(
            "ix_knowledge_point_sources_point_material",
            "knowledge_point_id",
            "material_id",
        ),
        Index(
            "uq_knowledge_point_sources_point_chunk",
            "knowledge_point_id",
            "material_chunk_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material_chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_chunks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_locator: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quoted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
