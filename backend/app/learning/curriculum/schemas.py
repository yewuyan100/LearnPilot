from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.learning.agents.curriculum.schemas import CurriculumProposalDraft
from app.schemas.course_architecture import PublishResult


class CurriculumApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CurriculumGenerateRequest(CurriculumApiModel):
    request_id: str = Field(min_length=8, max_length=100)
    actor_key: str = Field(default="local-owner", min_length=1, max_length=200)
    instruction: str = Field(default="请为这个目标生成学习路径", min_length=1, max_length=2000)
    material_ids: list[int] | None = Field(default=None, max_length=10)
    expected_context_version: str | None = Field(default=None, min_length=64, max_length=64)

    @field_validator("material_ids")
    @classmethod
    def unique_material_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and (any(item <= 0 for item in value) or len(value) != len(set(value))):
            raise ValueError("material_ids must contain unique positive IDs")
        return value


class CurriculumDecisionRequest(CurriculumApiModel):
    decision: Literal["accept", "reject"]
    expected_version: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=100)
    confirmed: bool


class CurriculumPublishRequest(CurriculumApiModel):
    expected_proposal_version: int = Field(ge=1)
    draft_version: int = Field(ge=1)
    publish_request_id: str = Field(min_length=8, max_length=100)
    confirmed: bool


class CurriculumGoalRead(CurriculumApiModel):
    id: int
    title: str
    description: str
    current_level: str
    target_date: date | None
    daily_minutes: int


class CurriculumArchitectureRead(CurriculumApiModel):
    draft_id: int
    public_id: str
    version: int
    status: str
    quality_status: str
    quality_report: dict


class CurriculumProposalRead(CurriculumApiModel):
    proposal_id: str
    proposal_type: Literal["curriculum"] = "curriculum"
    status: Literal["pending", "review_required", "accepted", "rejected", "expired"]
    version: int
    context_version: str | None
    generation_request_id: str
    goal: CurriculumGoalRead
    grounding_mode: Literal["goal_only", "source_grounded"]
    material_ids: list[int]
    curriculum: CurriculumProposalDraft
    architecture: CurriculumArchitectureRead
    expires_at: datetime | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CurriculumPublishResult(CurriculumApiModel):
    proposal: CurriculumProposalRead
    publication: PublishResult
