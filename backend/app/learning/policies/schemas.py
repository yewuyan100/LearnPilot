from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.learning.context.schemas import LearnerContext


PolicyPhase = Literal["pre_route", "after_result", "before_commit"]


class PolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: PolicyPhase
    context: LearnerContext
    expected_context_version: str | None = None
    request_conflict: bool = False
    result: dict[str, Any] | None = None


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool
    code: str | None = None
    reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
