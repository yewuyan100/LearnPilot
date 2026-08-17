from datetime import date, datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentConversationContext(StrictModel):
    context_type: Literal["general", "goal", "material", "lesson"] = "general"
    context_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_context(self) -> "AgentConversationContext":
        if (self.context_type == "general") != (self.context_id is None):
            raise ValueError("general context must not have an id; scoped context requires one")
        return self


class AgentConversationCreate(StrictModel):
    title: str = Field(default="新建学习助手会话", min_length=1, max_length=200)
    context: AgentConversationContext = Field(default_factory=AgentConversationContext)


class AgentRunCreate(StrictModel):
    input: str = Field(min_length=1, max_length=4000)
    request_id: str = Field(min_length=8, max_length=64)


class AgentConfirmRequest(StrictModel):
    decision: Literal["approve", "reject"]


class AgentCitation(BaseModel):
    source_label: str
    material_id: int | None = None
    chunk_id: int | None = None
    original_filename: str
    page_number: int | None = None
    section_title: str | None = None
    content_excerpt: str


class AgentMessageRead(BaseModel):
    id: int
    role: str
    content: str
    citations: list[dict]
    run_id: int | None
    created_at: datetime


class AgentConversationRead(BaseModel):
    id: int
    title: str
    status: str
    thread_id: str
    context: AgentConversationContext
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AgentConversationDetail(AgentConversationRead):
    messages: list[AgentMessageRead]


class AgentConfirmationRead(BaseModel):
    id: int
    summary: str
    tool_name: str
    arguments: dict[str, Any]
    status: str
    expires_at: datetime


class AgentToolCallRead(BaseModel):
    id: int
    step_index: int
    tool_name: str
    tool_kind: str
    arguments: dict[str, Any]
    status: str
    result: dict[str, Any] | None
    duration_ms: int | None


class AgentPublicError(BaseModel):
    code: str
    safe_message: str
    retryable: bool


class AgentRunRead(BaseModel):
    id: int
    conversation_id: int
    request_id: str
    input: str
    status: str
    intent: str | None
    final_answer: str | None
    citations: list[dict]
    error_code: str | None
    error: AgentPublicError | None = None
    idempotent_replay: bool = False
    confirmation: AgentConfirmationRead | None = None
    tool_calls: list[AgentToolCallRead] = Field(default_factory=list)
    performance: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AgentStatusRead(BaseModel):
    enabled: bool
    checkpoint_enabled: bool
    llm_configured: bool
    model: str | None
    max_steps: int
    read_tools: list[str]
    write_tools: list[str]


class IntentClassification(StrictModel):
    intent: Literal[
        "answer_materials", "search_materials", "list_courses", "list_knowledge_points",
        "list_daily_tasks", "get_learning_progress", "list_learning_activities",
        "get_activity_summary", "list_quiz_attempts", "get_wrong_answers",
        "get_knowledge_mastery", "list_weak_knowledge_points", "list_due_reviews",
        "get_adaptive_recommendations", "explain_mastery", "get_next_learning_action",
        "accept_review_recommendation",
        "create_daily_task", "update_daily_task_status", "save_learning_note",
        "generate_learning_activity", "create_wrong_answer_review", "start_quiz_attempt",
        "compound", "clarification", "unsupported"
    ]
    confidence: float = Field(ge=0, le=1)
    clarification_question: str | None = Field(default=None, max_length=500)
    entities: dict[str, Any] = Field(default_factory=dict)


class EmptyToolArguments(StrictModel):
    pass


class MaterialQueryArguments(StrictModel):
    material_ids: list[int] | None = Field(default=None, max_length=50)
    top_k: int | None = Field(default=None, ge=1, le=20)


class AnswerFromMaterialsArguments(MaterialQueryArguments):
    question: str = Field(min_length=1, max_length=4000)


class SearchMaterialsArguments(MaterialQueryArguments):
    query: str = Field(min_length=1, max_length=2000)
    min_score: float | None = Field(default=None, ge=-1, le=1)


class LimitArguments(StrictModel):
    limit: int | None = Field(default=None, ge=1, le=100)


class CourseArguments(StrictModel):
    course_id: int | None = Field(default=None, gt=0)


class DailyTaskListArguments(StrictModel):
    scheduled_date: date | None = None


class ActivityListArguments(StrictModel):
    status: str | None = Field(default=None, min_length=1, max_length=32)


class ActivityArguments(StrictModel):
    activity_id: int = Field(gt=0)


class QuizAttemptListArguments(StrictModel):
    activity_id: int | None = Field(default=None, gt=0)
    limit: int | None = Field(default=None, ge=1, le=100)


class WrongAnswerListArguments(StrictModel):
    status: Literal["active", "resolved", "dismissed"] | None = None
    course_id: int | None = Field(default=None, gt=0)
    knowledge_point_id: int | None = Field(default=None, gt=0)
    question_type: Literal["single_choice", "multiple_choice", "true_false", "short_answer"] | None = None
    limit: int | None = Field(default=None, ge=1, le=100)


class KnowledgePointArguments(StrictModel):
    knowledge_point_id: int = Field(gt=0)


class WeakKnowledgePointArguments(CourseArguments):
    limit: int | None = Field(default=None, ge=1, le=100)
    include_unassessed: bool | None = None


class DueReviewArguments(CourseArguments):
    start_date: date | None = None
    end_date: date | None = None
    status: str | None = Field(default=None, min_length=1, max_length=32)
    overdue: bool | None = None
    limit: int | None = Field(default=None, ge=1, le=100)


class AdaptiveRecommendationArguments(CourseArguments):
    status: str | None = Field(default=None, min_length=1, max_length=32)
    limit: int | None = Field(default=None, ge=1, le=100)


class NextLearningActionArguments(StrictModel):
    available_minutes: int | None = Field(default=None, ge=1, le=1440)


class CreateDailyTaskArguments(StrictModel):
    learning_goal_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    scheduled_date: date
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)
    course_id: int | None = Field(default=None, gt=0)
    knowledge_point_id: int | None = Field(default=None, gt=0)
    activity_id: int | None = Field(default=None, gt=0)
    task_type: str | None = Field(default=None, min_length=1, max_length=32)
    status: Literal["pending", "in_progress", "completed", "skipped"] | None = None


class UpdateDailyTaskStatusArguments(StrictModel):
    task_id: int = Field(gt=0)
    status: Literal["pending", "in_progress", "completed", "skipped"]


class SaveLearningNoteArguments(CourseArguments):
    learning_goal_id: int = Field(gt=0)
    note: str = Field(min_length=1, max_length=8000)
    knowledge_point_id: int | None = Field(default=None, gt=0)


class GenerateLearningActivityArguments(CourseArguments):
    title: str = Field(min_length=1, max_length=255)
    material_ids: list[int] = Field(min_length=1, max_length=50)
    question_types: list[Literal["single_choice", "multiple_choice", "true_false", "short_answer"]] = Field(min_length=1, max_length=4)
    question_count: int = Field(ge=1, le=20)
    difficulty: Literal["easy", "medium", "hard", "mixed"]
    knowledge_point_id: int | None = Field(default=None, gt=0)


class WrongAnswerReviewArguments(StrictModel):
    wrong_answer_ids: list[int] = Field(min_length=1, max_length=100)


class StartQuizAttemptArguments(ActivityArguments):
    learning_session_id: int | None = Field(default=None, gt=0)


class AcceptReviewRecommendationArguments(StrictModel):
    recommendation_id: int = Field(gt=0)


def _step(name: str, arguments: type[StrictModel]):
    return type(
        "".join(part.title() for part in name.split("_")) + "Step",
        (StrictModel,),
        {
            "__annotations__": {
                "tool_name": Literal[name],
                "arguments": arguments,
            },
            "tool_name": name,
        },
    )


AnswerFromMaterialsStep = _step("answer_from_materials", AnswerFromMaterialsArguments)
SearchMaterialsStep = _step("search_materials", SearchMaterialsArguments)
ListCoursesStep = _step("list_courses", LimitArguments)
ListKnowledgePointsStep = _step("list_knowledge_points", CourseArguments)
ListDailyTasksStep = _step("list_daily_tasks", DailyTaskListArguments)
GetLearningProgressStep = _step("get_learning_progress", EmptyToolArguments)
ListLearningActivitiesStep = _step("list_learning_activities", ActivityListArguments)
GetActivitySummaryStep = _step("get_activity_summary", ActivityArguments)
ListQuizAttemptsStep = _step("list_quiz_attempts", QuizAttemptListArguments)
GetWrongAnswersStep = _step("get_wrong_answers", WrongAnswerListArguments)
GetKnowledgeMasteryStep = _step("get_knowledge_mastery", KnowledgePointArguments)
ListWeakKnowledgePointsStep = _step("list_weak_knowledge_points", WeakKnowledgePointArguments)
ListDueReviewsStep = _step("list_due_reviews", DueReviewArguments)
GetAdaptiveRecommendationsStep = _step("get_adaptive_recommendations", AdaptiveRecommendationArguments)
ExplainMasteryStep = _step("explain_mastery", KnowledgePointArguments)
GetNextLearningActionStep = _step("get_next_learning_action", NextLearningActionArguments)
CreateDailyTaskStep = _step("create_daily_task", CreateDailyTaskArguments)
UpdateDailyTaskStatusStep = _step("update_daily_task_status", UpdateDailyTaskStatusArguments)
SaveLearningNoteStep = _step("save_learning_note", SaveLearningNoteArguments)
GenerateLearningActivityStep = _step("generate_learning_activity", GenerateLearningActivityArguments)
CreateWrongAnswerReviewStep = _step("create_wrong_answer_review", WrongAnswerReviewArguments)
StartQuizAttemptStep = _step("start_quiz_attempt", StartQuizAttemptArguments)
AcceptReviewRecommendationStep = _step("accept_review_recommendation", AcceptReviewRecommendationArguments)

PlannedTool = Annotated[
    Union[
        AnswerFromMaterialsStep,
        SearchMaterialsStep,
        ListCoursesStep,
        ListKnowledgePointsStep,
        ListDailyTasksStep,
        GetLearningProgressStep,
        ListLearningActivitiesStep,
        GetActivitySummaryStep,
        ListQuizAttemptsStep,
        GetWrongAnswersStep,
        GetKnowledgeMasteryStep,
        ListWeakKnowledgePointsStep,
        ListDueReviewsStep,
        GetAdaptiveRecommendationsStep,
        ExplainMasteryStep,
        GetNextLearningActionStep,
        CreateDailyTaskStep,
        UpdateDailyTaskStatusStep,
        SaveLearningNoteStep,
        GenerateLearningActivityStep,
        CreateWrongAnswerReviewStep,
        StartQuizAttemptStep,
        AcceptReviewRecommendationStep,
    ],
    Field(discriminator="tool_name"),
]


class AgentPlan(StrictModel):
    steps: list[PlannedTool] = Field(default_factory=list, max_length=4)
    response_hint: str = Field(default="", max_length=500)


class AgentResponseDraft(StrictModel):
    answer: str = Field(min_length=1, max_length=8000)
