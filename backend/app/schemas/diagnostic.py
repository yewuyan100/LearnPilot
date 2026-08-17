from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import QuestionDifficulty, QuestionType
from app.schemas.learning_activity import QuizAttemptRead


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DiagnosticCreateRequest(StrictModel):
    request_id: str = Field(min_length=8, max_length=100)
    questions_per_point: int = Field(default=2, ge=1, le=4)
    question_types: list[QuestionType] = Field(
        default_factory=lambda: [
            QuestionType.single_choice,
            QuestionType.multiple_choice,
            QuestionType.true_false,
            QuestionType.short_answer,
        ],
        min_length=1,
        max_length=4,
    )
    difficulty: QuestionDifficulty = QuestionDifficulty.medium
    supersedes_session_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def unique_types(self) -> "DiagnosticCreateRequest":
        if len(set(self.question_types)) != len(self.question_types):
            raise ValueError("诊断题型不能重复")
        return self


class DiagnosticAnswerSave(StrictModel):
    expected_version: int = Field(ge=1)
    answer: list[str | bool] | None = Field(default=None, max_length=12)
    answer_text: str | None = Field(default=None, max_length=4000)


class DiagnosticSubmitAnswer(StrictModel):
    question_id: int = Field(gt=0)
    answer: list[str | bool] | None = Field(default=None, max_length=12)
    answer_text: str | None = Field(default=None, max_length=4000)


class DiagnosticSubmitRequest(StrictModel):
    request_id: str = Field(min_length=8, max_length=100)
    expected_version: int = Field(ge=1)
    answers: list[DiagnosticSubmitAnswer] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_questions(self) -> "DiagnosticSubmitRequest":
        ids = [item.question_id for item in self.answers]
        if len(ids) != len(set(ids)):
            raise ValueError("同一道诊断题不能提交两次")
        return self


class DiagnosticAdjustmentRequest(StrictModel):
    request_id: str = Field(min_length=8, max_length=100)
    expected_version: int = Field(ge=1)
    ability_level: str = Field(pattern="^(evidence_insufficient|beginner|developing|proficient|strong)$")
    confidence: float = Field(ge=0, le=1)
    is_skill_gap: bool
    evidence_insufficient: bool
    priority: int = Field(ge=0, le=100)
    reason: str = Field(min_length=3, max_length=2000)


class DiagnosticAssessmentRead(BaseModel):
    quiz_answer_id: int
    status: str
    candidate_score: float | None
    dimensions: list
    rationale: str
    confidence: float | None
    recommend_manual_review: bool
    rubric_version: str | None
    model_name: str | None
    error_code: str | None


class DiagnosticKnowledgeResultRead(BaseModel):
    id: int
    knowledge_point_id: int
    knowledge_point_title: str
    answered_count: int
    graded_count: int
    earned_points: float | None
    possible_points: float | None
    score_percentage: float | None
    confidence: float
    ability_level: str
    is_skill_gap: bool
    evidence_insufficient: bool
    priority: int
    reason: str
    evidence_answer_ids: list[int]
    evidence_source_ids: list[int]
    mastery_evidence_id: int | None
    version: int
    assessments: list[DiagnosticAssessmentRead] = Field(default_factory=list)


class DiagnosticSessionRead(BaseModel):
    id: int
    public_id: str
    course_id: int
    course_title: str
    status: str
    version: int
    generation_request_id: str
    activity_id: int | None
    attempt_id: int | None
    supersedes_session_id: int | None
    prompt_version: str
    model_name: str | None
    coverage_report: dict
    generation_metrics: dict
    last_error_code: str | None
    last_error_message: str | None
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    attempt: QuizAttemptRead | None = None
    results: list[DiagnosticKnowledgeResultRead] = Field(default_factory=list)
    idempotent_replay: bool = False


class DiagnosticHistoryResponse(BaseModel):
    items: list[DiagnosticSessionRead]
    total: int
