from __future__ import annotations

from datetime import timezone
import logging

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.models.course import Course
from app.models.course_architecture import (
    CourseArchitectureDraft,
    CourseArchitectureDraftCourse,
    CourseArchitectureDraftKnowledgePoint,
    CourseArchitectureDraftPrerequisite,
    CourseArchitectureDraftSource,
    KnowledgePointPrerequisite,
)
from app.models.knowledge_point import KnowledgePoint
from app.schemas.course_architecture import PublishResult
from app.schemas.knowledge_point_source import KnowledgePointSourceCreate
from app.schemas.material_learning import MaterialLearningLinkCreate
from app.services.course_architecture.drafts import CourseArchitectureDraftService
from app.services.course_architecture.validation import CourseArchitectureValidationService
from app.services.knowledge_point_sources import KnowledgePointSourceService
from app.services.material_learning import MaterialLearningLinkService


logger = logging.getLogger("personal_learning.course_architecture.publishing")


class CourseArchitecturePublishingService:
    """The sole deterministic boundary from a reviewed draft to formal learning data."""

    def __init__(self, db: Session, settings: Settings, clock: Clock) -> None:
        self.db = db
        self.settings = settings
        self.clock = clock
        self.drafts = CourseArchitectureDraftService(db, clock)

    def publish(
        self,
        draft_id: int,
        *,
        version: int,
        publish_request_id: str,
        confirmed: bool,
    ) -> PublishResult:
        draft = self.drafts._get(draft_id)
        if draft.status == "published":
            return self._result(draft)
        if not confirmed:
            raise AppError("draft_publish_confirmation_required", "发布课程架构前需要明确确认", status.HTTP_422_UNPROCESSABLE_ENTITY)
        if draft.version != version:
            raise AppError("draft_version_conflict", "草案已被更新，请刷新后重试", status.HTTP_409_CONFLICT, {"expected": draft.version, "received": version})
        if draft.status != "ready":
            raise AppError("draft_not_ready", "只有通过质量检查的草案才能发布", status.HTTP_409_CONFLICT, {"status": draft.status})
        used_request = self.db.scalar(
            select(CourseArchitectureDraft).where(
                CourseArchitectureDraft.publish_request_id == publish_request_id,
                CourseArchitectureDraft.id != draft.id,
            )
        )
        if used_request is not None:
            raise AppError("publish_request_conflict", "该发布请求已用于其他草案", status.HTTP_409_CONFLICT)
        try:
            report = CourseArchitectureValidationService(self.db, self.settings).validate_draft(
                draft.id, version=version, commit=False, bump_version=False
            )
            if report.blocker_count:
                raise AppError("draft_quality_blocked", "草案仍有阻塞问题，不能发布", status.HTTP_409_CONFLICT, report.model_dump(mode="json"))
            draft.status = "publishing"
            draft.publish_request_id = publish_request_id
            self.db.flush()
            draft_courses = list(
                self.db.scalars(
                    select(CourseArchitectureDraftCourse)
                    .where(CourseArchitectureDraftCourse.draft_id == draft.id)
                    .order_by(CourseArchitectureDraftCourse.order_index, CourseArchitectureDraftCourse.id)
                )
            )
            draft_points = list(
                self.db.scalars(
                    select(CourseArchitectureDraftKnowledgePoint)
                    .join(CourseArchitectureDraftCourse)
                    .where(CourseArchitectureDraftCourse.draft_id == draft.id)
                    .order_by(
                        CourseArchitectureDraftKnowledgePoint.draft_course_id,
                        CourseArchitectureDraftKnowledgePoint.order_index,
                        CourseArchitectureDraftKnowledgePoint.id,
                    )
                )
            )
            points_by_course: dict[int, list[CourseArchitectureDraftKnowledgePoint]] = {
                course.id: [] for course in draft_courses
            }
            for point in draft_points:
                points_by_course[point.draft_course_id].append(point)
            course_map: dict[int, Course] = {}
            point_map: dict[int, KnowledgePoint] = {}
            for draft_course in draft_courses:
                course = Course(
                    learning_goal_id=draft.learning_goal_id,
                    title=draft_course.title,
                    description=draft_course.description,
                    status="active",
                )
                self.db.add(course)
                self.db.flush()
                draft_course.published_course_id = course.id
                course_map[draft_course.id] = course
                for order_index, draft_point in enumerate(points_by_course[draft_course.id]):
                    point = KnowledgePoint(
                        course_id=course.id,
                        title=draft_point.title,
                        description=draft_point.description,
                        order_index=order_index,
                        estimated_minutes=20,
                        status="not_started",
                    )
                    self.db.add(point)
                    self.db.flush()
                    draft_point.published_knowledge_point_id = point.id
                    point_map[draft_point.id] = point

            source_rows = list(
                self.db.scalars(
                    select(CourseArchitectureDraftSource).where(
                        CourseArchitectureDraftSource.draft_knowledge_point_id.in_(point_map)
                    )
                )
            )
            source_by_point: dict[int, list[CourseArchitectureDraftSource]] = {
                point_id: [] for point_id in point_map
            }
            for source in source_rows:
                source_by_point[source.draft_knowledge_point_id].append(source)

            link_service = MaterialLearningLinkService(self.db)
            source_service = KnowledgePointSourceService(self.db)
            material_link_count = 0
            for draft_course, course in course_map.items():
                course_sources = [
                    source
                    for draft_point in points_by_course[draft_course]
                    for source in source_by_point[draft_point.id]
                ]
                by_material: dict[int, list[CourseArchitectureDraftSource]] = {}
                for source in course_sources:
                    by_material.setdefault(source.material_id, []).append(source)
                for material_id, material_sources in by_material.items():
                    is_primary = any(source.source_role == "primary" for source in material_sources)
                    link_service.create_link(
                        material_id,
                        MaterialLearningLinkCreate(
                            target_type="course",
                            course_id=course.id,
                            relation_type="primary_source" if is_primary else "reference",
                            is_primary=is_primary,
                        ),
                        commit=False,
                    )
                    material_link_count += 1
            for draft_point_id, formal_point in point_map.items():
                for source in source_by_point[draft_point_id]:
                    source_service.create(
                        formal_point.id,
                        KnowledgePointSourceCreate(
                            material_id=source.material_id,
                            material_chunk_id=source.material_chunk_id,
                            source_type="chunk",
                            source_locator=source.source_locator,
                            quoted_text=source.quoted_text,
                            note="由课程架构草案发布",
                        ),
                        commit=False,
                    )

            edges = list(
                self.db.scalars(
                    select(CourseArchitectureDraftPrerequisite).where(
                        CourseArchitectureDraftPrerequisite.draft_id == draft.id
                    )
                )
            )
            for edge in edges:
                self.db.add(
                    KnowledgePointPrerequisite(
                        prerequisite_knowledge_point_id=point_map[edge.prerequisite_knowledge_point_id].id,
                        dependent_knowledge_point_id=point_map[edge.dependent_knowledge_point_id].id,
                        relation_type="prerequisite",
                        source="course_architecture",
                    )
                )
            draft.status = "published"
            draft.quality_status = "ready"
            draft.published_at = self.clock.now()
            draft.version += 1
            self.db.commit()
            result = self._result(draft)
            if result.material_link_count != material_link_count:
                logger.info(
                    "publish_material_link_count_adjusted draft_id=%s expected=%s actual=%s",
                    draft.id,
                    material_link_count,
                    result.material_link_count,
                )
            return result
        except AppError:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            failed = self.db.get(CourseArchitectureDraft, draft_id)
            if failed is not None and failed.status != "published":
                failed.status = "review_required"
                failed.last_error_code = "draft_publish_failed"
                failed.last_error_message = "发布失败，未创建任何正式课程，可修复后重试。"
                self.db.commit()
            logger.exception("course_architecture_publish_failed draft_id=%s", draft_id)
            raise AppError("draft_publish_failed", "发布失败，未留下半套课程", status.HTTP_500_INTERNAL_SERVER_ERROR) from exc

    def _result(self, draft: CourseArchitectureDraft) -> PublishResult:
        courses = list(
            self.db.scalars(
                select(CourseArchitectureDraftCourse)
                .where(CourseArchitectureDraftCourse.draft_id == draft.id)
                .order_by(CourseArchitectureDraftCourse.order_index)
            )
        )
        points = list(
            self.db.scalars(
                select(CourseArchitectureDraftKnowledgePoint)
                .join(CourseArchitectureDraftCourse)
                .where(CourseArchitectureDraftCourse.draft_id == draft.id)
                .order_by(CourseArchitectureDraftKnowledgePoint.id)
            )
        )
        course_ids = [course.published_course_id for course in courses if course.published_course_id]
        point_ids = [point.published_knowledge_point_id for point in points if point.published_knowledge_point_id]
        sources = self.db.scalar(
            select(func.count(CourseArchitectureDraftSource.id))
            .join(CourseArchitectureDraftKnowledgePoint)
            .join(CourseArchitectureDraftCourse)
            .where(CourseArchitectureDraftCourse.draft_id == draft.id)
        ) or 0
        prerequisites = self.db.scalar(
            select(func.count(CourseArchitectureDraftPrerequisite.id)).where(
                CourseArchitectureDraftPrerequisite.draft_id == draft.id
            )
        ) or 0
        distinct_links = self.db.scalar(
            select(func.count()).select_from(
                select(
                    CourseArchitectureDraftCourse.id,
                    CourseArchitectureDraftSource.material_id,
                )
                .join(
                    CourseArchitectureDraftKnowledgePoint,
                    CourseArchitectureDraftKnowledgePoint.draft_course_id
                    == CourseArchitectureDraftCourse.id,
                )
                .join(
                    CourseArchitectureDraftSource,
                    CourseArchitectureDraftSource.draft_knowledge_point_id
                    == CourseArchitectureDraftKnowledgePoint.id,
                )
                .where(CourseArchitectureDraftCourse.draft_id == draft.id)
                .distinct()
                .subquery()
            )
        ) or 0
        if draft.published_at is None or draft.publish_request_id is None:
            raise AppError("draft_publish_result_incomplete", "已发布草案缺少发布结果", status.HTTP_500_INTERNAL_SERVER_ERROR)
        published_at = draft.published_at
        if published_at.tzinfo is None:
            # SQLite stores the UTC instant without an offset. Restore the API contract
            # so an idempotent replay serializes exactly like the first response.
            published_at = published_at.replace(tzinfo=timezone.utc)
        return PublishResult(
            draft_id=draft.id,
            publish_request_id=draft.publish_request_id,
            course_ids=course_ids,
            knowledge_point_ids=point_ids,
            material_link_count=distinct_links,
            source_count=sources,
            prerequisite_count=prerequisites,
            published_at=published_at,
        )
