from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from fastapi import status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, not_found
from app.models.course import Course
from app.models.knowledge_point import KnowledgePoint
from app.models.learning_goal import LearningGoal
from app.models.material import Material
from app.models.material_learning_link import MaterialLearningLink
from app.schemas.material_learning import (
    EffectiveMaterialRead,
    MaterialLearningContextRead,
    MaterialLearningLinkCreate,
    MaterialLearningLinkRead,
    MaterialLearningLinkUpdate,
)


TargetType = Literal["learning_goal", "course", "knowledge_point"]


@dataclass(frozen=True)
class TargetContext:
    target_type: TargetType
    target_id: int
    title: str
    learning_goal_id: int
    course_id: int | None = None


@dataclass(frozen=True)
class MaterialScopeResolution:
    requested_scope: dict[str, int | list[int] | None]
    resolved_material_ids: list[int] | None
    scoped: bool

    @property
    def empty(self) -> bool:
        return self.scoped and not self.resolved_material_ids


class MaterialLearningLinkService:
    """The only write boundary for user-confirmed material learning ownership."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_link(
        self, material_id: int, payload: MaterialLearningLinkCreate, *, commit: bool = True
    ) -> MaterialLearningLinkRead:
        return self.bulk_create_links(material_id, [payload], commit=commit)[0]

    def bulk_create_links(
        self,
        material_id: int,
        payloads: Sequence[MaterialLearningLinkCreate],
        *,
        commit: bool = True,
    ) -> list[MaterialLearningLinkRead]:
        """Create links atomically; an existing target link is returned unchanged."""
        material = self._get_active_material(material_id)
        unique_payloads = self._deduplicate_payloads(payloads)
        existing = self._links_for_material(material_id)
        all_keys = {(link.target_type, link.target_id) for link in existing}
        all_keys.update((item.target_type, item.target_id) for item in unique_payloads)
        contexts = self._load_target_contexts(all_keys)
        self.validate_hierarchy(existing, unique_payloads, contexts)

        existing_by_key = {(item.target_type, item.target_id): item for item in existing}
        result: list[MaterialLearningLink] = []
        for payload in unique_payloads:
            key = (payload.target_type, payload.target_id)
            current = existing_by_key.get(key)
            if current is not None:
                result.append(current)
                continue
            link = MaterialLearningLink(
                material_id=material.id,
                target_type=payload.target_type,
                learning_goal_id=payload.learning_goal_id,
                course_id=payload.course_id,
                knowledge_point_id=payload.knowledge_point_id,
                relation_type=payload.relation_type,
                is_primary=payload.is_primary,
            )
            self.db.add(link)
            result.append(link)

        try:
            if commit:
                self.db.commit()
            else:
                self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(
                "material_learning_link_conflict",
                "The material learning link conflicts with an existing relationship.",
                status.HTTP_409_CONFLICT,
            ) from exc
        if commit:
            for link in result:
                self.db.refresh(link)
        return [self._serialize_link(item, contexts[(item.target_type, item.target_id)]) for item in result]

    def list_material_links(self, material_id: int) -> list[MaterialLearningLinkRead]:
        self._get_active_material(material_id)
        links = self._links_for_material(material_id)
        contexts = self._load_target_contexts(
            {(item.target_type, item.target_id) for item in links}
        )
        return [self._serialize_link(item, contexts[(item.target_type, item.target_id)]) for item in links]

    def update_link(
        self,
        material_id: int,
        link_id: int,
        payload: MaterialLearningLinkUpdate,
    ) -> MaterialLearningLinkRead:
        self._get_active_material(material_id)
        link = self.db.scalar(
            select(MaterialLearningLink).where(
                MaterialLearningLink.id == link_id,
                MaterialLearningLink.material_id == material_id,
            )
        )
        if link is None:
            raise not_found("material learning link", link_id)
        for name, value in payload.model_dump(exclude_none=True).items():
            setattr(link, name, value)
        self.db.commit()
        self.db.refresh(link)
        context = self._load_target_contexts({(link.target_type, link.target_id)})[
            (link.target_type, link.target_id)
        ]
        return self._serialize_link(link, context)

    def delete_link(self, material_id: int, link_id: int) -> None:
        self._get_active_material(material_id)
        link = self.db.scalar(
            select(MaterialLearningLink).where(
                MaterialLearningLink.id == link_id,
                MaterialLearningLink.material_id == material_id,
            )
        )
        if link is None:
            raise not_found("material learning link", link_id)
        self.db.delete(link)
        self.db.commit()

    def validate_hierarchy(
        self,
        existing: Sequence[MaterialLearningLink],
        additions: Sequence[MaterialLearningLinkCreate],
        contexts: dict[tuple[str, int], TargetContext],
    ) -> None:
        keys = {(item.target_type, item.target_id) for item in existing}
        keys.update((item.target_type, item.target_id) for item in additions)
        direct_goals = {target_id for target_type, target_id in keys if target_type == "learning_goal"}
        direct_courses = {target_id for target_type, target_id in keys if target_type == "course"}
        child_contexts = [contexts[key] for key in keys if key[0] != "learning_goal"]
        child_goals = {item.learning_goal_id for item in child_contexts}
        point_courses = {
            item.course_id for item in child_contexts
            if item.target_type == "knowledge_point" and item.course_id is not None
        }
        if len(child_goals) > 1:
            self._raise_hierarchy_conflict("course and knowledge point links must share one goal")
        if direct_goals and child_goals and not child_goals.issubset(direct_goals):
            self._raise_hierarchy_conflict("child links must belong to an explicitly linked goal")
        if direct_courses and point_courses and not point_courses.issubset(direct_courses):
            self._raise_hierarchy_conflict("knowledge point links must belong to an explicitly linked course")

    def check_duplicate(
        self, material_id: int, target_type: TargetType, target_id: int
    ) -> MaterialLearningLink | None:
        return self.db.scalar(
            select(MaterialLearningLink).where(
                MaterialLearningLink.material_id == material_id,
                MaterialLearningLink.target_type == target_type,
                self._target_column(target_type) == target_id,
            )
        )

    def summarize_links(self, material_ids: Iterable[int]) -> dict[int, int]:
        ids = set(material_ids)
        summary = {material_id: 0 for material_id in ids}
        if not ids:
            return summary
        links = self.db.scalars(
            select(MaterialLearningLink).where(MaterialLearningLink.material_id.in_(ids))
        ).all()
        for link in links:
            summary[link.material_id] += 1
        return summary

    def _get_active_material(self, material_id: int) -> Material:
        material = self.db.get(Material, material_id)
        if material is None:
            raise not_found("material", material_id)
        if material.deletion_status != "active":
            raise AppError(
                "material_unavailable",
                "A material pending deletion cannot be linked to learning content.",
                status.HTTP_409_CONFLICT,
                {"material_id": material_id, "deletion_status": material.deletion_status},
            )
        return material

    def _links_for_material(self, material_id: int) -> list[MaterialLearningLink]:
        return list(
            self.db.scalars(
                select(MaterialLearningLink)
                .where(MaterialLearningLink.material_id == material_id)
                .order_by(MaterialLearningLink.created_at, MaterialLearningLink.id)
            )
        )

    def _deduplicate_payloads(
        self, payloads: Sequence[MaterialLearningLinkCreate]
    ) -> list[MaterialLearningLinkCreate]:
        if not payloads:
            raise AppError(
                "material_learning_links_empty",
                "At least one link is required.",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        unique: dict[tuple[str, int], MaterialLearningLinkCreate] = {}
        for payload in payloads:
            key = (payload.target_type, payload.target_id)
            previous = unique.get(key)
            if previous is not None and previous != payload:
                raise AppError(
                    "material_learning_link_duplicate_payload",
                    "The same target appears with conflicting relationship details.",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    {"target_type": payload.target_type, "target_id": payload.target_id},
                )
            unique[key] = payload
        return list(unique.values())

    def _load_target_contexts(
        self, keys: set[tuple[str, int]]
    ) -> dict[tuple[str, int], TargetContext]:
        goal_ids = {target_id for target_type, target_id in keys if target_type == "learning_goal"}
        course_ids = {target_id for target_type, target_id in keys if target_type == "course"}
        point_ids = {target_id for target_type, target_id in keys if target_type == "knowledge_point"}
        goals = {item.id: item for item in self.db.scalars(select(LearningGoal).where(LearningGoal.id.in_(goal_ids)))} if goal_ids else {}
        points = {item.id: item for item in self.db.scalars(select(KnowledgePoint).where(KnowledgePoint.id.in_(point_ids)))} if point_ids else {}
        course_ids.update(item.course_id for item in points.values())
        courses = {item.id: item for item in self.db.scalars(select(Course).where(Course.id.in_(course_ids)))} if course_ids else {}

        contexts: dict[tuple[str, int], TargetContext] = {}
        for goal_id, goal in goals.items():
            contexts[("learning_goal", goal_id)] = TargetContext(
                "learning_goal", goal_id, goal.title, goal_id
            )
        for course_id, course in courses.items():
            if ("course", course_id) in keys:
                contexts[("course", course_id)] = TargetContext(
                    "course", course_id, course.title, course.learning_goal_id, course_id
                )
        for point_id, point in points.items():
            course = courses.get(point.course_id)
            if course is not None:
                contexts[("knowledge_point", point_id)] = TargetContext(
                    "knowledge_point", point_id, point.title, course.learning_goal_id, point.course_id
                )
        missing = keys.difference(contexts)
        if missing:
            target_type, target_id = sorted(missing)[0]
            raise AppError(
                "material_learning_target_not_found",
                "The selected learning target does not exist.",
                status.HTTP_404_NOT_FOUND,
                {"target_type": target_type, "target_id": target_id},
            )
        return contexts

    @staticmethod
    def _target_column(target_type: TargetType):
        return {
            "learning_goal": MaterialLearningLink.learning_goal_id,
            "course": MaterialLearningLink.course_id,
            "knowledge_point": MaterialLearningLink.knowledge_point_id,
        }[target_type]

    @staticmethod
    def _serialize_link(
        link: MaterialLearningLink, context: TargetContext
    ) -> MaterialLearningLinkRead:
        return MaterialLearningLinkRead(
            id=link.id,
            material_id=link.material_id,
            target_type=link.target_type,
            target_id=link.target_id,
            target_title=context.title,
            relation_type=link.relation_type,
            is_primary=link.is_primary,
            created_at=link.created_at,
            updated_at=link.updated_at,
        )

    @staticmethod
    def _raise_hierarchy_conflict(reason: str) -> None:
        raise AppError(
            "material_learning_hierarchy_conflict",
            "The material links would cross incompatible learning branches.",
            status.HTTP_409_CONFLICT,
            {"reason": reason},
        )


class MaterialScopeResolver:
    """Compute effective visibility from direct links without persisting inherited rows."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_target_materials(
        self, target_type: TargetType, target_id: int
    ) -> list[EffectiveMaterialRead]:
        target = self._resolve_target(target_type, target_id)
        rows = self.db.execute(
            select(MaterialLearningLink, Material)
            .join(Material, Material.id == MaterialLearningLink.material_id)
            .where(
                Material.deletion_status == "active",
                Material.archived_at.is_(None),
                self._visibility_filter(target),
            )
            .order_by(Material.updated_at.desc(), Material.id.desc(), MaterialLearningLink.id)
        ).all()
        keys = {(link.target_type, link.target_id) for link, _ in rows}
        contexts = MaterialLearningLinkService(self.db)._load_target_contexts(keys)
        grouped: dict[int, list[MaterialLearningContextRead]] = defaultdict(list)
        materials: dict[int, Material] = {}
        for link, material in rows:
            materials[material.id] = material
            target_context = contexts[(link.target_type, link.target_id)]
            grouped[material.id].append(
                self._serialize_context(link, material, target_context, target)
            )
        return [
            EffectiveMaterialRead(
                material_id=material.id,
                material_title=material.title,
                original_filename=material.original_filename,
                source_type=material.source_type,
                processing_status=material.processing_status,
                ingestion_status=material.ingestion_status,
                indexing_status=material.indexing_status,
                deletion_status=material.deletion_status,
                contexts=grouped[material.id],
            )
            for material in materials.values()
        ]

    def list_all_direct_contexts(
        self, material_ids: Sequence[int] | None = None
    ) -> list[MaterialLearningContextRead]:
        statement = (
            select(MaterialLearningLink, Material)
            .join(Material, Material.id == MaterialLearningLink.material_id)
            .where(Material.deletion_status == "active")
            .order_by(MaterialLearningLink.material_id, MaterialLearningLink.id)
        )
        if material_ids is not None:
            if not material_ids:
                return []
            statement = statement.where(MaterialLearningLink.material_id.in_(set(material_ids)))
        rows = self.db.execute(statement).all()
        contexts = MaterialLearningLinkService(self.db)._load_target_contexts(
            {(link.target_type, link.target_id) for link, _ in rows}
        )
        return [
            self._serialize_context(
                link,
                material,
                contexts[(link.target_type, link.target_id)],
                contexts[(link.target_type, link.target_id)],
            )
            for link, material in rows
        ]

    def resolve_effective_material_ids(
        self,
        target_type: TargetType,
        target_id: int,
        explicit_material_ids: Sequence[int] | None = None,
        *,
        searchable_only: bool = True,
    ) -> list[int]:
        items = self.list_target_materials(target_type, target_id)
        resolved = {item.material_id for item in items}
        if searchable_only:
            resolved = {
                item.material_id for item in items
                if item.ingestion_status == "completed" and item.indexing_status == "completed"
            }
        if explicit_material_ids is not None:
            resolved.intersection_update(explicit_material_ids)
        return sorted(resolved)

    def resolve_combined_scope(
        self,
        *,
        learning_goal_id: int | None = None,
        course_id: int | None = None,
        knowledge_point_id: int | None = None,
        material_ids: Sequence[int] | None = None,
        searchable_only: bool = True,
    ) -> MaterialScopeResolution:
        requested = {
            "learning_goal_id": learning_goal_id,
            "course_id": course_id,
            "knowledge_point_id": knowledge_point_id,
            "material_ids": list(dict.fromkeys(material_ids)) if material_ids is not None else None,
        }
        sets: list[set[int]] = []
        if learning_goal_id is not None:
            sets.append(set(self.resolve_effective_material_ids(
                "learning_goal", learning_goal_id, searchable_only=searchable_only
            )))
        if course_id is not None:
            sets.append(set(self.resolve_effective_material_ids(
                "course", course_id, searchable_only=searchable_only
            )))
        if knowledge_point_id is not None:
            sets.append(set(self.resolve_effective_material_ids(
                "knowledge_point", knowledge_point_id, searchable_only=searchable_only
            )))
        if material_ids is not None:
            explicit = set(material_ids)
            if explicit:
                rows = list(self.db.scalars(select(Material).where(Material.id.in_(explicit))))
                found = {item.id for item in rows}
                missing = explicit.difference(found)
                if missing:
                    raise AppError(
                        "material_not_found",
                        "One or more selected materials do not exist.",
                        status.HTTP_404_NOT_FOUND,
                        {"material_ids": sorted(missing)},
                    )
                explicit = {
                    item.id for item in rows
                    if item.deletion_status == "active"
                    and (
                        not searchable_only
                        or (item.ingestion_status == "completed" and item.indexing_status == "completed")
                    )
                }
            sets.append(explicit)
        scoped = bool(sets)
        if not sets:
            resolved = None
        else:
            resolved_set = set.intersection(*sets) if len(sets) > 1 else sets[0]
            resolved = sorted(resolved_set)
        return MaterialScopeResolution(requested, resolved, scoped)

    def material_link_contexts(self, material_ids: Sequence[int]) -> dict[int, list[dict]]:
        ids = set(material_ids)
        result: dict[int, list[dict]] = {material_id: [] for material_id in ids}
        if not ids:
            return result
        links = list(self.db.scalars(
            select(MaterialLearningLink)
            .where(MaterialLearningLink.material_id.in_(ids))
            .order_by(MaterialLearningLink.material_id, MaterialLearningLink.id)
        ))
        contexts = MaterialLearningLinkService(self.db)._load_target_contexts(
            {(item.target_type, item.target_id) for item in links}
        )
        for link in links:
            target = contexts[(link.target_type, link.target_id)]
            result[link.material_id].append({
                "target_type": link.target_type,
                "target_id": link.target_id,
                "target_title": target.title,
                "relation_type": link.relation_type,
            })
        return result

    def _resolve_target(self, target_type: TargetType, target_id: int) -> TargetContext:
        return MaterialLearningLinkService(self.db)._load_target_contexts({(target_type, target_id)})[
            (target_type, target_id)
        ]

    @staticmethod
    def _visibility_filter(target: TargetContext):
        if target.target_type == "learning_goal":
            course_ids = select(Course.id).where(Course.learning_goal_id == target.target_id)
            point_ids = select(KnowledgePoint.id).where(KnowledgePoint.course_id.in_(course_ids))
            return or_(
                MaterialLearningLink.learning_goal_id == target.target_id,
                MaterialLearningLink.course_id.in_(course_ids),
                MaterialLearningLink.knowledge_point_id.in_(point_ids),
            )
        if target.target_type == "course":
            point_ids = select(KnowledgePoint.id).where(KnowledgePoint.course_id == target.target_id)
            return or_(
                MaterialLearningLink.learning_goal_id == target.learning_goal_id,
                MaterialLearningLink.course_id == target.target_id,
                MaterialLearningLink.knowledge_point_id.in_(point_ids),
            )
        return or_(
            MaterialLearningLink.learning_goal_id == target.learning_goal_id,
            MaterialLearningLink.course_id == target.course_id,
            MaterialLearningLink.knowledge_point_id == target.target_id,
        )

    @staticmethod
    def _serialize_context(
        link: MaterialLearningLink,
        material: Material,
        source: TargetContext,
        requested: TargetContext,
    ) -> MaterialLearningContextRead:
        if link.target_type == requested.target_type and link.target_id == requested.target_id:
            visibility = "direct"
        elif requested.target_type == "learning_goal":
            visibility = "descendant"
        elif requested.target_type == "course" and link.target_type == "knowledge_point":
            visibility = "descendant"
        else:
            visibility = "inherited"
        return MaterialLearningContextRead(
            id=link.id,
            material_id=material.id,
            material_title=material.title,
            original_filename=material.original_filename,
            source_type=material.source_type,
            processing_status=material.processing_status,
            ingestion_status=material.ingestion_status,
            indexing_status=material.indexing_status,
            deletion_status=material.deletion_status,
            target_type=link.target_type,
            target_id=link.target_id,
            target_title=source.title,
            relation_type=link.relation_type,
            is_primary=link.is_primary,
            visibility=visibility,
            created_at=link.created_at,
            updated_at=link.updated_at,
        )
