import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models.activity_question import ActivityQuestion
from app.models.learning_activity import LearningActivity
from app.models.question_source import QuestionSource
from app.models.quiz_answer import QuizAnswer
from app.models.quiz_attempt import QuizAttempt
from app.services.grading.aggregator import AggregateScore, aggregate_scores
from app.services.grading.objective import grade_objective
from app.services.grading.short_answer import grade_short_answer
from app.services.llm.base import LLMProvider
from fastapi import status


logger = logging.getLogger("personal_learning.grading")


class GradingService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        provider: LLMProvider | None,
    ):
        self.db = db
        self.settings = settings
        self.provider = provider

    def grade(
        self,
        *,
        attempt: QuizAttempt,
        activity: LearningActivity,
        questions: list[ActivityQuestion],
        answers: list[QuizAnswer],
    ) -> tuple[AggregateScore, str | None]:
        by_question = {question.id: question for question in questions}
        grading_model: str | None = None
        failures = 0
        failure_details: list[dict] = []
        for answer in answers:
            question = by_question[answer.question_id]
            if question.question_type != "short_answer":
                result = grade_objective(question, answer.answer_json)
                answer.earned_points = result.earned_points
                answer.is_correct = result.is_correct
                answer.grading_status = "completed"
                answer.feedback = result.feedback
                answer.matched_rubric_items_json = None
                answer.missing_rubric_items_json = None
                answer.grader_confidence = 1.0
                continue
            text = (answer.answer_text or "").strip()
            if not text:
                answer.earned_points = 0
                answer.is_correct = False
                answer.grading_status = "completed"
                answer.feedback = "未作答"
                answer.matched_rubric_items_json = []
                answer.missing_rubric_items_json = [
                    item["criterion"] for item in question.grading_rubric_json or []
                ]
                answer.grader_confidence = 1.0
                continue
            if self.provider is None:
                answer.grading_status = "failed"
                answer.earned_points = None
                answer.feedback = "简答题批改模型尚未配置"
                failures += 1
                continue
            sources = self.db.scalars(
                select(QuestionSource)
                .where(QuestionSource.question_id == question.id)
                .order_by(QuestionSource.rank)
            ).all()
            try:
                result = grade_short_answer(
                    provider=self.provider,
                    settings=self.settings,
                    question=question,
                    answer_text=text,
                    sources=list(sources),
                )
                grade = result.value
                grading_model = result.model_name
                answer.earned_points = grade.earned_points
                answer.is_correct = abs(grade.earned_points - question.points) < 1e-6
                answer.grading_status = "completed"
                answer.feedback = grade.feedback
                answer.matched_rubric_items_json = grade.matched_items
                answer.missing_rubric_items_json = grade.missing_items
                answer.grader_confidence = grade.confidence
            except AppError as exc:
                answer.grading_status = "failed"
                answer.earned_points = None
                answer.is_correct = None
                answer.feedback = exc.message
                failures += 1
                failure_details.append(
                    {
                        "question_id": question.id,
                        "code": exc.code,
                        "details": exc.details,
                    }
                )
        self.db.flush()
        if failures:
            raise AppError(
                "grading_failed",
                "部分简答题暂未完成批改，可使用相同提交请求重试",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                {
                    "failed_question_count": failures,
                    "failures": failure_details,
                },
            )
        return aggregate_scores(answers), grading_model
