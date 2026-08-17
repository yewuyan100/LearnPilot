from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.course import KnowledgePointRead


LifecycleAction = Literal["archive", "supersede"]


class KnowledgePointChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: LifecycleAction
    superseded_by_id: int | None = Field(default=None, gt=0)
    lifecycle_reason: str = Field(min_length=3, max_length=2000)

    @model_validator(mode="after")
    def validate_replacement(self) -> "KnowledgePointChangeRequest":
        if self.action == "supersede" and self.superseded_by_id is None:
            raise ValueError("supersede 操作必须提供 superseded_by_id")
        if self.action == "archive" and self.superseded_by_id is not None:
            raise ValueError("archive 操作不能提供 superseded_by_id")
        return self


class KnowledgePointApplyRequest(KnowledgePointChangeRequest):
    request_id: str = Field(min_length=8, max_length=100)
    expected_version: int = Field(ge=1)
    impact_hash: str = Field(min_length=64, max_length=64)
    confirmed: bool

    @model_validator(mode="after")
    def require_confirmation(self) -> "KnowledgePointApplyRequest":
        if not self.confirmed:
            raise ValueError("必须明确确认生命周期变更")
        return self


class KnowledgePointImpact(BaseModel):
    knowledge_point_id: int
    knowledge_point_title: str
    course_id: int
    point_version: int
    lifecycle_status: str
    action: LifecycleAction
    superseded_by_id: int | None
    prerequisite_edge_ids: list[int]
    study_plan_ids: list[int]
    study_plan_version_ids: list[int]
    study_plan_item_ids: list[int]
    daily_task_ids: list[int]
    actionable_daily_task_ids: list[int]
    learning_session_ids: list[int]
    active_learning_session_ids: list[int]
    activity_ids: list[int]
    mastery_ids: list[int]
    review_schedule_ids: list[int]
    impact_hash: str
    requires_confirmation: bool = True


class KnowledgePointChangeResult(BaseModel):
    point: KnowledgePointRead
    impact: KnowledgePointImpact
    idempotent_replay: bool = False
