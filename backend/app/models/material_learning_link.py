from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class MaterialLearningLink(TimestampMixin, Base):
    __tablename__ = "material_learning_links"
    __table_args__ = (
        CheckConstraint(
            "(learning_goal_id IS NOT NULL) + (course_id IS NOT NULL) + "
            "(knowledge_point_id IS NOT NULL) = 1",
            name="exactly_one_target",
        ),
        CheckConstraint(
            "(target_type = 'learning_goal' AND learning_goal_id IS NOT NULL "
            "AND course_id IS NULL AND knowledge_point_id IS NULL) OR "
            "(target_type = 'course' AND course_id IS NOT NULL "
            "AND learning_goal_id IS NULL AND knowledge_point_id IS NULL) OR "
            "(target_type = 'knowledge_point' AND knowledge_point_id IS NOT NULL "
            "AND learning_goal_id IS NULL AND course_id IS NULL)",
            name="target_type_matches_foreign_key",
        ),
        CheckConstraint(
            "relation_type IN ('reference','primary_source','supplementary',"
            "'prerequisite','practice_source')",
            name="relation_type_valid",
        ),
        Index("ix_material_learning_links_material_target", "material_id", "target_type"),
        Index(
            "uq_material_learning_links_material_goal",
            "material_id",
            "learning_goal_id",
            unique=True,
            sqlite_where=text("learning_goal_id IS NOT NULL"),
        ),
        Index(
            "uq_material_learning_links_material_course",
            "material_id",
            "course_id",
            unique=True,
            sqlite_where=text("course_id IS NOT NULL"),
        ),
        Index(
            "uq_material_learning_links_material_point",
            "material_id",
            "knowledge_point_id",
            unique=True,
            sqlite_where=text("knowledge_point_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    learning_goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_goals.id", ondelete="CASCADE"), nullable=True, index=True
    )
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, index=True
    )
    knowledge_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=True, index=True
    )
    relation_type: Mapped[str] = mapped_column(
        String(32), default="reference", nullable=False, index=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    @property
    def target_id(self) -> int:
        value = {
            "learning_goal": self.learning_goal_id,
            "course": self.course_id,
            "knowledge_point": self.knowledge_point_id,
        }[self.target_type]
        assert value is not None
        return value
