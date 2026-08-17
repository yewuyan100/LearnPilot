from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import uuid4

from fastapi import status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import AppError, not_found
from app.models.course_architecture import (
    CourseArchitectureDraft,
    CourseArchitectureDraftCourse,
    CourseArchitectureDraftKnowledgePoint,
    CourseArchitectureDraftMaterial,
    CourseArchitectureDraftPrerequisite,
    CourseArchitectureDraftSource,
    CourseArchitectureDraftVersion,
)
from app.models.learning_goal import LearningGoal
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.schemas.course_architecture import (
    CourseArchitectureImport,
    DraftCourseCreate,
    DraftCourseRead,
    DraftCourseUpdate,
    DraftKnowledgePointCreate,
    DraftKnowledgePointMerge,
    DraftKnowledgePointMove,
    DraftKnowledgePointRead,
    DraftKnowledgePointUpdate,
    DraftListItem,
    DraftListResponse,
    DraftMaterialRead,
    DraftPrerequisiteCreate,
    DraftPrerequisiteRead,
    DraftRead,
    DraftReorder,
    DraftSourceCreate,
    DraftSourceRead,
)
from app.services.course_architecture.graph import has_cycle, normalize_title


EDITABLE_STATUSES = {"draft", "review_required", "ready", "failed"}


class CourseArchitectureDraftService:
    """Own the draft aggregate and hide its relational representation from routes."""

    def __init__(self, db: Session, clock: Clock) -> None:
        self.db = db
        self.clock = clock

    def create_draft(
        self,
        *,
        learning_goal_id: int,
        material_ids: Sequence[int],
        title: str | None,
        description: str,
    ) -> DraftRead:
        goal = self.db.get(LearningGoal, learning_goal_id)
        if goal is None:
            raise not_found("学习目标", learning_goal_id)
        materials = self.validate_materials(material_ids)
        draft = CourseArchitectureDraft(
            public_id=str(uuid4()),
            learning_goal_id=goal.id,
            title=(title or f"{goal.title}课程架构").strip(),
            description=description,
        )
        self.db.add(draft)
        self.db.flush()
        self._replace_material_rows(draft, materials)
        self.db.commit()
        return self.get_draft(draft.id)

    def import_structure(
        self,
        payload: CourseArchitectureImport,
        *,
        commit: bool = True,
    ) -> DraftRead:
        """Materialize a proposal as an unpublished draft aggregate.

        The caller supplies reviewed structure, while this Module owns all ORM
        details and source/prerequisite integrity. Formal facts are still only
        created by CourseArchitecturePublishingService.
        """

        goal = self.db.get(LearningGoal, payload.learning_goal_id)
        if goal is None:
            raise not_found("学习目标", payload.learning_goal_id)
        materials = self.validate_materials(payload.material_ids) if payload.material_ids else []
        material_ids = {item.id for item in materials}
        chunk_ids = {
            chunk_id
            for course in payload.courses
            for point in course.knowledge_points
            for chunk_id in point.source_chunk_ids
        }
        chunks = {
            item.id: item
            for item in self.db.scalars(select(MaterialChunk).where(MaterialChunk.id.in_(chunk_ids)))
        } if chunk_ids else {}
        invalid_chunks = sorted(
            chunk_id
            for chunk_id in chunk_ids
            if chunk_id not in chunks or chunks[chunk_id].material_id not in material_ids
        )
        if invalid_chunks:
            raise AppError(
                "draft_import_source_invalid",
                "课程架构导入引用了资料范围外的片段。",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {"chunk_ids": invalid_chunks},
            )

        draft = CourseArchitectureDraft(
            public_id=str(uuid4()),
            learning_goal_id=goal.id,
            title=payload.title.strip(),
            description=payload.description,
            status="review_required",
            generation_status="completed",
            generation_mode=payload.generation_mode,
            model_name=payload.model_name,
            prompt_version=payload.prompt_version,
            generation_request_id=payload.generation_request_id,
            generation_progress={"stage": "proposal_imported", "progress": 100},
            quality_status="not_checked",
        )
        self.db.add(draft)
        self.db.flush()
        self._replace_material_rows(draft, materials)

        points_by_title: dict[str, CourseArchitectureDraftKnowledgePoint] = {}
        for course_index, course_input in enumerate(payload.courses):
            course = CourseArchitectureDraftCourse(
                draft_id=draft.id,
                title=course_input.title.strip(),
                description=course_input.description,
                order_index=course_index,
                learning_outcomes=course_input.learning_outcomes,
                origin="curriculum",
            )
            self.db.add(course)
            self.db.flush()
            for point_index, point_input in enumerate(course_input.knowledge_points):
                normalized = normalize_title(point_input.title)
                if normalized in points_by_title:
                    raise AppError(
                        "draft_import_point_duplicate",
                        "课程架构导入包含重复知识点名称。",
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                    )
                point = CourseArchitectureDraftKnowledgePoint(
                    draft_course_id=course.id,
                    title=point_input.title.strip(),
                    description=point_input.description,
                    order_index=point_index,
                    learning_objectives=point_input.learning_objectives,
                    key_terms=point_input.key_terms,
                    difficulty_label=point_input.difficulty_label,
                    origin="curriculum",
                    source_status="valid" if point_input.source_chunk_ids else "missing",
                )
                self.db.add(point)
                self.db.flush()
                points_by_title[normalized] = point
                for chunk_id in dict.fromkeys(point_input.source_chunk_ids):
                    chunk = chunks[chunk_id]
                    self.db.add(
                        CourseArchitectureDraftSource(
                            draft_knowledge_point_id=point.id,
                            material_id=chunk.material_id,
                            material_chunk_id=chunk.id,
                            source_locator=self._locator(chunk),
                            quoted_text=chunk.content[:2000],
                            source_role="primary",
                            origin="curriculum",
                        )
                    )

        edge_pairs: list[tuple[int, int]] = []
        for edge in payload.prerequisites:
            source = points_by_title.get(normalize_title(edge.prerequisite_title))
            target = points_by_title.get(normalize_title(edge.dependent_title))
            if source is None or target is None or source.draft_course_id != target.draft_course_id:
                raise AppError(
                    "draft_import_prerequisite_invalid",
                    "课程架构导入包含无效或跨课程的前置关系。",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            edge_pairs.append((source.id, target.id))
            self.db.add(
                CourseArchitectureDraftPrerequisite(
                    draft_id=draft.id,
                    prerequisite_knowledge_point_id=source.id,
                    dependent_knowledge_point_id=target.id,
                    rationale=edge.rationale,
                    confidence=edge.confidence,
                    origin="curriculum",
                )
            )
        if has_cycle(edge_pairs):
            raise AppError(
                "draft_import_prerequisite_cycle",
                "课程架构导入的前置关系存在循环。",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return self.get_draft(draft.id)

    def list_drafts(self, *, include_archived: bool = False) -> DraftListResponse:
        material_count = (
            select(func.count(CourseArchitectureDraftMaterial.id))
            .where(CourseArchitectureDraftMaterial.draft_id == CourseArchitectureDraft.id)
            .correlate(CourseArchitectureDraft)
            .scalar_subquery()
        )
        course_count = (
            select(func.count(CourseArchitectureDraftCourse.id))
            .where(CourseArchitectureDraftCourse.draft_id == CourseArchitectureDraft.id)
            .correlate(CourseArchitectureDraft)
            .scalar_subquery()
        )
        point_count = (
            select(func.count(CourseArchitectureDraftKnowledgePoint.id))
            .join(
                CourseArchitectureDraftCourse,
                CourseArchitectureDraftCourse.id
                == CourseArchitectureDraftKnowledgePoint.draft_course_id,
            )
            .where(CourseArchitectureDraftCourse.draft_id == CourseArchitectureDraft.id)
            .correlate(CourseArchitectureDraft)
            .scalar_subquery()
        )
        statement = (
            select(
                CourseArchitectureDraft,
                LearningGoal.title,
                material_count,
                course_count,
                point_count,
            )
            .join(LearningGoal, LearningGoal.id == CourseArchitectureDraft.learning_goal_id)
            .order_by(CourseArchitectureDraft.updated_at.desc(), CourseArchitectureDraft.id.desc())
        )
        if not include_archived:
            statement = statement.where(CourseArchitectureDraft.status != "archived")
        rows = self.db.execute(statement).all()
        return DraftListResponse(
            items=[
                DraftListItem(
                    id=draft.id,
                    public_id=draft.public_id,
                    learning_goal_id=draft.learning_goal_id,
                    learning_goal_title=goal_title,
                    title=draft.title,
                    status=draft.status,
                    generation_status=draft.generation_status,
                    version=draft.version,
                    quality_status=draft.quality_status,
                    material_count=materials or 0,
                    course_count=courses or 0,
                    knowledge_point_count=points or 0,
                    created_at=draft.created_at,
                    updated_at=draft.updated_at,
                )
                for draft, goal_title, materials, courses, points in rows
            ],
            total=len(rows),
        )

    def get_draft(self, draft_id: int) -> DraftRead:
        draft = self._get(draft_id)
        goal_title = self.db.scalar(
            select(LearningGoal.title).where(LearningGoal.id == draft.learning_goal_id)
        )
        material_rows = self.db.execute(
            select(CourseArchitectureDraftMaterial, Material)
            .join(Material, Material.id == CourseArchitectureDraftMaterial.material_id)
            .where(CourseArchitectureDraftMaterial.draft_id == draft.id)
            .order_by(CourseArchitectureDraftMaterial.order_index)
        ).all()
        courses = list(
            self.db.scalars(
                select(CourseArchitectureDraftCourse)
                .where(CourseArchitectureDraftCourse.draft_id == draft.id)
                .order_by(CourseArchitectureDraftCourse.order_index, CourseArchitectureDraftCourse.id)
            )
        )
        course_ids = [item.id for item in courses]
        points = list(
            self.db.scalars(
                select(CourseArchitectureDraftKnowledgePoint)
                .where(CourseArchitectureDraftKnowledgePoint.draft_course_id.in_(course_ids))
                .order_by(
                    CourseArchitectureDraftKnowledgePoint.draft_course_id,
                    CourseArchitectureDraftKnowledgePoint.order_index,
                    CourseArchitectureDraftKnowledgePoint.id,
                )
            )
        ) if course_ids else []
        point_ids = [item.id for item in points]
        source_rows = self.db.execute(
            select(CourseArchitectureDraftSource, Material, MaterialChunk)
            .join(Material, Material.id == CourseArchitectureDraftSource.material_id)
            .join(MaterialChunk, MaterialChunk.id == CourseArchitectureDraftSource.material_chunk_id)
            .where(CourseArchitectureDraftSource.draft_knowledge_point_id.in_(point_ids))
            .order_by(CourseArchitectureDraftSource.id)
        ).all() if point_ids else []
        source_map: dict[int, list[DraftSourceRead]] = {point_id: [] for point_id in point_ids}
        for source, material, chunk in source_rows:
            source_map[source.draft_knowledge_point_id].append(
                self._source_read(source, material, chunk)
            )
        point_map: dict[int, list[DraftKnowledgePointRead]] = {course.id: [] for course in courses}
        title_by_point: dict[int, str] = {}
        for point in points:
            title_by_point[point.id] = point.title
            point_map[point.draft_course_id].append(
                DraftKnowledgePointRead(
                    **self._timestamps(point),
                    draft_course_id=point.draft_course_id,
                    title=point.title,
                    description=point.description,
                    order_index=point.order_index,
                    learning_objectives=point.learning_objectives,
                    key_terms=point.key_terms,
                    granularity_label=point.granularity_label,
                    difficulty_label=point.difficulty_label,
                    origin=point.origin,
                    is_locked=point.is_locked,
                    user_modified=point.user_modified,
                    source_status=point.source_status,
                    validation_status=point.validation_status,
                    published_knowledge_point_id=point.published_knowledge_point_id,
                    sources=source_map[point.id],
                )
            )
        prerequisite_rows = list(
            self.db.scalars(
                select(CourseArchitectureDraftPrerequisite)
                .where(CourseArchitectureDraftPrerequisite.draft_id == draft.id)
                .order_by(CourseArchitectureDraftPrerequisite.id)
            )
        )
        return DraftRead(
            **self._timestamps(draft),
            public_id=draft.public_id,
            learning_goal_id=draft.learning_goal_id,
            learning_goal_title=goal_title or "",
            title=draft.title,
            description=draft.description,
            status=draft.status,
            generation_status=draft.generation_status,
            version=draft.version,
            source_snapshot_version=draft.source_snapshot_version,
            generation_mode=draft.generation_mode,
            model_name=draft.model_name,
            prompt_version=draft.prompt_version,
            generation_progress=draft.generation_progress,
            last_error_code=draft.last_error_code,
            last_error_message=draft.last_error_message,
            quality_status=draft.quality_status,
            quality_report=draft.quality_report,
            publish_request_id=draft.publish_request_id,
            published_at=draft.published_at,
            archived_at=draft.archived_at,
            materials=[self._material_read(row, material) for row, material in material_rows],
            courses=[
                DraftCourseRead(
                    **self._timestamps(course),
                    draft_id=course.draft_id,
                    title=course.title,
                    description=course.description,
                    order_index=course.order_index,
                    learning_outcomes=course.learning_outcomes,
                    origin=course.origin,
                    is_locked=course.is_locked,
                    user_modified=course.user_modified,
                    published_course_id=course.published_course_id,
                    knowledge_points=point_map[course.id],
                )
                for course in courses
            ],
            prerequisites=[
                DraftPrerequisiteRead(
                    **self._timestamps(edge),
                    draft_id=edge.draft_id,
                    prerequisite_knowledge_point_id=edge.prerequisite_knowledge_point_id,
                    prerequisite_title=title_by_point.get(edge.prerequisite_knowledge_point_id, ""),
                    dependent_knowledge_point_id=edge.dependent_knowledge_point_id,
                    dependent_title=title_by_point.get(edge.dependent_knowledge_point_id, ""),
                    rationale=edge.rationale,
                    confidence=edge.confidence,
                    origin=edge.origin,
                    validation_status=edge.validation_status,
                )
                for edge in prerequisite_rows
            ],
        )

    def update_draft(
        self, draft_id: int, *, version: int, title: str | None, description: str | None
    ) -> DraftRead:
        draft = self._editable(draft_id, version)
        if title is not None:
            draft.title = title.strip()
        if description is not None:
            draft.description = description
        self._bump(draft)
        self.db.commit()
        return self.get_draft(draft.id)

    def archive_draft(self, draft_id: int, *, version: int) -> None:
        draft = self._editable(draft_id, version)
        draft.status = "archived"
        draft.archived_at = self.clock.now()
        self._bump(draft)
        self.db.commit()

    def create_version_from_published(self, draft_id: int) -> DraftRead:
        """Clone a published snapshot into a new editable aggregate.

        The formal entities remain untouched; only reviewed draft structure and
        still-valid source references are copied.
        """
        source = self._get(draft_id)
        if source.status != "published":
            raise AppError(
                "draft_version_source_not_published",
                "只有已发布草案可以创建新的编辑版本",
                status.HTTP_409_CONFLICT,
            )
        material_ids = list(
            self.db.scalars(
                select(CourseArchitectureDraftMaterial.material_id)
                .where(CourseArchitectureDraftMaterial.draft_id == source.id)
                .order_by(CourseArchitectureDraftMaterial.order_index)
            )
        )
        materials = self.validate_materials(material_ids)
        clone = CourseArchitectureDraft(
            public_id=str(uuid4()),
            learning_goal_id=source.learning_goal_id,
            title=f"{source.title} · 新版本",
            description=source.description,
            status="review_required",
            generation_status="not_started",
            generation_mode="manual",
            quality_status="not_checked",
        )
        self.db.add(clone)
        self.db.flush()
        self._replace_material_rows(clone, materials)

        course_map: dict[int, int] = {}
        point_map: dict[int, int] = {}
        source_courses = list(
            self.db.scalars(
                select(CourseArchitectureDraftCourse)
                .where(CourseArchitectureDraftCourse.draft_id == source.id)
                .order_by(CourseArchitectureDraftCourse.order_index, CourseArchitectureDraftCourse.id)
            )
        )
        for old_course in source_courses:
            new_course = CourseArchitectureDraftCourse(
                draft_id=clone.id,
                title=old_course.title,
                description=old_course.description,
                order_index=old_course.order_index,
                learning_outcomes=old_course.learning_outcomes,
                origin=old_course.origin,
                is_locked=old_course.is_locked,
                user_modified=old_course.user_modified,
            )
            self.db.add(new_course)
            self.db.flush()
            course_map[old_course.id] = new_course.id
        source_points = list(
            self.db.scalars(
                select(CourseArchitectureDraftKnowledgePoint)
                .where(CourseArchitectureDraftKnowledgePoint.draft_course_id.in_(course_map))
                .order_by(
                    CourseArchitectureDraftKnowledgePoint.draft_course_id,
                    CourseArchitectureDraftKnowledgePoint.order_index,
                    CourseArchitectureDraftKnowledgePoint.id,
                )
            )
        )
        for old_point in source_points:
            new_point = CourseArchitectureDraftKnowledgePoint(
                draft_course_id=course_map[old_point.draft_course_id],
                title=old_point.title,
                description=old_point.description,
                order_index=old_point.order_index,
                learning_objectives=old_point.learning_objectives,
                key_terms=old_point.key_terms,
                granularity_label=old_point.granularity_label,
                difficulty_label=old_point.difficulty_label,
                origin=old_point.origin,
                is_locked=old_point.is_locked,
                user_modified=old_point.user_modified,
                source_status=old_point.source_status,
                validation_status="unchecked",
            )
            self.db.add(new_point)
            self.db.flush()
            point_map[old_point.id] = new_point.id
        for old_source in self.db.scalars(
            select(CourseArchitectureDraftSource).where(
                CourseArchitectureDraftSource.draft_knowledge_point_id.in_(point_map)
            )
        ):
            self.db.add(
                CourseArchitectureDraftSource(
                    draft_knowledge_point_id=point_map[old_source.draft_knowledge_point_id],
                    material_id=old_source.material_id,
                    material_chunk_id=old_source.material_chunk_id,
                    source_locator=old_source.source_locator,
                    quoted_text=old_source.quoted_text,
                    source_role=old_source.source_role,
                    relevance_score=old_source.relevance_score,
                    origin=old_source.origin,
                )
            )
        for old_edge in self.db.scalars(
            select(CourseArchitectureDraftPrerequisite).where(
                CourseArchitectureDraftPrerequisite.draft_id == source.id
            )
        ):
            self.db.add(
                CourseArchitectureDraftPrerequisite(
                    draft_id=clone.id,
                    prerequisite_knowledge_point_id=point_map[old_edge.prerequisite_knowledge_point_id],
                    dependent_knowledge_point_id=point_map[old_edge.dependent_knowledge_point_id],
                    rationale=old_edge.rationale,
                    confidence=old_edge.confidence,
                    origin=old_edge.origin,
                    validation_status="valid",
                )
            )
        self.db.commit()
        return self.get_draft(clone.id)

    def replace_materials(
        self, draft_id: int, *, version: int, material_ids: Sequence[int]
    ) -> DraftRead:
        draft = self._editable(draft_id, version)
        materials = self.validate_materials(material_ids)
        self.db.execute(
            delete(CourseArchitectureDraftMaterial).where(
                CourseArchitectureDraftMaterial.draft_id == draft.id
            )
        )
        self._replace_material_rows(draft, materials)
        draft.source_snapshot_version += 1
        if draft.generation_mode == "curriculum_goal_only":
            draft.generation_mode = "curriculum_source_grounded"
        draft.quality_status = "stale"
        draft.status = "review_required"
        self._bump(draft)
        self.db.commit()
        return self.get_draft(draft.id)

    def add_course(self, draft_id: int, payload: DraftCourseCreate) -> DraftRead:
        draft = self._editable(draft_id, payload.version)
        course = CourseArchitectureDraftCourse(
            draft_id=draft.id,
            title=payload.title.strip(),
            description=payload.description,
            order_index=payload.order_index,
            learning_outcomes=payload.learning_outcomes,
            origin="manual",
            user_modified=True,
        )
        self.db.add(course)
        self._bump(draft)
        self.db.commit()
        return self.get_draft(draft.id)

    def update_course(
        self, draft_id: int, course_id: int, payload: DraftCourseUpdate
    ) -> DraftRead:
        draft = self._editable(draft_id, payload.version)
        course = self._draft_course(draft.id, course_id)
        values = payload.model_dump(exclude={"version"}, exclude_unset=True)
        for field, value in values.items():
            setattr(course, field, value.strip() if field == "title" else value)
        course.user_modified = True
        self._bump(draft)
        self.db.commit()
        return self.get_draft(draft.id)

    def reorder_courses(self, draft_id: int, payload: DraftReorder) -> DraftRead:
        draft = self._editable(draft_id, payload.version)
        courses = list(
            self.db.scalars(
                select(CourseArchitectureDraftCourse).where(
                    CourseArchitectureDraftCourse.draft_id == draft.id
                )
            )
        )
        self._apply_order(courses, payload.items, "course")
        self._bump(draft)
        self.db.commit()
        return self.get_draft(draft.id)

    def delete_course(self, draft_id: int, course_id: int, *, version: int) -> DraftRead:
        draft = self._editable(draft_id, version)
        self.db.delete(self._draft_course(draft.id, course_id))
        self._bump(draft)
        self.db.commit()
        return self.get_draft(draft.id)

    def add_knowledge_point(
        self, draft_id: int, payload: DraftKnowledgePointCreate
    ) -> DraftRead:
        draft = self._editable(draft_id, payload.version)
        course = self._draft_course(draft.id, payload.draft_course_id)
        self._ensure_unique_point_title(course.id, payload.title)
        point = CourseArchitectureDraftKnowledgePoint(
            draft_course_id=course.id,
            title=payload.title.strip(),
            description=payload.description,
            order_index=payload.order_index,
            learning_objectives=payload.learning_objectives,
            key_terms=payload.key_terms,
            granularity_label=payload.granularity_label,
            difficulty_label=payload.difficulty_label,
            origin="manual",
            user_modified=True,
            source_status="missing",
        )
        self.db.add(point)
        self._bump(draft)
        self.db.commit()
        return self.get_draft(draft.id)

    def update_knowledge_point(
        self, draft_id: int, point_id: int, payload: DraftKnowledgePointUpdate
    ) -> DraftRead:
        draft = self._editable(draft_id, payload.version)
        point = self._draft_point(draft.id, point_id)
        values = payload.model_dump(exclude={"version"}, exclude_unset=True)
        if "title" in values:
            self._ensure_unique_point_title(point.draft_course_id, values["title"], point.id)
        for field, value in values.items():
            setattr(point, field, value.strip() if field == "title" else value)
        point.user_modified = True
        self._bump(draft)
        self.db.commit()
        return self.get_draft(draft.id)

    def reorder_knowledge_points(self, draft_id: int, payload: DraftReorder) -> DraftRead:
        draft = self._editable(draft_id, payload.version)
        point_ids = [item.id for item in payload.items]
        points = list(
            self.db.scalars(
                select(CourseArchitectureDraftKnowledgePoint)
                .join(
                    CourseArchitectureDraftCourse,
                    CourseArchitectureDraftCourse.id
                    == CourseArchitectureDraftKnowledgePoint.draft_course_id,
                )
                .where(
                    CourseArchitectureDraftCourse.draft_id == draft.id,
                    CourseArchitectureDraftKnowledgePoint.id.in_(point_ids),
                )
            )
        )
        self._apply_order(points, payload.items, "knowledge point", require_exact=True)
        for point in points:
            point.user_modified = True
        self._bump(draft)
        self.db.commit()
        return self.get_draft(draft.id)

    def move_knowledge_point(
        self, draft_id: int, payload: DraftKnowledgePointMove
    ) -> DraftRead:
        draft = self._editable(draft_id, payload.version)
        point = self._draft_point(draft.id, payload.knowledge_point_id)
        target = self._draft_course(draft.id, payload.target_course_id)
        if point.draft_course_id != target.id:
            point.draft_course_id = target.id
            self._delete_cross_course_edges(draft.id)
        point.order_index = payload.order_index
        point.user_modified = True
        self._bump(draft)
        self.db.commit()
        return self.get_draft(draft.id)

    def merge_knowledge_points(
        self, draft_id: int, payload: DraftKnowledgePointMerge
    ) -> DraftRead:
        draft = self._editable(draft_id, payload.version)
        keep = self._draft_point(draft.id, payload.keep_knowledge_point_id)
        merge_ids = set(payload.merge_knowledge_point_ids)
        if keep.id in merge_ids:
            raise AppError("draft_merge_self", "保留知识点不能同时作为被合并项", status.HTTP_422_UNPROCESSABLE_ENTITY)
        merged = [self._draft_point(draft.id, point_id) for point_id in merge_ids]
        if any(point.draft_course_id != keep.draft_course_id for point in merged):
            raise AppError("draft_merge_cross_course", "只能合并同一草案课程内的知识点", status.HTTP_409_CONFLICT)
        if payload.title is not None:
            keep.title = payload.title.strip()
        if payload.description is not None:
            keep.description = payload.description
        existing_chunks = set(
            self.db.scalars(
                select(CourseArchitectureDraftSource.material_chunk_id).where(
                    CourseArchitectureDraftSource.draft_knowledge_point_id == keep.id
                )
            )
        )
        sources = list(
            self.db.scalars(
                select(CourseArchitectureDraftSource).where(
                    CourseArchitectureDraftSource.draft_knowledge_point_id.in_(merge_ids)
                )
            )
        )
        for source in sources:
            if source.material_chunk_id in existing_chunks:
                self.db.delete(source)
            else:
                source.draft_knowledge_point_id = keep.id
                existing_chunks.add(source.material_chunk_id)
        self._merge_edges(draft.id, keep.id, merge_ids)
        for point in merged:
            self.db.delete(point)
        keep.user_modified = True
        keep.source_status = "valid" if existing_chunks else "missing"
        self._bump(draft)
        self.db.commit()
        return self.get_draft(draft.id)

    def delete_knowledge_point(self, draft_id: int, point_id: int, *, version: int) -> DraftRead:
        draft = self._editable(draft_id, version)
        self.db.delete(self._draft_point(draft.id, point_id))
        self._bump(draft)
        self.db.commit()
        return self.get_draft(draft.id)

    def add_source(
        self, draft_id: int, point_id: int, payload: DraftSourceCreate
    ) -> DraftRead:
        draft = self._editable(draft_id, payload.version)
        point = self._draft_point(draft.id, point_id)
        allowed_material_ids = set(
            self.db.scalars(
                select(CourseArchitectureDraftMaterial.material_id).where(
                    CourseArchitectureDraftMaterial.draft_id == draft.id
                )
            )
        )
        if payload.material_id not in allowed_material_ids:
            raise AppError("draft_source_out_of_scope", "来源资料不在草案选择范围内", status.HTTP_409_CONFLICT)
        chunk = self.db.get(MaterialChunk, payload.material_chunk_id)
        if chunk is None:
            raise not_found("资料片段", payload.material_chunk_id)
        if chunk.material_id != payload.material_id:
            raise AppError("draft_source_chunk_mismatch", "来源片段不属于所选资料", status.HTTP_422_UNPROCESSABLE_ENTITY)
        existing = self.db.scalar(
            select(CourseArchitectureDraftSource).where(
                CourseArchitectureDraftSource.draft_knowledge_point_id == point.id,
                CourseArchitectureDraftSource.material_chunk_id == chunk.id,
                CourseArchitectureDraftSource.source_role == payload.source_role,
            )
        )
        if existing is None:
            self.db.add(
                CourseArchitectureDraftSource(
                    draft_knowledge_point_id=point.id,
                    material_id=payload.material_id,
                    material_chunk_id=chunk.id,
                    source_locator=payload.source_locator or self._locator(chunk),
                    quoted_text=payload.quoted_text or chunk.content[:2000],
                    source_role=payload.source_role,
                    relevance_score=payload.relevance_score,
                    origin="manual",
                )
            )
        point.source_status = "valid"
        point.user_modified = True
        self._bump(draft)
        self.db.commit()
        return self.get_draft(draft.id)

    def delete_source(self, draft_id: int, source_id: int, *, version: int) -> DraftRead:
        draft = self._editable(draft_id, version)
        source = self.db.scalar(
            select(CourseArchitectureDraftSource)
            .join(
                CourseArchitectureDraftKnowledgePoint,
                CourseArchitectureDraftKnowledgePoint.id
                == CourseArchitectureDraftSource.draft_knowledge_point_id,
            )
            .join(
                CourseArchitectureDraftCourse,
                CourseArchitectureDraftCourse.id
                == CourseArchitectureDraftKnowledgePoint.draft_course_id,
            )
            .where(
                CourseArchitectureDraftSource.id == source_id,
                CourseArchitectureDraftCourse.draft_id == draft.id,
            )
        )
        if source is None:
            raise not_found("草案来源", source_id)
        point_id = source.draft_knowledge_point_id
        self.db.delete(source)
        self.db.flush()
        point = self.db.get(CourseArchitectureDraftKnowledgePoint, point_id)
        remaining = self.db.scalar(
            select(func.count(CourseArchitectureDraftSource.id)).where(
                CourseArchitectureDraftSource.draft_knowledge_point_id == point_id
            )
        )
        if point is not None:
            point.source_status = "valid" if remaining else "missing"
            point.user_modified = True
        self._bump(draft)
        self.db.commit()
        return self.get_draft(draft.id)

    def add_prerequisite(
        self, draft_id: int, payload: DraftPrerequisiteCreate
    ) -> DraftRead:
        draft = self._editable(draft_id, payload.version)
        source = self._draft_point(draft.id, payload.prerequisite_knowledge_point_id)
        target = self._draft_point(draft.id, payload.dependent_knowledge_point_id)
        if source.id == target.id:
            raise AppError("draft_prerequisite_self", "知识点不能依赖自身", status.HTTP_422_UNPROCESSABLE_ENTITY)
        if source.draft_course_id != target.draft_course_id:
            raise AppError("draft_prerequisite_cross_course", "V9 只支持同一草案课程内的前置关系", status.HTTP_409_CONFLICT)
        existing = self.db.scalar(
            select(CourseArchitectureDraftPrerequisite).where(
                CourseArchitectureDraftPrerequisite.draft_id == draft.id,
                CourseArchitectureDraftPrerequisite.prerequisite_knowledge_point_id == source.id,
                CourseArchitectureDraftPrerequisite.dependent_knowledge_point_id == target.id,
            )
        )
        if existing is None:
            edges = self._edge_pairs(draft.id) + [(source.id, target.id)]
            if has_cycle(edges):
                raise AppError("draft_prerequisite_cycle", "该前置关系会形成循环", status.HTTP_409_CONFLICT)
            self.db.add(
                CourseArchitectureDraftPrerequisite(
                    draft_id=draft.id,
                    prerequisite_knowledge_point_id=source.id,
                    dependent_knowledge_point_id=target.id,
                    rationale=payload.rationale,
                    confidence=payload.confidence,
                    origin="manual",
                )
            )
        self._bump(draft)
        self.db.commit()
        return self.get_draft(draft.id)

    def delete_prerequisite(self, draft_id: int, edge_id: int, *, version: int) -> DraftRead:
        draft = self._editable(draft_id, version)
        edge = self.db.scalar(
            select(CourseArchitectureDraftPrerequisite).where(
                CourseArchitectureDraftPrerequisite.id == edge_id,
                CourseArchitectureDraftPrerequisite.draft_id == draft.id,
            )
        )
        if edge is None:
            raise not_found("草案前置关系", edge_id)
        self.db.delete(edge)
        self._bump(draft)
        self.db.commit()
        return self.get_draft(draft.id)

    def save_version_snapshot(self, draft_id: int, reason: str) -> None:
        draft = self._get(draft_id)
        self.db.add(
            CourseArchitectureDraftVersion(
                draft_id=draft.id,
                version=draft.version,
                reason=reason,
                snapshot=self.get_draft(draft.id).model_dump(mode="json"),
            )
        )
        self.db.flush()

    def validate_materials(self, material_ids: Sequence[int]) -> list[Material]:
        unique_ids = list(dict.fromkeys(material_ids))
        if not unique_ids:
            raise AppError("draft_materials_empty", "课程架构草案至少需要一份资料", status.HTTP_422_UNPROCESSABLE_ENTITY)
        materials = {
            item.id: item
            for item in self.db.scalars(select(Material).where(Material.id.in_(unique_ids)))
        }
        missing = [item for item in unique_ids if item not in materials]
        if missing:
            raise AppError("draft_material_not_found", "一份或多份资料不存在", status.HTTP_404_NOT_FOUND, {"material_ids": missing})
        for material_id in unique_ids:
            material = materials[material_id]
            reason = None
            if material.archived_at is not None:
                reason = "archived"
            elif material.deletion_status != "active":
                reason = material.deletion_status
            elif material.ingestion_status != "completed":
                reason = "not_processed"
            elif material.indexing_status != "completed":
                reason = "not_indexed"
            elif material.chunk_count <= 0:
                reason = "no_chunks"
            if reason:
                raise AppError(
                    "draft_material_unavailable",
                    "所选资料尚未满足课程架构分析条件",
                    status.HTTP_409_CONFLICT,
                    {"material_id": material.id, "reason": reason},
                )
        return [materials[item] for item in unique_ids]

    def mark_stale_for_material(self, material_id: int, reason: str) -> list[int]:
        drafts = list(
            self.db.scalars(
                select(CourseArchitectureDraft)
                .join(
                    CourseArchitectureDraftMaterial,
                    CourseArchitectureDraftMaterial.draft_id == CourseArchitectureDraft.id,
                )
                .where(
                    CourseArchitectureDraftMaterial.material_id == material_id,
                    CourseArchitectureDraft.status.not_in(("published", "archived")),
                )
            )
        )
        for draft in drafts:
            draft.status = "review_required"
            draft.quality_status = "stale"
            draft.last_error_code = "draft_material_changed"
            draft.last_error_message = reason[:2000]
        self.db.flush()
        return [draft.id for draft in drafts]

    def material_snapshots_stale(self, draft_id: int) -> bool:
        rows = self.db.execute(
            select(CourseArchitectureDraftMaterial, Material)
            .join(Material, Material.id == CourseArchitectureDraftMaterial.material_id)
            .where(CourseArchitectureDraftMaterial.draft_id == draft_id)
        ).all()
        return not rows or any(self._snapshot_stale(snapshot, material) for snapshot, material in rows)

    def _editable(self, draft_id: int, version: int) -> CourseArchitectureDraft:
        draft = self._get(draft_id)
        if draft.status not in EDITABLE_STATUSES:
            raise AppError("draft_read_only", "当前状态的课程架构草案不可修改", status.HTTP_409_CONFLICT, {"status": draft.status})
        if draft.version != version:
            raise AppError("draft_version_conflict", "草案已被更新，请刷新后重试", status.HTTP_409_CONFLICT, {"expected": draft.version, "received": version})
        return draft

    def _get(self, draft_id: int) -> CourseArchitectureDraft:
        draft = self.db.get(CourseArchitectureDraft, draft_id)
        if draft is None:
            raise not_found("课程架构草案", draft_id)
        return draft

    def _draft_course(self, draft_id: int, course_id: int) -> CourseArchitectureDraftCourse:
        course = self.db.scalar(
            select(CourseArchitectureDraftCourse).where(
                CourseArchitectureDraftCourse.id == course_id,
                CourseArchitectureDraftCourse.draft_id == draft_id,
            )
        )
        if course is None:
            raise not_found("草案课程", course_id)
        return course

    def _draft_point(self, draft_id: int, point_id: int) -> CourseArchitectureDraftKnowledgePoint:
        point = self.db.scalar(
            select(CourseArchitectureDraftKnowledgePoint)
            .join(
                CourseArchitectureDraftCourse,
                CourseArchitectureDraftCourse.id == CourseArchitectureDraftKnowledgePoint.draft_course_id,
            )
            .where(
                CourseArchitectureDraftKnowledgePoint.id == point_id,
                CourseArchitectureDraftCourse.draft_id == draft_id,
            )
        )
        if point is None:
            raise not_found("草案知识点", point_id)
        return point

    def _replace_material_rows(self, draft: CourseArchitectureDraft, materials: Sequence[Material]) -> None:
        for index, material in enumerate(materials):
            self.db.add(
                CourseArchitectureDraftMaterial(
                    draft_id=draft.id,
                    material_id=material.id,
                    order_index=index,
                    material_updated_at_snapshot=material.updated_at,
                    chunk_count_snapshot=material.chunk_count,
                    index_state_snapshot=material.indexing_status,
                )
            )

    def _ensure_unique_point_title(self, course_id: int, title: str, exclude_id: int | None = None) -> None:
        normalized = normalize_title(title)
        points = list(
            self.db.scalars(
                select(CourseArchitectureDraftKnowledgePoint).where(
                    CourseArchitectureDraftKnowledgePoint.draft_course_id == course_id
                )
            )
        )
        if any(point.id != exclude_id and normalize_title(point.title) == normalized for point in points):
            raise AppError("draft_knowledge_point_duplicate", "同一草案课程内已存在同名知识点", status.HTTP_409_CONFLICT)

    def _apply_order(self, rows, items, label: str, *, require_exact: bool = False) -> None:
        row_by_id = {row.id: row for row in rows}
        item_ids = {item.id for item in items}
        if len(item_ids) != len(items) or not item_ids.issubset(row_by_id):
            raise AppError("draft_reorder_invalid", f"{label}排序包含重复或无效项目", status.HTTP_422_UNPROCESSABLE_ENTITY)
        if require_exact and item_ids != set(row_by_id):
            # Knowledge point reorder endpoints may intentionally submit one course only.
            course_ids = {row_by_id[item.id].draft_course_id for item in items}
            expected = {row.id for row in rows if row.draft_course_id in course_ids}
            if item_ids != expected:
                raise AppError("draft_reorder_incomplete", f"{label}排序必须包含当前课程的全部项目", status.HTTP_422_UNPROCESSABLE_ENTITY)
        for item in items:
            row_by_id[item.id].order_index = item.order_index

    def _edge_pairs(self, draft_id: int) -> list[tuple[int, int]]:
        return list(
            self.db.execute(
                select(
                    CourseArchitectureDraftPrerequisite.prerequisite_knowledge_point_id,
                    CourseArchitectureDraftPrerequisite.dependent_knowledge_point_id,
                ).where(CourseArchitectureDraftPrerequisite.draft_id == draft_id)
            ).tuples()
        )

    def _delete_cross_course_edges(self, draft_id: int) -> None:
        edges = list(
            self.db.scalars(
                select(CourseArchitectureDraftPrerequisite).where(
                    CourseArchitectureDraftPrerequisite.draft_id == draft_id
                )
            )
        )
        course_by_point = {
            point.id: point.draft_course_id
            for point in self.db.scalars(
                select(CourseArchitectureDraftKnowledgePoint)
                .join(CourseArchitectureDraftCourse)
                .where(CourseArchitectureDraftCourse.draft_id == draft_id)
            )
        }
        for edge in edges:
            if course_by_point.get(edge.prerequisite_knowledge_point_id) != course_by_point.get(edge.dependent_knowledge_point_id):
                self.db.delete(edge)

    def _merge_edges(self, draft_id: int, keep_id: int, merge_ids: set[int]) -> None:
        edges = list(
            self.db.scalars(
                select(CourseArchitectureDraftPrerequisite).where(
                    CourseArchitectureDraftPrerequisite.draft_id == draft_id
                )
            )
        )
        desired: dict[tuple[int, int], CourseArchitectureDraftPrerequisite] = {}
        for edge in edges:
            source = keep_id if edge.prerequisite_knowledge_point_id in merge_ids else edge.prerequisite_knowledge_point_id
            target = keep_id if edge.dependent_knowledge_point_id in merge_ids else edge.dependent_knowledge_point_id
            if source == target or (source, target) in desired:
                self.db.delete(edge)
                continue
            edge.prerequisite_knowledge_point_id = source
            edge.dependent_knowledge_point_id = target
            desired[(source, target)] = edge
        if has_cycle(desired):
            raise AppError("draft_merge_creates_cycle", "合并知识点会形成循环前置关系", status.HTTP_409_CONFLICT)

    def _bump(self, draft: CourseArchitectureDraft) -> None:
        draft.version += 1
        draft.quality_status = "not_checked"
        if draft.status == "ready":
            draft.status = "review_required"

    @staticmethod
    def _timestamps(row) -> dict:
        return {"id": row.id, "created_at": row.created_at, "updated_at": row.updated_at}

    @staticmethod
    def _snapshot_stale(snapshot: CourseArchitectureDraftMaterial, material: Material) -> bool:
        return (
            str(snapshot.material_updated_at_snapshot) != str(material.updated_at)
            or snapshot.chunk_count_snapshot != material.chunk_count
            or snapshot.index_state_snapshot != material.indexing_status
            or material.indexing_status != "completed"
            or material.ingestion_status != "completed"
            or material.deletion_status != "active"
            or material.archived_at is not None
        )

    def _material_read(self, snapshot: CourseArchitectureDraftMaterial, material: Material) -> DraftMaterialRead:
        return DraftMaterialRead(
            **self._timestamps(snapshot),
            draft_id=snapshot.draft_id,
            material_id=material.id,
            material_title=material.title,
            original_filename=material.original_filename,
            order_index=snapshot.order_index,
            material_updated_at_snapshot=snapshot.material_updated_at_snapshot,
            chunk_count_snapshot=snapshot.chunk_count_snapshot,
            index_state_snapshot=snapshot.index_state_snapshot,
            current_chunk_count=material.chunk_count,
            current_indexing_status=material.indexing_status,
            stale=self._snapshot_stale(snapshot, material),
        )

    @staticmethod
    def _locator(chunk: MaterialChunk) -> str:
        if chunk.page_number is not None:
            return f"第 {chunk.page_number} 页 · 片段 {chunk.chunk_index + 1}"
        if chunk.section_title:
            return f"{chunk.section_title} · 片段 {chunk.chunk_index + 1}"
        return f"片段 {chunk.chunk_index + 1}"

    def _source_read(
        self, source: CourseArchitectureDraftSource, material: Material, chunk: MaterialChunk
    ) -> DraftSourceRead:
        return DraftSourceRead(
            **self._timestamps(source),
            draft_knowledge_point_id=source.draft_knowledge_point_id,
            material_id=material.id,
            material_title=material.title,
            material_chunk_id=chunk.id,
            chunk_index=chunk.chunk_index,
            source_locator=source.source_locator,
            quoted_text=source.quoted_text,
            source_role=source.source_role,
            relevance_score=source.relevance_score,
            origin=source.origin,
            context_url=f"/materials/{material.id}?chunk={chunk.id}",
        )
