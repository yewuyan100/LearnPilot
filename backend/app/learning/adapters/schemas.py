from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.learning.context.schemas import LearnerContext
from app.learning.proposals.schemas import ProposalEnvelope


class AgentExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_run_id: int
    status: str
    answer: str | None
    confirmation: dict[str, Any] | None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    error_code: str | None = None


class OperationsAdapterInterface(Protocol):
    def execute(
        self,
        *,
        conversation_id: int,
        user_input: str,
        request_id: str,
        harness_run_id: int,
    ) -> AgentExecutionResult: ...

    def resume(
        self,
        *,
        conversation_id: int,
        agent_run_id: int,
        decision: str,
    ) -> AgentExecutionResult: ...


class CurriculumExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str = "awaiting_confirmation"
    answer: str
    proposal: ProposalEnvelope
    citations: list[dict[str, Any]] = Field(default_factory=list)


class CurriculumAdapterInterface(Protocol):
    def execute(
        self,
        *,
        learner_context: LearnerContext,
        user_input: str,
        request_id: str,
        harness_run_id: int,
    ) -> CurriculumExecutionResult: ...
