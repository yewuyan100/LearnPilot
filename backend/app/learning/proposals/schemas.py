from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ProposalStatus = Literal["pending", "review_required", "accepted", "rejected", "expired"]


class ProposalEnvelope(BaseModel):
    """Decision envelope only; it never embeds a formal Course or StudyPlan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal_id: str
    proposal_type: str = Field(min_length=1, max_length=64)
    status: ProposalStatus = "pending"
    version: int = Field(default=1, ge=1)
    context_version: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    summary: dict = Field(default_factory=dict)
    expires_at: datetime | None = None
