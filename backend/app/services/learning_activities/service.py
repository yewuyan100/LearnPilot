from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from hashlib import sha256
from math import ceil
from threading import Lock

from fastapi import status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models.activity_question import ActivityQuestion
from app.models.course import Course
from app.models.knowledge_point import KnowledgePoint
from app.models.learning_activity import LearningActivity
from app.models.question_source import QuestionSource
from app.models.quiz_attempt import QuizAttempt
from app.schemas.learning_activity import (
    ActivityDetail,
    ActivityGenerateRequest,
    ActivityListItem,
    ActivityQuestionAdminRead,
    ActivityUpdate,
    GeneratedActivity,
    GeneratedQuestion,
    QuestionOption,
    QuestionReorderRequest,
    QuestionSourceRead,
    RubricItem,
)
from app.services.embedding.base import Embedder
from app.services.learning_activities.generator import generate_activity
from app.services.learning_activities.retrieval import retrieve_activity_sources
from app.services.learning_activities.validator import (
    content_hash,
    validate_generated_activity,
)
from app.services.llm.base import LLMProvider


logger = logging.getLogger("personal_learning.activities")
ACTIVITY_GENERATION_LOCK = Lock()


def _hash_payload(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


class ActivityGenerationService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        embedder: Embedder,
        provider: LLMProvider | None,
    ):
        self.db = db
        self.settings = settings
        self.embedder = embedder
        self.provider = provider

    def _get(self, activity_id: int) -> LearningActivity:
        activity = self.db.get(LearningActivity, activity_id)
        if activity is None:
            raise AppError(
                "activity_not_found",
                "学习活动不存在",
                status.HTTP_404_NOT_FOUND,
                {"id": activity_id},
            )
        return activity

    def _validate_scope(self, request: ActivityGenerateRequest) -> tuple[Course | None, KnowledgePoint | None]:
        if request.question_count > self.settings.activity_max_question_count:
            raise AppError(
                "activity_generation_invalid",
                f"题目数量不能超过 {self.settings.activity_max_question_count}",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        course = self.db.get(Course, request.course_id) if request.course_id else None
        if request.course_id and course is None:
            raise AppError("course_not_found", "课程不存在", status.HTTP_404_NOT_FOUND)
        point = (
            self.db.get(KnowledgePoint, request.knowledge_point_id)
            if request.knowledge_point_id
            else None
        )
        if request.knowledge_point_id and point is None:
            raise AppError(
                "knowledge_point_not_found", "知识点不存在", status.HTTP_404_NOT_FOUND
            )
        if course and point and point.course_id != course.id:
            raise AppError(
                "activity_generation_invalid",
                "知识点不属于所选课程",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return course, point

    def generate(self, request: ActivityGenerateRequest) -> ActivityDetail:
        with ACTIVITY_GENERATION_LOCK:
            return self._generate_locked(request)

    def _generate_locked(self, request: ActivityGenerateRequest) -> ActivityDetail:
        config = request.model_dump(mode="json", exclude={"request_id"})
        config_hash = _hash_payload(config)
        existing = self.db.scalar(
            select(LearningActivity).where(
                LearningActivity.generation_request_id == request.request_id
            )
        )
        if existing is not None:
            if existing.generation_config_hash != config_hash:
                raise AppError(
                    "activity_request_conflict",
                    "相同 request_id 已用于不同的活动配置",
                    status.HTTP_409_CONFLICT,
                )
            return self.detail(existing.id, include_secrets=True)
        course, point = self._validate_scope(request)
        query_parts = [
            point.title if point else "",
            point.description if point else "",
            course.title if course else "",
            request.title,
            request.description,
        ]
        query = " ".join(part.strip() for part in query_parts if part and part.strip())
        sources = retrieve_activity_sources(
            db=self.db,
            settings=self.settings,
            embedder=self.embedder,
            query=query,
            material_ids=request.material_ids,
        )
        if self.provider is None:
            raise AppError(
                "llm_not_configured",
                "已找到可靠资料，但 LLM 尚未配置，无法生成题目",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        generated = generate_activity(
            provider=self.provider,
            request=request,
            sources=sources,
            max_output_tokens=self.settings.activity_generation_max_output_tokens,
        )
        activity = LearningActivity(
            title=generated.activity.title.strip(),
            description=generated.activity.description.strip(),
            activity_type="quiz",
            status="draft",
            course_id=course.id if course else (point.course_id if point else None),
            knowledge_point_id=point.id if point else None,
            source_scope={
                "kind": "generated",
                "material_ids": request.material_ids,
                "difficulty": request.difficulty,
                "question_types": [item.value for item in request.question_types],
            },
            question_count=len(generated.activity.questions),
            total_points=round(sum(item.points for item in generated.activity.questions), 2),
            generation_request_id=request.request_id,
            generation_config_hash=config_hash,
            prompt_version=self.settings.activity_generation_prompt_version,
            model_name=generated.model_name,
            validation_warnings=generated.report.warnings,
        )
        source_map = {source.source_label: source for source in sources}
        try:
            self.db.add(activity)
            self.db.flush()
            for index, generated_question in enumerate(
                generated.activity.questions, start=1
            ):
                question = ActivityQuestion(
                    activity_id=activity.id,
                    question_index=index,
                    question_type=generated_question.question_type.value,
                    stem=generated_question.stem.strip(),
                    options_json=(
                        [item.model_dump() for item in generated_question.options]
                        if generated_question.options
                        else None
                    ),
                    correct_answer_json=generated_question.correct_answer,
                    reference_answer=generated_question.reference_answer,
                    grading_rubric_json=(
                        [item.model_dump() for item in generated_question.grading_rubric]
                        if generated_question.grading_rubric
                        else None
                    ),
                    explanation=generated_question.explanation.strip(),
                    difficulty=generated_question.difficulty.value,
                    points=round(generated_question.points, 2),
                    content_hash=content_hash(generated_question),
                )
                self.db.add(question)
                self.db.flush()
                for source_id in dict.fromkeys(generated_question.cited_source_ids):
                    source = source_map[source_id]
                    self.db.add(
                        QuestionSource(
                            question_id=question.id,
                            source_label=source.source_label,
                            material_id=source.material_id,
                            chunk_id=source.chunk_id,
                            rank=source.rank,
                            score=source.score,
                            original_filename=source.original_filename,
                            chunk_index=source.chunk_index,
                            page_number=source.page_number,
                            section_title=source.section_title,
                            content_excerpt=source.content[
                                : self.settings.question_source_excerpt_chars
                            ],
                        )
                    )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        logger.info(
            "activity_generation_completed request_id=%s activity_id=%s course_id=%s "
            "knowledge_point_id=%s material_count=%s selected_source_count=%s "
            "requested_question_count=%s generated_question_count=%s model_name=%s "
            "prompt_version=%s generation_repair_used=%s generation_latency_ms=%s",
            request.request_id,
            activity.id,
            activity.course_id,
            activity.knowledge_point_id,
            len(request.material_ids or []),
            len(sources),
            request.question_count,
            activity.question_count,
            generated.model_name,
            activity.prompt_version,
            generated.repair_used,
            generated.latency_ms,
        )
        return self.detail(activity.id, include_secrets=True)

    def list(
        self,
        *,
        page: int,
        page_size: int,
        status_filter: str | None,
        course_id: int | None,
        knowledge_point_id: int | None,
    ) -> dict:
        query = select(LearningActivity)
        if status_filter:
            query = query.where(LearningActivity.status == status_filter)
        if course_id:
            query = query.where(LearningActivity.course_id == course_id)
        if knowledge_point_id:
            query = query.where(
                LearningActivity.knowledge_point_id == knowledge_point_id
            )
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        activities = self.db.scalars(
            query.order_by(LearningActivity.created_at.desc(), LearningActivity.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return {
            "items": [self._serialize_list_item(item) for item in activities],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": ceil(total / page_size) if total else 0,
        }

    def _serialize_list_item(self, activity: LearningActivity) -> ActivityListItem:
        course_title = (
            self.db.scalar(select(Course.title).where(Course.id == activity.course_id))
            if activity.course_id
            else None
        )
        point_title = (
            self.db.scalar(
                select(KnowledgePoint.title).where(
                    KnowledgePoint.id == activity.knowledge_point_id
                )
            )
            if activity.knowledge_point_id
            else None
        )
        completed = self.db.scalar(
            select(func.count())
            .select_from(QuizAttempt)
            .where(
                QuizAttempt.activity_id == activity.id,
                QuizAttempt.status == "completed",
            )
        ) or 0
        return ActivityListItem.model_validate(
            {
                "id": activity.id,
                "title": activity.title,
                "description": activity.description,
                "activity_type": activity.activity_type,
                "status": activity.status,
                "course_id": activity.course_id,
                "knowledge_point_id": activity.knowledge_point_id,
                "question_count": activity.question_count,
                "total_points": activity.total_points,
                "created_at": activity.created_at,
                "updated_at": activity.updated_at,
                "published_at": activity.published_at,
                "course_title": course_title,
                "knowledge_point_title": point_title,
                "completed_attempt_count": completed,
            }
        )

    def _sources(self, question_id: int) -> list[QuestionSourceRead]:
        items = self.db.scalars(
            select(QuestionSource)
            .where(QuestionSource.question_id == question_id)
            .order_by(QuestionSource.rank)
        ).all()
        return [
            QuestionSourceRead.model_validate(
                {**source.__dict__, "source_available": source.chunk_id is not None}
            )
            for source in items
        ]

    def detail(self, activity_id: int, *, include_secrets: bool | None = None) -> ActivityDetail:
        activity = self._get(activity_id)
        if include_secrets is None:
            include_secrets = activity.status == "draft"
        questions = self.db.scalars(
            select(ActivityQuestion)
            .where(ActivityQuestion.activity_id == activity.id)
            .order_by(ActivityQuestion.question_index)
        ).all()
        serialized = []
        for question in questions:
            serialized.append(
                ActivityQuestionAdminRead.model_validate(
                    {
                        **question.__dict__,
                        "options": question.options_json,
                        "correct_answer": (
                            question.correct_answer_json if include_secrets else None
                        ),
                        "reference_answer": (
                            question.reference_answer if include_secrets else None
                        ),
                        "grading_rubric": (
                            question.grading_rubric_json if include_secrets else None
                        ),
                        "explanation": (
                            question.explanation if include_secrets else ""
                        ),
                        "sources": self._sources(question.id) if include_secrets else [],
                    }
                )
            )
        item = self._serialize_list_item(activity)
        return ActivityDetail.model_validate(
            {
                **item.model_dump(),
                "source_scope": activity.source_scope,
                "generation_request_id": activity.generation_request_id,
                "prompt_version": activity.prompt_version,
                "model_name": activity.model_name,
                "validation_warnings": activity.validation_warnings,
                "questions": serialized,
            }
        )

    def update(self, activity_id: int, payload: ActivityUpdate) -> ActivityDetail:
        activity = self._get(activity_id)
        values = payload.model_dump(exclude_unset=True)
        if values.get("status") == "archived":
            if activity.status not in {"published", "draft"}:
                raise AppError(
                    "activity_invalid_transition",
                    "当前活动状态不能归档",
                    status.HTTP_409_CONFLICT,
                )
            activity.status = "archived"
        else:
            if activity.status != "draft":
                raise AppError(
                    "activity_not_draft",
                    "只有草稿活动可以修改",
                    status.HTTP_409_CONFLICT,
                )
            for field in ("title", "description"):
                if field in values:
                    setattr(activity, field, values[field])
        self.db.commit()
        return self.detail(activity.id, include_secrets=activity.status == "draft")

    def delete_question(self, activity_id: int, question_id: int) -> ActivityDetail:
        activity = self._get(activity_id)
        if activity.status != "draft":
            raise AppError(
                "activity_not_draft", "只有草稿可以删除题目", status.HTTP_409_CONFLICT
            )
        question = self.db.get(ActivityQuestion, question_id)
        if question is None or question.activity_id != activity.id:
            raise AppError(
                "question_not_found", "题目不存在", status.HTTP_404_NOT_FOUND
            )
        self.db.delete(question)
        self.db.flush()
        self._renumber(activity)
        self.db.commit()
        return self.detail(activity.id, include_secrets=True)

    def reorder(
        self, activity_id: int, payload: QuestionReorderRequest
    ) -> ActivityDetail:
        activity = self._get(activity_id)
        if activity.status != "draft":
            raise AppError(
                "activity_not_draft", "只有草稿可以调整顺序", status.HTTP_409_CONFLICT
            )
        questions = self.db.scalars(
            select(ActivityQuestion).where(ActivityQuestion.activity_id == activity.id)
        ).all()
        by_id = {question.id: question for question in questions}
        if set(payload.question_ids) != set(by_id):
            raise AppError(
                "question_invalid",
                "必须提交该活动完整且不重复的题目 ID 集合",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        for index, question_id in enumerate(payload.question_ids, start=1):
            by_id[question_id].question_index = -index
        self.db.flush()
        for index, question_id in enumerate(payload.question_ids, start=1):
            by_id[question_id].question_index = index
        self.db.commit()
        return self.detail(activity.id, include_secrets=True)

    def _renumber(self, activity: LearningActivity) -> None:
        questions = self.db.scalars(
            select(ActivityQuestion)
            .where(ActivityQuestion.activity_id == activity.id)
            .order_by(ActivityQuestion.question_index)
        ).all()
        for index, question in enumerate(questions, start=1):
            question.question_index = -index
        self.db.flush()
        for index, question in enumerate(questions, start=1):
            question.question_index = index
        activity.question_count = len(questions)
        activity.total_points = round(sum(question.points for question in questions), 2)

    def publish(self, activity_id: int) -> ActivityDetail:
        activity = self._get(activity_id)
        if activity.status != "draft":
            raise AppError(
                "activity_not_draft",
                "只有草稿活动可以发布",
                status.HTTP_409_CONFLICT,
            )
        questions = self.db.scalars(
            select(ActivityQuestion)
            .where(ActivityQuestion.activity_id == activity.id)
            .order_by(ActivityQuestion.question_index)
        ).all()
        if not questions:
            raise AppError(
                "activity_generation_invalid",
                "活动至少需要一道题才能发布",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        generated_questions = []
        allowed_sources: set[str] = set()
        for question in questions:
            sources = self.db.scalars(
                select(QuestionSource).where(QuestionSource.question_id == question.id)
            ).all()
            source_ids = [source.source_label for source in sources]
            allowed_sources.update(source_ids)
            generated_questions.append(
                GeneratedQuestion.model_validate(
                    {
                        "question_type": question.question_type,
                        "stem": question.stem,
                        "options": question.options_json,
                        "correct_answer": question.correct_answer_json,
                        "reference_answer": question.reference_answer,
                        "grading_rubric": question.grading_rubric_json,
                        "explanation": question.explanation,
                        "difficulty": question.difficulty,
                        "points": question.points,
                        "cited_source_ids": source_ids,
                    }
                )
            )
        request = ActivityGenerateRequest.model_validate(
            {
                "title": activity.title,
                "description": activity.description,
                "course_id": activity.course_id,
                "knowledge_point_id": activity.knowledge_point_id,
                "material_ids": activity.source_scope.get("material_ids"),
                "question_types": list(
                    dict.fromkeys(question.question_type for question in questions)
                ),
                "question_count": len(questions),
                "difficulty": activity.source_scope.get("difficulty", "mixed"),
                "request_id": activity.generation_request_id,
            }
        )
        report = validate_generated_activity(
            GeneratedActivity(
                title=activity.title,
                description=activity.description,
                questions=generated_questions,
            ),
            request,
            allowed_sources,
        )
        if not report.valid:
            raise AppError(
                "activity_generation_invalid",
                "活动未通过发布前校验",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {"errors": report.errors},
            )
        activity.validation_warnings = report.warnings
        activity.status = "published"
        activity.published_at = datetime.now(timezone.utc)
        self.db.commit()
        return self.detail(activity.id, include_secrets=False)
