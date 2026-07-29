from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import KnowledgePointStatus


class KnowledgePoint(TimestampMixin, Base):
    __tablename__ = "knowledge_points"
    __table_args__ = (
        UniqueConstraint(
            "course_id",
            "order_index",
            name="uq_knowledge_points_course_order",
        ),
        CheckConstraint("estimated_minutes >= 1", name="estimated_minutes_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    order_index: Mapped[int] = mapped_column(default=0, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(default=20, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=KnowledgePointStatus.not_started, nullable=False, index=True
    )
