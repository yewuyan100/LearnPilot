from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.learning.context.schemas import LearnerContext


class PlanningModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MasteryChangeInput(PlanningModel):
    knowledge_point_id: int = Field(gt=0)
    knowledge_point_title: str = Field(min_length=1, max_length=200)
    old_level: str = Field(min_length=1, max_length=24)
    new_level: str = Field(min_length=1, max_length=24)
    confidence: float = Field(ge=0, le=100)
    evidence_ids: list[int] = Field(min_length=1)


class RecentMasteryEvidence(PlanningModel):
    evidence_id: int = Field(gt=0)
    evidence_type: str = Field(min_length=1, max_length=32)
    normalized_score: float = Field(ge=0, le=100)
    occurred_at: datetime


class CurrentStudyPlanInput(PlanningModel):
    study_plan_id: int = Field(gt=0)
    version: int = Field(ge=1)
    active_version_number: int = Field(ge=1)
    status: str = Field(min_length=1, max_length=32)


class PlanningAgentRequest(PlanningModel):
    learner_context: LearnerContext
    mastery_changes: list[MasteryChangeInput] = Field(min_length=1)
    recent_evidence: list[RecentMasteryEvidence] = Field(min_length=1)
    current_plan: CurrentStudyPlanInput
    goal_deadline: date | None = None


class AffectedPlanItem(PlanningModel):
    kind: Literal["knowledge_point"] = "knowledge_point"
    id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    proposed_change: Literal["add_review"] = "add_review"


class PlanAdjustmentProposal(PlanningModel):
    """Human-reviewable suggestion; it carries no scheduling authority."""

    reason: str = Field(min_length=1, max_length=2000)
    suggestion: str = Field(min_length=1, max_length=1000)
    impact: str = Field(min_length=1, max_length=2000)
    adjustment_kind: Literal["add_review"] = "add_review"
    affected_items: list[AffectedPlanItem] = Field(min_length=1, max_length=20)
    mastery_evidence_ids: list[int] = Field(min_length=1, max_length=100)
