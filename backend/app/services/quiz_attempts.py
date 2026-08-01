import json
import logging
from datetime import datetime, timezone
from hashlib import sha256
from threading import Lock

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models.activity_question import ActivityQuestion
from app.models.daily_task import DailyTask
from app.models.learning_activity import LearningActivity
from app.models.learning_session import LearningSession
from app.models.question_source import QuestionSource
from app.models.quiz_answer import QuizAnswer
from app.models.quiz_attempt import QuizAttempt
from app.models.wrong_answer import WrongAnswer
from app.schemas.learning_activity import (
    ActivityQuestionSafeRead,
    AnswerPayload,
    AttemptSubmitRequest,
    QuestionSourceRead,
    QuizAnswerRead,
    QuizAttemptRead,
)
from app.services.grading.objective import normalize_objective_answer
from app.services.grading.service import GradingService
from app.services.llm.base import LLMProvider
from app.services.wrong_answers import WrongAnswerService
from app.services.adaptive_learning.lifecycle import try_refresh_adaptive_learning


logger = logging.getLogger("personal_learning.attempts")
ATTEMPT_SUBMIT_LOCK = Lock()


class QuizAttemptService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        provider: LLMProvider | None,
    ):
        self.db = db
        self.settings = settings
        self.provider = provider

    def _attempt(self, attempt_id: int) -> QuizAttempt:
        attempt = self.db.get(QuizAttempt, attempt_id)
        if attempt is None:
            raise AppError(
                "attempt_not_found",
                "测验记录不存在",
                status.HTTP_404_NOT_FOUND,
                {"id": attempt_id},
            )
        return attempt

    def _activity(self, activity_id: int) -> LearningActivity:
        activity = self.db.get(LearningActivity, activity_id)
        if activity is None:
            raise AppError(
                "activity_not_found", "学习活动不存在", status.HTTP_404_NOT_FOUND
            )
        return activity

    def _questions(self, activity_id: int) -> list[ActivityQuestion]:
        return list(
            self.db.scalars(
                select(ActivityQuestion)
                .where(ActivityQuestion.activity_id == activity_id)
                .order_by(ActivityQuestion.question_index)
            )
        )

    def start(
        self, activity_id: int, learning_session_id: int | None
    ) -> QuizAttemptRead:
        activity = self._activity(activity_id)
        if activity.status != "published":
            raise AppError(
                "activity_not_published",
                "只有已发布活动可以开始测验",
                status.HTTP_409_CONFLICT,
            )
        if learning_session_id:
            session = self.db.get(LearningSession, learning_session_id)
            if session is None:
                raise AppError(
                    "learning_session_not_found",
                    "学习会话不存在",
                    status.HTTP_404_NOT_FOUND,
                )
        attempt = QuizAttempt(
            activity_id=activity.id,
            learning_session_id=learning_session_id,
            status="in_progress",
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(attempt)
        self.db.commit()
        self.db.refresh(attempt)
        return self.serialize(attempt)

    def _validate_payload(
        self, question: ActivityQuestion, payload: AnswerPayload
    ) -> tuple[list[str | bool] | None, str | None]:
        if question.question_type == "short_answer":
            if payload.answer not in (None, []):
                raise AppError(
                    "attempt_answer_invalid",
                    "简答题不能提交选项答案",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            text = payload.answer_text
            if text is not None and len(text) > self.settings.short_answer_max_chars:
                raise AppError(
                    "attempt_answer_invalid",
                    f"简答题答案不能超过 {self.settings.short_answer_max_chars} 字符",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            return None, text
        if (payload.answer_text or "").strip():
            raise AppError(
                "attempt_answer_invalid",
                "客观题不能提交文本答案",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return normalize_objective_answer(question, payload.answer), None

    def save_answer(
        self, attempt_id: int, question_id: int, payload: AnswerPayload
    ) -> QuizAttemptRead:
        attempt = self._attempt(attempt_id)
        if attempt.status != "in_progress":
            raise AppError(
                "attempt_not_in_progress",
                "已提交的测验不能继续修改答案",
                status.HTTP_409_CONFLICT,
            )
        question = self.db.get(ActivityQuestion, question_id)
        if question is None or question.activity_id != attempt.activity_id:
            raise AppError(
                "attempt_answer_invalid",
                "题目不属于该测验",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        answer_json, answer_text = self._validate_payload(question, payload)
        answer = self.db.scalar(
            select(QuizAnswer).where(
                QuizAnswer.attempt_id == attempt.id,
                QuizAnswer.question_id == question.id,
            )
        )
        if answer is None:
            answer = QuizAnswer(
                attempt_id=attempt.id,
                question_id=question.id,
                max_points=question.points,
            )
            self.db.add(answer)
        answer.answer_json = answer_json
        answer.answer_text = answer_text
        answer.grading_status = "pending"
        answer.earned_points = None
        answer.is_correct = None
        self.db.commit()
        return self.serialize(attempt)

    def submit(
        self, attempt_id: int, payload: AttemptSubmitRequest
    ) -> QuizAttemptRead:
        with ATTEMPT_SUBMIT_LOCK:
            return self._submit_locked(attempt_id, payload)

    def _submit_locked(
        self, attempt_id: int, payload: AttemptSubmitRequest
    ) -> QuizAttemptRead:
        attempt = self._attempt(attempt_id)
        canonical = [
            {
                "question_id": item.question_id,
                "answer": item.answer,
                "answer_text": item.answer_text,
            }
            for item in sorted(payload.answers, key=lambda item: item.question_id)
        ]
        submission_hash = sha256(
            json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if attempt.status == "completed":
            if (
                attempt.request_id == payload.request_id
                and attempt.submission_hash == submission_hash
            ):
                return self.serialize(attempt, idempotent_replay=True)
            raise AppError(
                "attempt_already_submitted",
                "该测验已经提交完成",
                status.HTTP_409_CONFLICT,
            )
        if attempt.status not in {"in_progress", "failed"}:
            raise AppError(
                "attempt_not_in_progress",
                "当前测验状态不能提交",
                status.HTTP_409_CONFLICT,
            )
        if attempt.status == "failed" and (
            attempt.request_id != payload.request_id
            or attempt.submission_hash != submission_hash
        ):
            raise AppError(
                "attempt_already_submitted",
                "批改重试必须使用原 request_id 与相同答案",
                status.HTTP_409_CONFLICT,
            )
        activity = self._activity(attempt.activity_id)
        questions = self._questions(activity.id)
        by_id = {question.id: question for question in questions}
        submitted = {item.question_id: item for item in payload.answers}
        if any(question_id not in by_id for question_id in submitted):
            raise AppError(
                "attempt_answer_invalid",
                "提交包含不属于该活动的题目",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        normalized: dict[int, tuple[list[str | bool] | None, str | None]] = {}
        existing_answers = {
            answer.question_id: answer
            for answer in self.db.scalars(
                select(QuizAnswer).where(QuizAnswer.attempt_id == attempt.id)
            )
        }
        for question in questions:
            if question.id in submitted:
                normalized[question.id] = self._validate_payload(
                    question, submitted[question.id]
                )
            elif question.id in existing_answers:
                current = existing_answers[question.id]
                normalized[question.id] = (
                    current.answer_json,
                    current.answer_text,
                )
            else:
                normalized[question.id] = (None, None)
        try:
            attempt.request_id = payload.request_id
            attempt.submission_hash = submission_hash
            attempt.status = "grading"
            attempt.submitted_at = attempt.submitted_at or datetime.now(timezone.utc)
            attempt.error_message = None
            for question in questions:
                answer = existing_answers.get(question.id)
                if answer is None:
                    answer = QuizAnswer(
                        attempt_id=attempt.id,
                        question_id=question.id,
                        max_points=question.points,
                    )
                    self.db.add(answer)
                    existing_answers[question.id] = answer
                answer.answer_json, answer.answer_text = normalized[question.id]
                answer.grading_status = "pending"
                answer.earned_points = None
                answer.is_correct = None
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(
                "attempt_request_conflict",
                "request_id 已用于另一份测验提交",
                status.HTTP_409_CONFLICT,
            ) from exc
        answers = [existing_answers[question.id] for question in questions]
        try:
            score, model = GradingService(
                self.db, self.settings, self.provider
            ).grade(
                attempt=attempt,
                activity=activity,
                questions=questions,
                answers=answers,
            )
            attempt.total_points = score.total_points
            attempt.earned_points = score.earned_points
            attempt.score_percentage = score.score_percentage
            attempt.correct_count = score.correct_count
            attempt.incorrect_count = score.incorrect_count
            attempt.partial_count = score.partial_count
            attempt.grading_model = model
            attempt.grading_prompt_version = (
                self.settings.short_answer_grading_prompt_version
                if any(q.question_type == "short_answer" for q in questions)
                else None
            )
            wrong_count = WrongAnswerService(
                self.db, self.settings
            ).create_for_attempt(attempt, activity, answers)
            WrongAnswerService(self.db, self.settings).update_review_results(
                activity, questions, answers
            )
            attempt.status = "completed"
            attempt.graded_at = datetime.now(timezone.utc)
            self._complete_learning_links(attempt, activity)
            self.db.commit()
            if activity.knowledge_point_id:
                from app.services.adaptive_learning.scheduler import ReviewScheduler
                completed_tasks = self.db.scalars(select(DailyTask).where(
                    DailyTask.knowledge_point_id == activity.knowledge_point_id,
                    DailyTask.status == "completed",
                )).all()
                scheduler = ReviewScheduler(self.db, self.settings)
                for completed_task in completed_tasks:
                    scheduler.complete_for_task(completed_task)
                self.db.commit()
            try_refresh_adaptive_learning(
                self.db, self.settings, activity.knowledge_point_id,
                trigger_type=(
                    "review_completed"
                    if activity.source_scope.get("kind") == "wrong_answer_review"
                    else "quiz_completed"
                ),
                trigger_source_id=attempt.id,
            )
            logger.info(
                "attempt_grading_completed request_id=%s activity_id=%s attempt_id=%s "
                "objective_question_count=%s short_answer_count=%s earned_points=%s "
                "total_points=%s wrong_answer_count=%s model_name=%s prompt_version=%s",
                payload.request_id,
                activity.id,
                attempt.id,
                sum(q.question_type != "short_answer" for q in questions),
                sum(q.question_type == "short_answer" for q in questions),
                attempt.earned_points,
                attempt.total_points,
                wrong_count,
                model,
                attempt.grading_prompt_version,
            )
        except AppError as exc:
            attempt.status = "failed"
            attempt.error_message = exc.message
            self.db.commit()
            raise
        return self.serialize(attempt)

    def _complete_learning_links(
        self, attempt: QuizAttempt, activity: LearningActivity
    ) -> None:
        now = datetime.now(timezone.utc)
        if attempt.learning_session_id:
            session = self.db.get(LearningSession, attempt.learning_session_id)
            if session:
                session.status = "completed"
                session.ended_at = session.ended_at or now
                if session.daily_task_id:
                    task = self.db.get(DailyTask, session.daily_task_id)
                    if task and (task.activity_id is None or task.activity_id == activity.id):
                        task.status = "completed"
        tasks = self.db.scalars(
            select(DailyTask).where(DailyTask.activity_id == activity.id)
        ).all()
        for task in tasks:
            task.status = "completed"

    def serialize(
        self, attempt: QuizAttempt, *, idempotent_replay: bool = False
    ) -> QuizAttemptRead:
        activity = self._activity(attempt.activity_id)
        questions = self._questions(activity.id)
        answers = {
            answer.question_id: answer
            for answer in self.db.scalars(
                select(QuizAnswer).where(QuizAnswer.attempt_id == attempt.id)
            )
        }
        safe_questions = [
            ActivityQuestionSafeRead(
                id=question.id,
                question_index=question.question_index,
                question_type=question.question_type,
                stem=question.stem,
                options=question.options_json,
                difficulty=question.difficulty,
                points=question.points,
                saved_answer=(
                    answers[question.id].answer_json if question.id in answers else None
                ),
                saved_answer_text=(
                    answers[question.id].answer_text if question.id in answers else None
                ),
            )
            for question in questions
        ]
        answer_reads: list[QuizAnswerRead] = []
        completed_or_failed = attempt.status in {"completed", "failed"}
        for question in questions:
            answer = answers.get(question.id)
            if answer is None:
                continue
            sources = []
            if attempt.status == "completed":
                source_rows = self.db.scalars(
                    select(QuestionSource)
                    .where(QuestionSource.question_id == question.id)
                    .order_by(QuestionSource.rank)
                ).all()
                sources = [
                    QuestionSourceRead.model_validate(
                        {
                            **source.__dict__,
                            "source_available": source.chunk_id is not None,
                        }
                    )
                    for source in source_rows
                ]
            wrong = self.db.scalar(
                select(WrongAnswer).where(WrongAnswer.answer_id == answer.id)
            )
            answer_reads.append(
                QuizAnswerRead.model_validate(
                    {
                        **answer.__dict__,
                        "question_type": question.question_type,
                        "stem": question.stem,
                        "answer": answer.answer_json,
                        "matched_rubric_items": answer.matched_rubric_items_json,
                        "missing_rubric_items": answer.missing_rubric_items_json,
                        "correct_answer": (
                            question.correct_answer_json
                            if attempt.status == "completed"
                            else None
                        ),
                        "reference_answer": (
                            question.reference_answer
                            if attempt.status == "completed"
                            else None
                        ),
                        "grading_rubric": (
                            question.grading_rubric_json
                            if attempt.status == "completed"
                            else None
                        ),
                        "explanation": (
                            question.explanation if completed_or_failed else None
                        ),
                        "sources": sources,
                        "wrong_answer_id": wrong.id if wrong else None,
                        "wrong_answer_status": wrong.status if wrong else None,
                    }
                )
            )
        return QuizAttemptRead.model_validate(
            {
                "id": attempt.id,
                "activity_id": attempt.activity_id,
                "learning_session_id": attempt.learning_session_id,
                "status": attempt.status,
                "started_at": attempt.started_at,
                "submitted_at": attempt.submitted_at,
                "graded_at": attempt.graded_at,
                "total_points": attempt.total_points,
                "earned_points": attempt.earned_points,
                "score_percentage": attempt.score_percentage,
                "correct_count": attempt.correct_count,
                "incorrect_count": attempt.incorrect_count,
                "partial_count": attempt.partial_count,
                "grading_model": attempt.grading_model,
                "grading_prompt_version": attempt.grading_prompt_version,
                "error_message": attempt.error_message,
                "created_at": attempt.created_at,
                "updated_at": attempt.updated_at,
                "activity_title": activity.title,
                "questions": safe_questions,
                "answers": answer_reads,
                "idempotent_replay": idempotent_replay,
            }
        )
