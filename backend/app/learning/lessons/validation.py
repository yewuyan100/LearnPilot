import re

from fastapi import status
from sqlalchemy import select

from app.core.errors import AppError
from app.learning.agents.lesson.schemas import GeneratedLessonDraft
from app.models.lesson import Lesson, LessonSource, LessonVersion, LessonVersionKnowledgePoint
from app.services.rag.types import RagSource


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def validate_generated_lesson(
    draft: GeneratedLessonDraft,
    *,
    required_point_titles: list[str],
    sources: list[RagSource],
    effective_material_ids: set[int],
) -> dict:
    issues: list[dict] = []
    body = _normalized("\n".join(draft.objectives) + "\n" + draft.core_explanation_markdown)
    for title in required_point_titles:
        if _normalized(title) not in body:
            issues.append(
                {
                    "code": "objective_knowledge_point_mismatch",
                    "severity": "blocker",
                    "message": f"教学目标或讲解未明确覆盖知识点：{title}",
                }
            )
    if not draft.core_explanation_markdown.strip():
        issues.append(
            {"code": "explanation_missing", "severity": "blocker", "message": "缺少核心讲解。"}
        )
    if not draft.examples:
        issues.append(
            {"code": "example_missing", "severity": "blocker", "message": "缺少教学示例。"}
        )
    if not draft.guided_practice:
        issues.append(
            {"code": "practice_missing", "severity": "blocker", "message": "缺少引导练习。"}
        )
    if not draft.checks:
        issues.append(
            {"code": "check_missing", "severity": "blocker", "message": "缺少理解检查。"}
        )

    allowed_labels = {source.source_label for source in sources}
    cited_labels = set(draft.cited_source_ids)
    if not cited_labels:
        issues.append(
            {"code": "citation_missing", "severity": "blocker", "message": "课节没有引用来源。"}
        )
    elif not cited_labels.issubset(allowed_labels):
        issues.append(
            {
                "code": "citation_invalid",
                "severity": "blocker",
                "message": "课节引用了检索结果之外的来源。",
            }
        )
    source_material_ids = {
        source.material_id for source in sources if source.source_label in cited_labels
    }
    if not source_material_ids.issubset(effective_material_ids):
        issues.append(
            {
                "code": "source_outside_effective_scope",
                "severity": "blocker",
                "message": "课节来源不属于有效资料范围。",
            }
        )
    blockers = [item for item in issues if item["severity"] == "blocker"]
    return {
        "valid": not blockers,
        "status": "ready" if not blockers else "review_required",
        "issues": issues,
        "required_knowledge_point_count": len(required_point_titles),
        "cited_source_count": len(cited_labels),
        "has_explanation": bool(draft.core_explanation_markdown.strip()),
        "has_example": bool(draft.examples),
        "has_practice": bool(draft.guided_practice),
        "has_check": bool(draft.checks),
    }


def validate_published_source_scope(
    db,
    version: LessonVersion,
    effective_material_ids: set[int],
) -> None:
    material_ids = set(
        db.scalars(
            select(LessonSource.material_id).where(
                LessonSource.lesson_version_id == version.id
            )
        )
    )
    if not material_ids or not material_ids.issubset(effective_material_ids):
        raise AppError(
            "lesson_source_scope_invalid",
            "课节来源已不属于当前有效资料范围，不能发布。",
            status.HTTP_409_CONFLICT,
        )


def resolve_session_lesson_version(
    db,
    *,
    course_id: int | None,
    knowledge_point_id: int | None,
    lesson_version_id: int | None,
) -> LessonVersion | None:
    if lesson_version_id is not None:
        version = db.get(LessonVersion, lesson_version_id)
        if version is None:
            raise AppError(
                "lesson_version_not_found",
                "课节版本不存在。",
                status.HTTP_404_NOT_FOUND,
            )
        lesson = db.get(Lesson, version.lesson_id)
        relation = db.scalar(
            select(LessonVersionKnowledgePoint).where(
                LessonVersionKnowledgePoint.lesson_version_id == version.id,
                LessonVersionKnowledgePoint.knowledge_point_id == knowledge_point_id,
                LessonVersionKnowledgePoint.role.in_(("primary", "supporting")),
            )
        )
        if (
            lesson is None
            or lesson.course_id != course_id
            or lesson.status != "published"
            or lesson.active_version_number != version.version_number
            or version.status != "published"
            or relation is None
        ):
            raise AppError(
                "lesson_session_context_mismatch",
                "课节版本与当前课程或知识点不一致。",
                status.HTTP_409_CONFLICT,
            )
        return version

    if course_id is None or knowledge_point_id is None:
        return None
    candidates = list(
        db.scalars(
            select(LessonVersion)
            .join(Lesson, Lesson.id == LessonVersion.lesson_id)
            .join(
                LessonVersionKnowledgePoint,
                LessonVersionKnowledgePoint.lesson_version_id == LessonVersion.id,
            )
            .where(
                Lesson.course_id == course_id,
                Lesson.status == "published",
                Lesson.active_version_number == LessonVersion.version_number,
                LessonVersion.status == "published",
                LessonVersionKnowledgePoint.knowledge_point_id == knowledge_point_id,
                LessonVersionKnowledgePoint.role.in_(("primary", "supporting")),
            )
            .order_by(Lesson.order_index, Lesson.id)
        )
    )
    if len(candidates) > 1:
        raise AppError(
            "lesson_version_required",
            "当前知识点对应多个已发布课节，请明确选择课节版本。",
            status.HTTP_409_CONFLICT,
        )
    return candidates[0] if candidates else None


def lesson_url_for_session(db, session) -> str:
    if session.lesson_version_id is None:
        return f"/learning-sessions/{session.id}"
    version = db.get(LessonVersion, session.lesson_version_id)
    return (
        f"/lessons/{version.lesson_id}?session={session.id}"
        if version is not None
        else f"/learning-sessions/{session.id}"
    )
