from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SurfaceContext(ContextModel):
    goal_id: int | None = Field(default=None, gt=0)
    course_id: int | None = Field(default=None, gt=0)
    knowledge_point_id: int | None = Field(default=None, gt=0)
    learning_session_id: int | None = Field(default=None, gt=0)
    lesson_id: int | None = Field(default=None, gt=0)
    lesson_version_id: int | None = Field(default=None, gt=0)
    source_path: str | None = Field(default=None, max_length=500)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=100)


class ContextQuery(ContextModel):
    actor_key: str = Field(min_length=1, max_length=200)
    surface_context: SurfaceContext
    expected_context_version: str | None = Field(default=None, min_length=64, max_length=64)


class GoalContext(ContextModel):
    id: int
    title: str
    description: str
    status: str
    target_date: date | None
    daily_minutes: int
    current_level: str
    updated_at: datetime


class CourseContext(ContextModel):
    id: int
    learning_goal_id: int
    title: str
    status: str
    updated_at: datetime


class KnowledgePointContext(ContextModel):
    id: int
    course_id: int
    title: str
    status: str
    lifecycle_status: str
    version: int
    superseded_by_id: int | None
    updated_at: datetime


class StudyPlanContext(ContextModel):
    id: int
    public_id: str
    status: str
    version: int
    active_version_number: int | None
    active_version_status: str | None
    active_version_stale_at: datetime | None
    updated_at: datetime


class LearningSessionContext(ContextModel):
    id: int
    learning_goal_id: int
    course_id: int | None
    knowledge_point_id: int | None
    daily_task_id: int | None
    lesson_version_id: int | None
    status: str
    started_at: datetime
    ended_at: datetime | None
    invalidated_at: datetime | None
    updated_at: datetime


class LessonContext(ContextModel):
    id: int
    public_id: str
    course_id: int
    title: str
    description: str
    order_index: int
    status: str
    active_version_number: int | None
    updated_at: datetime


class LessonVersionContext(ContextModel):
    id: int
    lesson_id: int
    version_number: int
    status: str
    objectives: list[str]
    estimated_minutes: int
    source_snapshot_hash: str
    published_at: datetime | None
    updated_at: datetime


class MasterySummaryContext(ContextModel):
    knowledge_point_id: int
    mastery_score: float | None
    confidence_score: float
    mastery_level: str
    evidence_count: int
    calculated_at: datetime


class RecentLearningRecord(ContextModel):
    learning_session_id: int
    knowledge_point_id: int | None
    knowledge_point_title: str | None
    status: str
    started_at: datetime
    ended_at: datetime | None


class MaterialReferenceContext(ContextModel):
    material_id: int
    title: str
    original_filename: str
    source_type: str


class MaterialScopeContext(ContextModel):
    requested_scope: dict
    material_ids: list[int] = Field(default_factory=list)
    materials: list[MaterialReferenceContext] = Field(default_factory=list)
    scoped: bool
    empty: bool


class WeakPointContext(ContextModel):
    knowledge_point_id: int
    title: str
    mastery_level: str
    weakness_score: float
    recent_failure: bool
    overdue: bool


class CurrentTaskContext(ContextModel):
    id: int
    title: str
    task_type: str
    status: str
    estimated_minutes: int
    scheduled_date: date
    blocked_at: datetime | None


class NextLearningActionContext(ContextModel):
    action_type: str
    target_kind: str
    target_id: int | None
    title: str
    reason: str
    estimated_minutes: int


class LearnerContext(ContextModel):
    actor_key: str
    goal: GoalContext | None
    course: CourseContext | None
    knowledge_point: KnowledgePointContext | None
    study_plan: StudyPlanContext | None
    learning_session: LearningSessionContext | None
    lesson: LessonContext | None
    lesson_version: LessonVersionContext | None
    mastery_summary: MasterySummaryContext | None
    recent_learning_history: list[RecentLearningRecord] = Field(default_factory=list)
    material_scope: MaterialScopeContext
    weak_points: list[WeakPointContext] = Field(default_factory=list)
    current_task: CurrentTaskContext | None
    next_learning_action: NextLearningActionContext | None
    context_version: str
    valid: bool = True
    invalid_reason: str | None = None
