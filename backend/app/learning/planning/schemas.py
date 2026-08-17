from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.learning.agents.planning.schemas import AffectedPlanItem, MasteryChangeInput
from app.learning.proposals.schemas import ProposalStatus


class PlanningRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanAdjustmentDecisionRequest(PlanningRequestModel):
    request_id: str = Field(min_length=8, max_length=100)
    decision: Literal["accept", "reject"]
    expected_version: int = Field(ge=1)
    context_version: str = Field(min_length=64, max_length=64)
    confirmed: bool = False


class PlanAdjustmentProposalRead(BaseModel):
    proposal_id: str
    proposal_type: Literal["plan_adjustment"] = "plan_adjustment"
    status: ProposalStatus
    version: int
    context_version: str
    source_event_id: str
    study_plan_id: int
    study_plan_version: int
    active_plan_version: int
    reason: str
    suggestion: str
    impact: str
    adjustment_kind: Literal["add_review"]
    affected_items: list[AffectedPlanItem]
    mastery_change: MasteryChangeInput
    mastery_evidence_ids: list[int]
    application: dict | None = None
    expires_at: datetime | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime
