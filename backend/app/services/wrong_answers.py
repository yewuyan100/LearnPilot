from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from math import ceil

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models.activity_question import ActivityQuestion
from app.models.course import Course
from app.models.knowledge_point import KnowledgePoint
from app.models.learning_activity import LearningActivity
from app.models.question_source import QuestionSource
from app.models.quiz_answer import QuizAnswer
from app.models.quiz_attempt import QuizAttempt
from app.models.wrong_answer import WrongAnswer
from app.schemas.learning_activity import (
    QuestionSourceRead,
    WrongAnswerPage,
    WrongAnswerRead,
)


class WrongAnswerService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def create_for_attempt(
        self,
        attempt: QuizAttempt,
        activity: LearningActivity,
        answers: list[QuizAnswer],
    ) -> int:
        if activity.source_scope.get("kind") == "wrong_answer_review":
            return 0
        created = 0
        for answer in answers:
            if answer.grading_status != "completed" or answer.earned_points is None:
                continue
            question = self.db.get(ActivityQuestion, answer.question_id)
            assert question is not None
            if answer.answer_json is None and not (answer.answer_text or "").strip():
                error_type = "unanswered"
            elif answer.earned_points <= 0:
                error_type = "incorrect"
            elif (
                question.question_type == "short_answer"
                and answer.earned_points / answer.max_points
                < self.settings.wrong_answer_short_answer_threshold
            ):
                error_type = "partial"
            else:
                continue
            existing = self.db.scalar(
                select(WrongAnswer).where(
                    WrongAnswer.attempt_id == attempt.id,
                    WrongAnswer.answer_id == answer.id,
                )
            )
            if existing is None:
                self.db.add(
                    WrongAnswer(
                        question_id=question.id,
                        attempt_id=attempt.id,
                        answer_id=answer.id,
                        course_id=activity.course_id,
                        knowledge_point_id=activity.knowledge_point_id,
                        status="active",
                        error_type=error_type,
                    )
                )
                created += 1
        self.db.flush()
        return created

    def update_review_results(
        self,
        activity: LearningActivity,
        questions: list[ActivityQuestion],
        answers: list[QuizAnswer],
    ) -> None:
        if activity.source_scope.get("kind") != "wrong_answer_review":
            return
        mapping = activity.source_scope.get("wrong_answer_map") or {}
        by_question = {answer.question_id: answer for answer in answers}
        now = datetime.now(timezone.utc)
        for question in questions:
            wrong_id = mapping.get(str(question.id))
            if not wrong_id:
                continue
            wrong = self.db.get(WrongAnswer, int(wrong_id))
            if wrong is None:
                continue
            answer = by_question.get(question.id)
            wrong.review_count += 1
            wrong.last_reviewed_at = now
            if (
                answer
                and answer.grading_status == "completed"
                and answer.earned_points is not None
                and abs(answer.earned_points - answer.max_points) < 1e-6
            ):
                wrong.status = "resolved"
                wrong.resolved_at = now
            else:
                wrong.status = "active"
                wrong.resolved_at = None

    def _get(self, wrong_id: int) -> WrongAnswer:
        wrong = self.db.get(WrongAnswer, wrong_id)
        if wrong is None:
            raise AppError(
                "wrong_answer_not_found",
                "错题不存在",
                status.HTTP_404_NOT_FOUND,
                {"id": wrong_id},
            )
        return wrong

    def _serialize(self, wrong: WrongAnswer) -> WrongAnswerRead:
        question = self.db.get(ActivityQuestion, wrong.question_id)
        answer = self.db.get(QuizAnswer, wrong.answer_id)
        assert question is not None and answer is not None
        sources = self.db.scalars(
            select(QuestionSource)
            .where(QuestionSource.question_id == question.id)
            .order_by(QuestionSource.rank)
        ).all()
        course_title = (
            self.db.scalar(select(Course.title).where(Course.id == wrong.course_id))
            if wrong.course_id
            else None
        )
        point_title = (
            self.db.scalar(
                select(KnowledgePoint.title).where(
                    KnowledgePoint.id == wrong.knowledge_point_id
                )
            )
            if wrong.knowledge_point_id
            else None
        )
        return WrongAnswerRead.model_validate(
            {
                **wrong.__dict__,
                "course_title": course_title,
                "knowledge_point_title": point_title,
                "question_type": question.question_type,
                "stem": question.stem,
                "explanation": question.explanation,
                "answer": answer.answer_json,
                "answer_text": answer.answer_text,
                "correct_answer": question.correct_answer_json,
                "reference_answer": question.reference_answer,
                "sources": [
                    QuestionSourceRead.model_validate(
                        {
                            **source.__dict__,
                            "source_available": source.chunk_id is not None,
                        }
                    )
                    for source in sources
                ],
            }
        )

    def list(
        self,
        *,
        page: int,
        page_size: int,
        status_filter: str | None,
        course_id: int | None,
        knowledge_point_id: int | None,
        question_type: str | None,
    ) -> WrongAnswerPage:
        query = select(WrongAnswer)
        if status_filter:
            query = query.where(WrongAnswer.status == status_filter)
        if course_id:
            query = query.where(WrongAnswer.course_id == course_id)
        if knowledge_point_id:
            query = query.where(WrongAnswer.knowledge_point_id == knowledge_point_id)
        if question_type:
            query = query.join(
                ActivityQuestion, ActivityQuestion.id == WrongAnswer.question_id
            ).where(ActivityQuestion.question_type == question_type)
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = self.db.scalars(
            query.order_by(WrongAnswer.updated_at.desc(), WrongAnswer.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return WrongAnswerPage(
            items=[self._serialize(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=ceil(total / page_size) if total else 0,
        )

    def detail(self, wrong_id: int) -> WrongAnswerRead:
        return self._serialize(self._get(wrong_id))

    def update_status(self, wrong_id: int, value: str) -> WrongAnswerRead:
        wrong = self._get(wrong_id)
        wrong.status = value
        if value == "resolved":
            wrong.resolved_at = datetime.now(timezone.utc)
        elif value in {"active", "dismissed"}:
            wrong.resolved_at = None
        self.db.commit()
        return self._serialize(wrong)

    def create_review_attempt(
        self,
        *,
        wrong_answer_ids: list[int],
        request_id: str,
        learning_session_id: int | None = None,
    ) -> QuizAttempt:
        wrongs = [self._get(item) for item in wrong_answer_ids]
        if any(wrong.status == "dismissed" for wrong in wrongs):
            raise AppError(
                "review_request_invalid",
                "已忽略的错题不能加入复习",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        config_hash = sha256(
            json.dumps(sorted(wrong_answer_ids), separators=(",", ":")).encode()
        ).hexdigest()
        generation_id = "review-" + sha256(request_id.encode()).hexdigest()[:57]
        existing = self.db.scalar(
            select(LearningActivity).where(
                LearningActivity.generation_request_id == generation_id
            )
        )
        if existing:
            if existing.generation_config_hash != config_hash:
                raise AppError(
                    "activity_request_conflict",
                    "相同 request_id 已用于不同的错题集合",
                    status.HTTP_409_CONFLICT,
                )
            attempt = self.db.scalar(
                select(QuizAttempt)
                .where(QuizAttempt.activity_id == existing.id)
                .order_by(QuizAttempt.id)
            )
            assert attempt is not None
            return attempt
        activity = LearningActivity(
            title=f"错题复习 · {len(wrongs)} 题",
            description="基于错题快照创建，不使用间隔重复或掌握度算法。",
            activity_type="quiz",
            status="published",
            course_id=wrongs[0].course_id if all(w.course_id == wrongs[0].course_id for w in wrongs) else None,
            knowledge_point_id=(
                wrongs[0].knowledge_point_id
                if all(w.knowledge_point_id == wrongs[0].knowledge_point_id for w in wrongs)
                else None
            ),
            source_scope={
                "kind": "wrong_answer_review",
                "original_wrong_answer_ids": wrong_answer_ids,
                "wrong_answer_map": {},
            },
            question_count=len(wrongs),
            total_points=0,
            generation_request_id=generation_id,
            generation_config_hash=config_hash,
            prompt_version="wrong-answer-review-v1",
            model_name=None,
            published_at=datetime.now(timezone.utc),
        )
        self.db.add(activity)
        self.db.flush()
        mapping: dict[str, int] = {}
        total_points = 0.0
        for index, wrong in enumerate(wrongs, start=1):
            original = self.db.get(ActivityQuestion, wrong.question_id)
            assert original is not None
            copy = ActivityQuestion(
                activity_id=activity.id,
                question_index=index,
                question_type=original.question_type,
                stem=original.stem,
                options_json=original.options_json,
                correct_answer_json=original.correct_answer_json,
                reference_answer=original.reference_answer,
                grading_rubric_json=original.grading_rubric_json,
                explanation=original.explanation,
                difficulty=original.difficulty,
                points=original.points,
                content_hash=original.content_hash,
            )
            self.db.add(copy)
            self.db.flush()
            mapping[str(copy.id)] = wrong.id
            total_points += original.points
            sources = self.db.scalars(
                select(QuestionSource).where(
                    QuestionSource.question_id == original.id
                )
            ).all()
            for source in sources:
                self.db.add(
                    QuestionSource(
                        question_id=copy.id,
                        source_label=source.source_label,
                        material_id=source.material_id,
                        chunk_id=source.chunk_id,
                        rank=source.rank,
                        score=source.score,
                        original_filename=source.original_filename,
                        chunk_index=source.chunk_index,
                        page_number=source.page_number,
                        section_title=source.section_title,
                        content_excerpt=source.content_excerpt,
                    )
                )
            wrong.status = "reviewing"
        activity.total_points = round(total_points, 2)
        activity.source_scope = {**activity.source_scope, "wrong_answer_map": mapping}
        attempt = QuizAttempt(
            activity_id=activity.id,
            learning_session_id=learning_session_id,
            status="in_progress",
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(attempt)
        self.db.commit()
        self.db.refresh(attempt)
        return attempt
