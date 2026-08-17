from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    ActivityStatus,
    QuestionDifficulty,
    QuestionType,
    WrongAnswerStatus,
)
from app.schemas.common import Timestamped


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuestionOption(StrictModel):
    id: str = Field(min_length=1, max_length=8, pattern=r"^[A-Z][A-Z0-9_-]*$")
    text: str = Field(min_length=1, max_length=1000)


class RubricItem(StrictModel):
    criterion: str = Field(min_length=1, max_length=500)
    points: float = Field(gt=0, le=1000)
    required_concepts: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_text(self) -> "RubricItem":
        self.criterion = self.criterion.strip()
        concepts = [item.strip() for item in self.required_concepts]
        if not self.criterion or any(not item for item in concepts):
            raise ValueError("评分项和必要概念不能为空白")
        if len(concepts) != len(set(concepts)):
            raise ValueError("同一评分项的必要概念不能重复")
        self.required_concepts = concepts
        return self


class GeneratedQuestion(StrictModel):
    question_type: QuestionType
    stem: str = Field(min_length=1, max_length=4000)
    options: list[QuestionOption] | None = Field(default=None, max_length=12)
    correct_answer: list[str | bool] | None = Field(default=None, max_length=12)
    reference_answer: str | None = Field(default=None, max_length=8000)
    grading_rubric: list[RubricItem] | None = Field(default=None, max_length=20)
    explanation: str = Field(min_length=1, max_length=8000)
    difficulty: QuestionDifficulty
    points: float = Field(gt=0, le=1000)
    cited_source_ids: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_type_fields(self) -> "GeneratedQuestion":
        answer = self.correct_answer
        if self.question_type in {QuestionType.single_choice, QuestionType.multiple_choice}:
            if not self.options or len(self.options) < 3:
                raise ValueError("选择题至少需要 3 个选项")
            if not answer or any(not isinstance(item, str) for item in answer):
                raise ValueError("选择题答案必须是选项 ID")
            if len(answer) != len(set(answer)):
                raise ValueError("选择题答案不能重复")
            if self.question_type == QuestionType.single_choice and len(answer) != 1:
                raise ValueError("单选题只能有一个正确答案")
            if self.question_type == QuestionType.multiple_choice and len(answer) < 2:
                raise ValueError("多选题至少需要两个正确答案")
            if self.reference_answer is not None or self.grading_rubric is not None:
                raise ValueError("选择题不能包含简答题字段")
        elif self.question_type == QuestionType.true_false:
            if self.options is not None:
                raise ValueError("判断题不能包含普通选项")
            if (
                not answer
                or len(answer) != 1
                or type(answer[0]) is not bool
            ):
                raise ValueError("判断题答案必须是单个布尔值")
            if self.reference_answer is not None or self.grading_rubric is not None:
                raise ValueError("判断题不能包含简答题字段")
        else:
            if self.options is not None or answer is not None:
                raise ValueError("简答题不能包含选项或客观答案")
            if not (self.reference_answer or "").strip() or not self.grading_rubric:
                raise ValueError("简答题必须包含参考答案和评分标准")
            criteria = [item.criterion for item in self.grading_rubric]
            if len(criteria) != len(set(criteria)):
                raise ValueError("简答题评分项不能重复")
            rubric_total = round(sum(item.points for item in self.grading_rubric), 6)
            if abs(rubric_total - self.points) > 1e-6:
                raise ValueError("评分标准总分必须等于题目分值")
        return self


class GeneratedActivity(StrictModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=5000)
    questions: list[GeneratedQuestion] = Field(min_length=1, max_length=20)


class ActivityGenerateRequest(StrictModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=5000)
    course_id: int | None = Field(default=None, gt=0)
    knowledge_point_id: int | None = Field(default=None, gt=0)
    learning_goal_id: int | None = Field(default=None, gt=0)
    material_ids: list[int] | None = Field(default=None, max_length=50)
    source_mode: Literal["materials", "without_materials"] = "materials"
    question_types: list[QuestionType] = Field(min_length=1, max_length=4)
    question_count: int = Field(default=8, ge=1)
    difficulty: Literal["easy", "medium", "hard", "mixed"] = "mixed"
    request_id: str = Field(min_length=8, max_length=64)

    @model_validator(mode="after")
    def validate_scope(self) -> "ActivityGenerateRequest":
        if self.material_ids is not None and len(set(self.material_ids)) != len(self.material_ids):
            raise ValueError("资料范围不能包含重复 ID")
        if self.material_ids is not None and any(item <= 0 for item in self.material_ids):
            raise ValueError("资料 ID 必须大于 0")
        has_scope = any((
            self.learning_goal_id,
            self.course_id,
            self.knowledge_point_id,
            self.material_ids is not None,
        ))
        if self.source_mode == "materials" and not has_scope:
            raise ValueError("资料生成模式必须指定学习范围或资料范围")
        if self.source_mode == "without_materials" and self.material_ids:
            raise ValueError("无资料生成模式不能指定资料 ID")
        if len(set(self.question_types)) != len(self.question_types):
            raise ValueError("题型不能重复")
        if self.question_count < len(self.question_types):
            raise ValueError("题目数量不能少于所选题型数量")
        return self


class ActivityUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    status: Literal["archived"] | None = None


class QuestionReorderRequest(StrictModel):
    question_ids: list[int] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_ids(self) -> "QuestionReorderRequest":
        if len(set(self.question_ids)) != len(self.question_ids):
            raise ValueError("题目 ID 不能重复")
        return self


class QuestionSourceRead(Timestamped):
    question_id: int
    source_label: str
    material_id: int | None
    chunk_id: int | None
    rank: int
    score: float
    original_filename: str
    chunk_index: int
    page_number: int | None
    section_title: str | None
    content_excerpt: str
    source_available: bool


class ActivityQuestionAdminRead(Timestamped):
    activity_id: int
    question_index: int
    question_type: str
    stem: str
    options: list[QuestionOption] | None
    correct_answer: list[str | bool] | None
    reference_answer: str | None
    grading_rubric: list[RubricItem] | None
    explanation: str
    difficulty: str
    points: float
    status: str
    sources: list[QuestionSourceRead]


class ActivityQuestionSafeRead(BaseModel):
    id: int
    question_index: int
    question_type: str
    stem: str
    options: list[QuestionOption] | None
    difficulty: str
    points: float
    saved_answer: list[str | bool] | None = None
    saved_answer_text: str | None = None


class ActivityListItem(Timestamped):
    title: str
    description: str
    activity_type: str
    status: str
    course_id: int | None
    knowledge_point_id: int | None
    course_title: str | None
    knowledge_point_title: str | None
    question_count: int
    total_points: float
    published_at: datetime | None
    completed_attempt_count: int
    source_scope: dict


class ActivityDetail(ActivityListItem):
    source_scope: dict
    generation_request_id: str
    prompt_version: str
    model_name: str | None
    validation_warnings: list[str]
    questions: list[ActivityQuestionAdminRead]


class ActivityPage(BaseModel):
    items: list[ActivityListItem]
    total: int
    page: int
    page_size: int
    pages: int


class AttemptStartRequest(StrictModel):
    learning_session_id: int | None = Field(default=None, gt=0)


class AnswerPayload(StrictModel):
    answer: list[str | bool] | None = Field(default=None, max_length=12)
    answer_text: str | None = Field(default=None, max_length=4000)


class AttemptAnswerInput(AnswerPayload):
    question_id: int = Field(gt=0)


class AttemptSubmitRequest(StrictModel):
    request_id: str = Field(min_length=8, max_length=64)
    answers: list[AttemptAnswerInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_questions(self) -> "AttemptSubmitRequest":
        ids = [item.question_id for item in self.answers]
        if len(set(ids)) != len(ids):
            raise ValueError("同一道题不能提交两次")
        return self


class QuizAnswerRead(Timestamped):
    question_id: int
    question_type: str
    stem: str
    answer: list[str | bool] | None
    answer_text: str | None
    is_correct: bool | None
    grading_status: str
    earned_points: float | None
    max_points: float
    feedback: str | None
    matched_rubric_items: list[str] | None
    missing_rubric_items: list[str] | None
    grader_confidence: float | None
    correct_answer: list[str | bool] | None = None
    reference_answer: str | None = None
    grading_rubric: list[RubricItem] | None = None
    explanation: str | None = None
    sources: list[QuestionSourceRead] = Field(default_factory=list)
    wrong_answer_id: int | None = None
    wrong_answer_status: str | None = None


class QuizAttemptRead(Timestamped):
    activity_id: int
    activity_title: str
    learning_session_id: int | None
    request_id: str | None
    status: str
    started_at: datetime
    submitted_at: datetime | None
    graded_at: datetime | None
    total_points: float | None
    earned_points: float | None
    score_percentage: float | None
    correct_count: int
    incorrect_count: int
    partial_count: int
    grading_model: str | None
    grading_prompt_version: str | None
    error_message: str | None
    questions: list[ActivityQuestionSafeRead]
    answers: list[QuizAnswerRead]
    idempotent_replay: bool = False


class ShortAnswerGrade(StrictModel):
    earned_points: float
    matched_items: list[str] = Field(max_length=20)
    missing_items: list[str] = Field(max_length=20)
    feedback: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1)
    answer_supported: bool


class WrongAnswerRead(Timestamped):
    question_id: int
    attempt_id: int
    answer_id: int
    course_id: int | None
    knowledge_point_id: int | None
    course_title: str | None
    knowledge_point_title: str | None
    status: str
    error_type: str
    review_count: int
    last_reviewed_at: datetime | None
    resolved_at: datetime | None
    question_type: str
    stem: str
    explanation: str
    answer: list[str | bool] | None
    answer_text: str | None
    correct_answer: list[str | bool] | None
    reference_answer: str | None
    sources: list[QuestionSourceRead]


class WrongAnswerPage(BaseModel):
    items: list[WrongAnswerRead]
    total: int
    page: int
    page_size: int
    pages: int


class WrongAnswerUpdate(StrictModel):
    status: Literal["active", "resolved", "dismissed"]


class WrongAnswerReviewRequest(StrictModel):
    wrong_answer_ids: list[int] = Field(min_length=1, max_length=50)
    request_id: str = Field(min_length=8, max_length=64)

    @model_validator(mode="after")
    def unique_wrong_answers(self) -> "WrongAnswerReviewRequest":
        if len(set(self.wrong_answer_ids)) != len(self.wrong_answer_ids):
            raise ValueError("错题 ID 不能重复")
        return self
