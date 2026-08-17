from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.learning.context.schemas import SurfaceContext
from app.learning.agents.tutor.schemas import TutorAnswer
from app.learning.proposals.schemas import ProposalEnvelope


class RuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LearningRequest(RuntimeModel):
    request_id: str = Field(min_length=8, max_length=100)
    actor_key: str = Field(min_length=1, max_length=200)
    input: str = Field(min_length=1, max_length=4000)
    conversation_id: int = Field(gt=0)
    channel: str = Field(default="web", min_length=1, max_length=32)
    surface_context: SurfaceContext = Field(default_factory=SurfaceContext)
    expected_context_version: str | None = Field(default=None, min_length=64, max_length=64)

    @field_validator("actor_key", "input", "channel")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class LearningResponse(RuntimeModel):
    run_id: str
    status: str
    selected_agent: str | None
    answer: str | None
    proposal: ProposalEnvelope | None
    confirmation: dict[str, Any] | None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    tutor_answer: TutorAnswer | None = None
    context_version: str | None
    warnings: list[str] = Field(default_factory=list)


class ResumeRequest(RuntimeModel):
    decision: str = Field(pattern="^(approve|reject)$")
    request_id: str = Field(min_length=8, max_length=100)
