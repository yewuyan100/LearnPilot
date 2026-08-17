from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models.course import Course
from app.models.course_architecture import (
    CourseArchitectureDraft,
    CourseArchitectureDraftCourse,
    CourseArchitectureDraftKnowledgePoint,
    CourseArchitectureDraftPrerequisite,
    CourseArchitectureDraftSource,
)
from app.models.knowledge_point import KnowledgePoint
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.schemas.course_architecture import CourseArchitectureQualityReport, QualityIssue
from app.services.course_architecture.drafts import CourseArchitectureDraftService
from app.services.course_architecture.graph import has_cycle, normalize_title


class CourseArchitectureValidationService:
    """Compute the publish gate from database facts, never from model judgement."""

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def build_report(self, draft_id: int) -> CourseArchitectureQualityReport:
        draft = self.db.get(CourseArchitectureDraft, draft_id)
        if draft is None:
            from app.core.errors import not_found
            raise not_found("课程架构草案", draft_id)
        courses = list(
            self.db.scalars(
                select(CourseArchitectureDraftCourse).where(
                    CourseArchitectureDraftCourse.draft_id == draft.id
                )
            )
        )
        points = list(
            self.db.scalars(
                select(CourseArchitectureDraftKnowledgePoint)
                .join(CourseArchitectureDraftCourse)
                .where(CourseArchitectureDraftCourse.draft_id == draft.id)
            )
        )
        point_ids = [point.id for point in points]
        sources = list(
            self.db.scalars(
                select(CourseArchitectureDraftSource).where(
                    CourseArchitectureDraftSource.draft_knowledge_point_id.in_(point_ids)
                )
            )
        ) if point_ids else []
        edges = list(
            self.db.scalars(
                select(CourseArchitectureDraftPrerequisite).where(
                    CourseArchitectureDraftPrerequisite.draft_id == draft.id
                )
            )
        )
        issues: list[QualityIssue] = []
        goal_only = draft.generation_mode == "curriculum_goal_only"
        stale = (
            False
            if goal_only
            else CourseArchitectureDraftService(
                self.db, _UnusedClock()
            ).material_snapshots_stale(draft.id)
        )
        if stale:
            issues.append(self._issue("materials_stale", "blocker", "所选资料已发生变化，请重新分析或重新验证。"))
        if goal_only:
            issues.append(
                self._issue(
                    "goal_only_unverified",
                    "warning",
                    "该学习路径未使用资料验证；发布前请人工审查范围与知识点拆分。",
                )
            )
        if not courses:
            issues.append(self._issue("no_courses", "blocker", "草案还没有课程。"))
        points_by_course: dict[int, list[CourseArchitectureDraftKnowledgePoint]] = {
            course.id: [] for course in courses
        }
        for point in points:
            points_by_course.setdefault(point.draft_course_id, []).append(point)
        for course in courses:
            if not course.title.strip():
                issues.append(self._issue("course_title_empty", "blocker", "课程名称不能为空。", course_id=course.id))
            if not points_by_course.get(course.id):
                issues.append(self._issue("course_without_points", "blocker", "课程至少需要一个知识点。", course_id=course.id))
        course_titles = Counter(normalize_title(course.title) for course in courses if course.title.strip())
        for course in courses:
            if course_titles[normalize_title(course.title)] > 1:
                issues.append(self._issue("duplicate_course", "blocker", "草案中存在重复课程名称。", course_id=course.id))
        source_count = Counter(source.draft_knowledge_point_id for source in sources)
        for point in points:
            if not point.title.strip():
                issues.append(self._issue("knowledge_point_title_empty", "blocker", "知识点名称不能为空。", knowledge_point_id=point.id))
            if source_count[point.id] == 0:
                issues.append(
                    self._issue(
                        "knowledge_point_unverified" if goal_only else "knowledge_point_without_source",
                        "warning" if goal_only else "blocker",
                        "知识点尚未经过真实资料验证。" if goal_only else "知识点尚未关联真实资料片段。",
                        knowledge_point_id=point.id,
                    )
                )
        for course_id, course_points in points_by_course.items():
            titles = Counter(normalize_title(point.title) for point in course_points if point.title.strip())
            for point in course_points:
                if titles[normalize_title(point.title)] > 1:
                    issues.append(self._issue("duplicate_knowledge_point", "blocker", "同一课程中存在重复知识点。", course_id=course_id, knowledge_point_id=point.id))
        allowed_material_ids = {
            item.material_id for item in CourseArchitectureDraftService(self.db, _UnusedClock()).get_draft(draft.id).materials
        }
        chunks = {
            chunk.id: chunk
            for chunk in self.db.scalars(
                select(MaterialChunk).where(MaterialChunk.id.in_([source.material_chunk_id for source in sources]))
            )
        } if sources else {}
        materials = {
            material.id: material
            for material in self.db.scalars(select(Material).where(Material.id.in_(allowed_material_ids)))
        } if allowed_material_ids else {}
        for source in sources:
            chunk = chunks.get(source.material_chunk_id)
            material = materials.get(source.material_id)
            if source.material_id not in allowed_material_ids or material is None:
                issues.append(self._issue("source_material_invalid", "blocker", "来源资料不在草案有效范围内。", knowledge_point_id=source.draft_knowledge_point_id))
            elif chunk is None or chunk.material_id != source.material_id:
                issues.append(self._issue("source_chunk_invalid", "blocker", "来源片段已失效或不属于对应资料。", knowledge_point_id=source.draft_knowledge_point_id))
        course_by_point = {point.id: point.draft_course_id for point in points}
        edge_pairs: list[tuple[int, int]] = []
        connected: set[int] = set()
        for edge in edges:
            source_course = course_by_point.get(edge.prerequisite_knowledge_point_id)
            target_course = course_by_point.get(edge.dependent_knowledge_point_id)
            if source_course is None or target_course is None:
                issues.append(self._issue("prerequisite_outside_draft", "blocker", "前置关系引用了无效知识点。"))
                continue
            if edge.prerequisite_knowledge_point_id == edge.dependent_knowledge_point_id:
                issues.append(self._issue("prerequisite_self", "blocker", "前置关系不能指向自身。", knowledge_point_id=edge.dependent_knowledge_point_id))
            if source_course != target_course:
                issues.append(self._issue("prerequisite_cross_course", "blocker", "V9 前置关系只能位于同一课程。", knowledge_point_id=edge.dependent_knowledge_point_id))
            edge_pairs.append((edge.prerequisite_knowledge_point_id, edge.dependent_knowledge_point_id))
            connected.update(edge_pairs[-1])
        if has_cycle(edge_pairs):
            issues.append(self._issue("prerequisite_cycle", "blocker", "前置关系中存在循环。"))
        for point in points:
            if len(points_by_course.get(point.draft_course_id, [])) > 1 and point.id not in connected:
                issues.append(self._issue("isolated_knowledge_point", "info", "该知识点暂未参与前置关系。", knowledge_point_id=point.id))
        formal_course_titles = {
            normalize_title(item.title)
            for item in self.db.scalars(select(Course).where(Course.learning_goal_id == draft.learning_goal_id))
        }
        for course in courses:
            if normalize_title(course.title) in formal_course_titles and course.published_course_id is None:
                issues.append(self._issue("formal_course_name_conflict", "blocker", "该学习目标下已存在同名正式课程。", course_id=course.id))
        formal_point_titles = {
            normalize_title(title)
            for title in self.db.scalars(
                select(KnowledgePoint.title)
                .join(Course)
                .where(Course.learning_goal_id == draft.learning_goal_id)
            )
        }
        for point in points:
            if normalize_title(point.title) in formal_point_titles and point.published_knowledge_point_id is None:
                issues.append(self._issue("formal_knowledge_point_name_conflict", "blocker", "该学习目标下已存在同名正式知识点。", knowledge_point_id=point.id))
        if len(courses) > self.settings.course_architecture_max_generated_courses:
            issues.append(self._issue("course_limit_exceeded", "blocker", "草案课程数量超过配置上限。"))
        if len(points) > self.settings.course_architecture_max_total_knowledge_points:
            issues.append(self._issue("knowledge_point_limit_exceeded", "blocker", "草案知识点数量超过配置上限。"))
        blocker_count = sum(issue.severity == "blocker" for issue in issues)
        warning_count = sum(issue.severity == "warning" for issue in issues)
        info_count = sum(issue.severity == "info" for issue in issues)
        status_value = "stale" if stale else "blocked" if blocker_count else "ready"
        return CourseArchitectureQualityReport(
            status=status_value,
            blocker_count=blocker_count,
            warning_count=warning_count,
            info_count=info_count,
            source_coverage=round((sum(source_count[point.id] > 0 for point in points) / len(points) * 100), 1) if points else 0,
            issues=issues,
        )

    def validate_draft(
        self,
        draft_id: int,
        *,
        version: int | None = None,
        commit: bool = True,
        bump_version: bool = True,
    ) -> CourseArchitectureQualityReport:
        draft = self.db.get(CourseArchitectureDraft, draft_id)
        if draft is None:
            from app.core.errors import not_found
            raise not_found("课程架构草案", draft_id)
        if version is not None and draft.version != version:
            raise AppError("draft_version_conflict", "草案已被更新，请刷新后重试", 409, {"expected": draft.version, "received": version})
        report = self.build_report(draft.id)
        draft.quality_report = report.model_dump(mode="json")
        draft.quality_status = report.status
        if draft.status not in {"published", "archived", "publishing"}:
            draft.status = "ready" if report.status == "ready" else "review_required"
        if bump_version:
            draft.version += 1
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return report

    @staticmethod
    def _issue(code: str, severity: str, message: str, **locations) -> QualityIssue:
        return QualityIssue(code=code, severity=severity, message=message, **locations)


class _UnusedClock:
    def now(self):  # pragma: no cover - draft inspection does not use the clock
        raise RuntimeError("clock is not used")

    def today(self):  # pragma: no cover
        raise RuntimeError("clock is not used")
