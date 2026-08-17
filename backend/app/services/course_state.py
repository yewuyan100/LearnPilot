import json
from collections import defaultdict, deque
from hashlib import sha256

from fastapi import status
from sqlalchemy import or_, select

from app.core.errors import AppError
from app.models import (
    Course,
    KnowledgePoint,
    KnowledgePointPrerequisite,
    KnowledgePointSource,
    Material,
    MaterialLearningLink,
)


class CourseStateService:
    """Formal-course integrity and snapshot interface shared by V10 modules."""

    def __init__(self, db):
        self.db = db

    def require_formal(self, course_id: int) -> tuple[Course, list[KnowledgePoint]]:
        course = self.db.get(Course, course_id)
        if course is None:
            raise AppError("course_not_found", "课程不存在", status.HTTP_404_NOT_FOUND)
        if course.status != "active":
            raise AppError(
                "course_not_published",
                "只有正式发布且可用的课程可以执行此操作",
                status.HTTP_409_CONFLICT,
            )
        points = list(
            self.db.scalars(
                select(KnowledgePoint)
                .where(
                    KnowledgePoint.course_id == course.id,
                    KnowledgePoint.lifecycle_status == "active",
                )
                .order_by(KnowledgePoint.order_index, KnowledgePoint.id)
            )
        )
        if not points:
            raise AppError("course_empty", "课程没有可执行知识点", status.HTTP_409_CONFLICT)
        self.topological_ids(points)
        return course, points

    def edges(self, points: list[KnowledgePoint]) -> list[KnowledgePointPrerequisite]:
        ids = [point.id for point in points]
        return list(
            self.db.scalars(
                select(KnowledgePointPrerequisite).where(
                    KnowledgePointPrerequisite.prerequisite_knowledge_point_id.in_(ids),
                    KnowledgePointPrerequisite.dependent_knowledge_point_id.in_(ids),
                )
            )
        )

    def topological_ids(
        self,
        points: list[KnowledgePoint],
        priority: dict[int, float] | None = None,
    ) -> list[int]:
        edges = self.edges(points)
        indegree = {point.id: 0 for point in points}
        outgoing: dict[int, list[int]] = defaultdict(list)
        hint = {point.id: (point.order_index, point.id) for point in points}
        priority = priority or {}

        def key(point_id: int):
            return (-priority.get(point_id, 0), *hint[point_id])

        for edge in edges:
            outgoing[edge.prerequisite_knowledge_point_id].append(edge.dependent_knowledge_point_id)
            indegree[edge.dependent_knowledge_point_id] += 1
        ready = sorted((pid for pid, degree in indegree.items() if degree == 0), key=key)
        ordered: list[int] = []
        while ready:
            current = ready.pop(0)
            ordered.append(current)
            for dependent in sorted(outgoing[current], key=key):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)
                    ready.sort(key=key)
        if len(ordered) != len(points):
            raise AppError(
                "course_prerequisite_cycle",
                "课程知识点前置关系存在环",
                status.HTTP_409_CONFLICT,
            )
        return ordered

    def snapshot_hash(self, course: Course, points: list[KnowledgePoint]) -> str:
        ids = [point.id for point in points]
        edges = self.edges(points)
        sources = list(
            self.db.scalars(
                select(KnowledgePointSource).where(KnowledgePointSource.knowledge_point_id.in_(ids))
            )
        )
        links = list(
            self.db.scalars(
                select(MaterialLearningLink).where(
                    or_(
                        MaterialLearningLink.learning_goal_id == course.learning_goal_id,
                        MaterialLearningLink.course_id == course.id,
                        MaterialLearningLink.knowledge_point_id.in_(ids),
                    )
                )
            )
        )
        material_ids = sorted({item.material_id for item in sources} | {item.material_id for item in links})
        materials = list(
            self.db.scalars(select(Material).where(Material.id.in_(material_ids)))
        ) if material_ids else []
        payload = {
            "course": [course.id, course.status, course.learning_goal_id, course.updated_at],
            "points": [
                [
                    p.id,
                    p.title,
                    p.description,
                    p.order_index,
                    p.estimated_minutes,
                    p.status,
                    p.lifecycle_status,
                    p.version,
                    p.updated_at,
                ]
                for p in points
            ],
            "edges": sorted(
                [e.prerequisite_knowledge_point_id, e.dependent_knowledge_point_id] for e in edges
            ),
            "sources": sorted(
                [s.id, s.knowledge_point_id, s.material_id, s.material_chunk_id, s.updated_at]
                for s in sources
            ),
            "links": sorted(
                [
                    link.id,
                    link.material_id,
                    link.target_type,
                    link.target_id,
                    link.relation_type,
                    link.updated_at,
                ]
                for link in links
            ),
            "materials": sorted(
                [m.id, m.deletion_status, m.indexing_status, m.updated_at] for m in materials
            ),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
        return sha256(raw.encode()).hexdigest()
