from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ActionType = Literal[
    "learn",
    "practice",
    "review",
    "resume_session",
    "complete_assessment",
    "review_proposal",
    "replan_required",
]


class NextLearningActionRead(BaseModel):
    action_type: ActionType
    target_kind: str
    target_id: int | None
    learning_goal_id: int | None
    course_id: int | None
    course_title: str | None
    knowledge_point_id: int | None
    knowledge_point_title: str | None
    title: str
    reason_code: str
    reason: str
    priority: int = Field(ge=0, le=100)
    estimated_minutes: int = Field(ge=0)
    from_formal_plan: bool
    is_due_review: bool
    plan_id: int | None = None
    plan_item_id: int | None = None
    cta_label: str
    cta_href: str
    action_signature: str = Field(min_length=64, max_length=64)
    available_minutes: int | None = None


class NextActionAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=8, max_length=100)
    action_signature: str = Field(min_length=64, max_length=64)
    available_minutes: int | None = Field(default=None, gt=0, le=720)


class NextActionAcceptResponse(BaseModel):
    action: NextLearningActionRead
    outcome_kind: str
    outcome_id: int | None
    next_url: str
    daily_task_id: int | None = None
    learning_session_id: int | None = None
    idempotent_replay: bool = False
