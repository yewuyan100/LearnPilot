import json
from hashlib import sha256
from uuid import uuid4

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.learning.agents.lesson.prompts import LESSON_PROMPT_VERSION
from app.learning.agents.lesson.schemas import (
    LessonGenerationKnowledgePoint,
    LessonGenerationMaterialScope,
    LessonGenerationPrerequisite,
    LessonGenerationRequest,
)
from app.learning.context.schemas import MaterialReferenceContext, MaterialScopeContext
from app.learning.lessons.schemas import (
    LessonArchiveRequest,
    LessonCreate,
    LessonGenerateRequest,
    LessonKnowledgePointRead,
    LessonPublishRequest,
    LessonRead,
    LessonSourceRead,
    LessonVersionRead,
)
from app.learning.lessons.validation import (
    validate_generated_lesson,
    validate_published_source_scope,
)
from app.models.course import Course
from app.models.course_architecture import KnowledgePointPrerequisite
from app.models.knowledge_mastery import KnowledgeMastery
from app.models.knowledge_point import KnowledgePoint
from app.models.learning_goal import LearningGoal
from app.models.lesson import (
    Lesson,
    LessonSource,
    LessonVersion,
    LessonVersionKnowledgePoint,
)
from app.models.material import Material
from app.services.material_learning import MaterialScopeResolver


class LessonModule:
    """Deep Lesson Domain Module for lifecycle, generation, publication, and reading."""

    def __init__(self, db, agent, clock):
        self.db = db
        self.agent = agent
        self.clock = clock

    def _lesson(self, lesson_id: int) -> Lesson:
        lesson = self.db.get(Lesson, lesson_id)
        if lesson is None:
            raise AppError("lesson_not_found", "课节不存在。", status.HTTP_404_NOT_FOUND)
        return lesson

    def _version(self, lesson: Lesson, version_number: int) -> LessonVersion:
        version = self.db.scalar(
            select(LessonVersion).where(
                LessonVersion.lesson_id == lesson.id,
                LessonVersion.version_number == version_number,
            )
        )
        if version is None:
            raise AppError(
                "lesson_version_not_found",
                "课节版本不存在。",
                status.HTTP_404_NOT_FOUND,
            )
        return version

    def create(self, course_id: int, payload: LessonCreate) -> LessonRead:
        course = self.db.get(Course, course_id)
        if course is None:
            raise AppError("course_not_found", "课程不存在。", status.HTTP_404_NOT_FOUND)
        if course.status != "active":
            raise AppError(
                "lesson_course_inactive",
                "只能为有效课程创建课节。",
                status.HTTP_409_CONFLICT,
            )
        order_index = payload.order_index
        if order_index is None:
            maximum = self.db.scalar(
                select(func.max(Lesson.order_index)).where(Lesson.course_id == course.id)
            )
            order_index = int(maximum or 0) + 1
        lesson = Lesson(
            public_id=str(uuid4()),
            course_id=course.id,
            title=payload.title.strip(),
            description=payload.description.strip(),
            order_index=order_index,
            status="draft",
            current_version_number=0,
        )
        self.db.add(lesson)
        try:
            self.db.commit()
            self.db.refresh(lesson)
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(
                "lesson_order_conflict",
                "该课程中的课节顺序已被占用。",
                status.HTTP_409_CONFLICT,
            ) from exc
        return self.serialize(lesson)

    def list_for_course(self, course_id: int) -> list[LessonRead]:
        if self.db.get(Course, course_id) is None:
            raise AppError("course_not_found", "课程不存在。", status.HTTP_404_NOT_FOUND)
        lessons = list(
            self.db.scalars(
                select(Lesson)
                .where(Lesson.course_id == course_id)
                .order_by(Lesson.order_index, Lesson.id)
            )
        )
        return [self.serialize(item) for item in lessons]

    def get(self, lesson_id: int) -> LessonRead:
        return self.serialize(self._lesson(lesson_id))

    def versions(self, lesson_id: int) -> list[LessonVersionRead]:
        lesson = self._lesson(lesson_id)
        versions = list(
            self.db.scalars(
                select(LessonVersion)
                .where(LessonVersion.lesson_id == lesson.id)
                .order_by(LessonVersion.version_number.desc())
            )
        )
        return [self._serialize_version(item) for item in versions]

    def _points(
        self,
        lesson: Lesson,
        payload: LessonGenerateRequest,
    ) -> tuple[list[KnowledgePoint], int]:
        rows = list(
            self.db.scalars(
                select(KnowledgePoint).where(
                    KnowledgePoint.id.in_(payload.knowledge_point_ids)
                )
            )
        )
        by_id = {item.id: item for item in rows}
        if len(by_id) != len(payload.knowledge_point_ids):
            missing = sorted(set(payload.knowledge_point_ids).difference(by_id))
            raise AppError(
                "lesson_knowledge_point_not_found",
                "一个或多个知识点不存在。",
                status.HTTP_404_NOT_FOUND,
                {"knowledge_point_ids": missing},
            )
        ordered = [by_id[item_id] for item_id in payload.knowledge_point_ids]
        invalid = [
            item.id
            for item in ordered
            if item.course_id != lesson.course_id or item.lifecycle_status != "active"
        ]
        if invalid:
            raise AppError(
                "lesson_knowledge_point_scope_invalid",
                "课节只能覆盖同一课程内的有效知识点。",
                status.HTTP_409_CONFLICT,
                {"knowledge_point_ids": invalid},
            )
        return ordered, payload.primary_knowledge_point_id or ordered[0].id

    def _prerequisites(self, selected_ids: list[int]) -> list[KnowledgePoint]:
        rows = self.db.execute(
            select(KnowledgePointPrerequisite, KnowledgePoint)
            .join(
                KnowledgePoint,
                KnowledgePoint.id
                == KnowledgePointPrerequisite.prerequisite_knowledge_point_id,
            )
            .where(
                KnowledgePointPrerequisite.dependent_knowledge_point_id.in_(selected_ids),
                KnowledgePoint.lifecycle_status == "active",
            )
            .order_by(KnowledgePoint.order_index, KnowledgePoint.id)
        ).all()
        selected = set(selected_ids)
        result: dict[int, KnowledgePoint] = {}
        for _edge, point in rows:
            if point.id not in selected:
                result[point.id] = point
        return list(result.values())

    def _material_scope(
        self,
        course: Course,
        points: list[KnowledgePoint],
    ) -> MaterialScopeContext:
        resolver = MaterialScopeResolver(self.db)
        material_ids: set[int] = set()
        for point in points:
            resolution = resolver.resolve_combined_scope(
                learning_goal_id=course.learning_goal_id,
                course_id=course.id,
                knowledge_point_id=point.id,
                searchable_only=True,
            )
            material_ids.update(resolution.resolved_material_ids or [])
        ids = sorted(material_ids)
        materials = list(
            self.db.scalars(
                select(Material)
                .where(Material.id.in_(ids))
                .order_by(Material.updated_at.desc(), Material.id.desc())
            )
        ) if ids else []
        return MaterialScopeContext(
            requested_scope={
                "learning_goal_id": course.learning_goal_id,
                "course_id": course.id,
                "knowledge_point_ids": [item.id for item in points],
            },
            material_ids=ids,
            materials=[
                MaterialReferenceContext(
                    material_id=item.id,
                    title=item.title,
                    original_filename=item.original_filename,
                    source_type=item.source_type,
                )
                for item in materials
            ],
            scoped=True,
            empty=not ids,
        )

    def _generation_context(
        self,
        lesson: Lesson,
        points: list[KnowledgePoint],
        primary_id: int,
        prerequisites: list[KnowledgePoint],
        scope: MaterialScopeContext,
        target_minutes: int,
    ) -> LessonGenerationRequest:
        course = self.db.get(Course, lesson.course_id)
        assert course is not None
        goal = self.db.get(LearningGoal, course.learning_goal_id)
        assert goal is not None
        masteries = {
            item.knowledge_point_id: item.mastery_level
            for item in self.db.scalars(
                select(KnowledgeMastery).where(
                    KnowledgeMastery.knowledge_point_id.in_([point.id for point in points])
                )
            )
        }
        return LessonGenerationRequest(
            lesson_title=lesson.title,
            lesson_description=lesson.description,
            goal_title=goal.title,
            current_level=goal.current_level,
            course_title=course.title,
            knowledge_points=[
                LessonGenerationKnowledgePoint(
                    id=point.id,
                    title=point.title,
                    description=point.description,
                    role="primary" if point.id == primary_id else "supporting",
                    mastery_band=masteries.get(point.id, "unassessed"),
                )
                for point in points
            ],
            prerequisites=[
                LessonGenerationPrerequisite(id=point.id, title=point.title)
                for point in prerequisites
            ],
            material_scope=LessonGenerationMaterialScope.model_validate(
                scope.model_dump(mode="json")
            ),
            target_minutes=target_minutes,
        )

    @staticmethod
    def _content_markdown(draft) -> str:
        mistakes = "\n".join(f"- {item}" for item in draft.common_mistakes)
        return (
            "# 核心讲解\n\n"
            f"{draft.core_explanation_markdown.strip()}\n\n"
            "## 常见错误\n\n"
            f"{mistakes}"
        )

    @staticmethod
    def _snapshot(points, sources) -> str:
        raw = json.dumps(
            {
                "knowledge_points": [item.id for item in points],
                "sources": [
                    {
                        "chunk_id": item.chunk_id,
                        "material_id": item.material_id,
                        "content": item.content,
                    }
                    for item in sources
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(raw.encode("utf-8")).hexdigest()

    def generate(self, lesson_id: int, payload: LessonGenerateRequest) -> LessonRead:
        lesson = self._lesson(lesson_id)
        if lesson.status == "archived":
            raise AppError(
                "lesson_archived",
                "已归档课节不能生成新版本。",
                status.HTTP_409_CONFLICT,
            )
        replay = self.db.scalar(
            select(LessonVersion).where(
                LessonVersion.generation_request_id == payload.request_id
            )
        )
        if replay is not None:
            if replay.lesson_id != lesson.id:
                raise AppError(
                    "lesson_generation_request_conflict",
                    "相同 request_id 已用于另一课节。",
                    status.HTTP_409_CONFLICT,
                )
            return self.serialize(lesson, idempotent_replay=True)

        points, primary_id = self._points(lesson, payload)
        prerequisites = self._prerequisites([item.id for item in points])
        course = self.db.get(Course, lesson.course_id)
        assert course is not None
        scope = self._material_scope(course, points)
        request = self._generation_context(
            lesson,
            points,
            primary_id,
            prerequisites,
            scope,
            payload.target_minutes,
        )
        try:
            result = self.agent.generate(request)
            quality = validate_generated_lesson(
                result.draft,
                required_point_titles=[item.title for item in points],
                sources=result.sources,
                effective_material_ids=set(scope.material_ids),
            )
            cited = set(result.draft.cited_source_ids)
            selected_sources = [
                item for item in result.sources if item.source_label in cited
            ]
            version_number = lesson.current_version_number + 1
            version = LessonVersion(
                lesson_id=lesson.id,
                version_number=version_number,
                status=quality["status"],
                objectives=result.draft.objectives,
                content_markdown=self._content_markdown(result.draft),
                examples=[item.model_dump(mode="json") for item in result.draft.examples],
                guided_practice=[
                    item.model_dump(mode="json") for item in result.draft.guided_practice
                ],
                checks=[item.model_dump(mode="json") for item in result.draft.checks],
                estimated_minutes=result.draft.estimated_minutes,
                source_snapshot_hash=self._snapshot(points, selected_sources),
                generation_request_id=payload.request_id,
                model_name=result.model_name,
                prompt_version=LESSON_PROMPT_VERSION,
                quality_report=quality,
            )
            self.db.add(version)
            self.db.flush()
            order = 1
            for point in points:
                self.db.add(
                    LessonVersionKnowledgePoint(
                        lesson_version_id=version.id,
                        knowledge_point_id=point.id,
                        order_index=order,
                        role="primary" if point.id == primary_id else "supporting",
                    )
                )
                order += 1
            for point in prerequisites:
                self.db.add(
                    LessonVersionKnowledgePoint(
                        lesson_version_id=version.id,
                        knowledge_point_id=point.id,
                        order_index=order,
                        role="prerequisite_context",
                    )
                )
                order += 1
            for index, source in enumerate(selected_sources):
                location = f"chunk:{source.chunk_index}"
                if source.page_number is not None:
                    location += f";page:{source.page_number}"
                elif source.section_title:
                    location += f";section:{source.section_title}"
                self.db.add(
                    LessonSource(
                        lesson_version_id=version.id,
                        material_id=source.material_id,
                        material_chunk_id=source.chunk_id,
                        source_role="primary" if index == 0 else "supporting",
                        source_locator=location[:500],
                        quoted_text=source.content,
                    )
                )
            lesson.current_version_number = version_number
            if lesson.active_version_number is None:
                lesson.status = quality["status"]
            self.db.commit()
            self.db.refresh(lesson)
            return self.serialize(lesson)
        except AppError:
            self.db.rollback()
            raise
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(
                "lesson_generation_conflict",
                "课节版本生成发生并发冲突。",
                status.HTTP_409_CONFLICT,
            ) from exc

    def publish(
        self,
        lesson_id: int,
        version_number: int,
        payload: LessonPublishRequest,
    ) -> LessonRead:
        lesson = self._lesson(lesson_id)
        if payload.expected_version_number != lesson.current_version_number:
            raise AppError(
                "lesson_version_conflict",
                "课节已生成新版本，请刷新后重试。",
                status.HTTP_409_CONFLICT,
                {"current_version_number": lesson.current_version_number},
            )
        version = self._version(lesson, version_number)
        if (
            version.status == "published"
            and lesson.active_version_number == version.version_number
        ):
            return self.serialize(lesson, idempotent_replay=True)
        if version.status != "ready":
            raise AppError(
                "lesson_version_not_ready",
                "只有通过质量检查的 ready 版本可以发布。",
                status.HTTP_409_CONFLICT,
            )
        relations = list(
            self.db.scalars(
                select(LessonVersionKnowledgePoint).where(
                    LessonVersionKnowledgePoint.lesson_version_id == version.id,
                    LessonVersionKnowledgePoint.role.in_(("primary", "supporting")),
                )
            )
        )
        points = [
            self.db.get(KnowledgePoint, item.knowledge_point_id) for item in relations
        ]
        valid_points = [item for item in points if item is not None]
        course = self.db.get(Course, lesson.course_id)
        assert course is not None
        scope = self._material_scope(course, valid_points)
        validate_published_source_scope(self.db, version, set(scope.material_ids))

        if lesson.active_version_number is not None:
            previous = self._version(lesson, lesson.active_version_number)
            if previous.id != version.id:
                previous.status = "superseded"
        version.status = "published"
        version.published_at = self.clock.now()
        lesson.active_version_number = version.version_number
        lesson.status = "published"
        self.db.commit()
        self.db.refresh(lesson)
        return self.serialize(lesson)

    def archive(self, lesson_id: int, payload: LessonArchiveRequest) -> LessonRead:
        lesson = self._lesson(lesson_id)
        if lesson.status == "archived":
            return self.serialize(lesson, idempotent_replay=True)
        lesson.status = "archived"
        self.db.commit()
        self.db.refresh(lesson)
        return self.serialize(lesson)

    def _serialize_version(self, version: LessonVersion) -> LessonVersionRead:
        point_rows = self.db.execute(
            select(LessonVersionKnowledgePoint, KnowledgePoint)
            .join(
                KnowledgePoint,
                KnowledgePoint.id == LessonVersionKnowledgePoint.knowledge_point_id,
            )
            .where(LessonVersionKnowledgePoint.lesson_version_id == version.id)
            .order_by(LessonVersionKnowledgePoint.order_index)
        ).all()
        source_rows = self.db.execute(
            select(LessonSource, Material)
            .join(Material, Material.id == LessonSource.material_id)
            .where(LessonSource.lesson_version_id == version.id)
            .order_by(LessonSource.source_role, LessonSource.source_locator)
        ).all()
        return LessonVersionRead(
            id=version.id,
            lesson_id=version.lesson_id,
            version_number=version.version_number,
            status=version.status,
            objectives=version.objectives,
            content_markdown=version.content_markdown,
            examples=version.examples,
            guided_practice=version.guided_practice,
            checks=version.checks,
            estimated_minutes=version.estimated_minutes,
            source_snapshot_hash=version.source_snapshot_hash,
            generation_request_id=version.generation_request_id,
            model_name=version.model_name,
            prompt_version=version.prompt_version,
            quality_report=version.quality_report,
            published_at=version.published_at,
            created_at=version.created_at,
            updated_at=version.updated_at,
            knowledge_points=[
                LessonKnowledgePointRead(
                    knowledge_point_id=point.id,
                    title=point.title,
                    order_index=relation.order_index,
                    role=relation.role,
                )
                for relation, point in point_rows
            ],
            sources=[
                LessonSourceRead(
                    material_id=source.material_id,
                    material_title=material.title,
                    material_chunk_id=source.material_chunk_id,
                    source_role=source.source_role,
                    source_locator=source.source_locator,
                    quoted_text=source.quoted_text,
                )
                for source, material in source_rows
            ],
        )

    def serialize(
        self,
        lesson: Lesson,
        *,
        idempotent_replay: bool = False,
    ) -> LessonRead:
        course = self.db.get(Course, lesson.course_id)
        assert course is not None
        latest = (
            self._version(lesson, lesson.current_version_number)
            if lesson.current_version_number
            else None
        )
        active = (
            self._version(lesson, lesson.active_version_number)
            if lesson.active_version_number
            else None
        )
        return LessonRead(
            id=lesson.id,
            public_id=lesson.public_id,
            course_id=lesson.course_id,
            course_title=course.title,
            learning_goal_id=course.learning_goal_id,
            title=lesson.title,
            description=lesson.description,
            order_index=lesson.order_index,
            status=lesson.status,
            current_version_number=lesson.current_version_number,
            active_version_number=lesson.active_version_number,
            created_at=lesson.created_at,
            updated_at=lesson.updated_at,
            latest_version=self._serialize_version(latest) if latest else None,
            active_version=self._serialize_version(active) if active else None,
            idempotent_replay=idempotent_replay,
        )
