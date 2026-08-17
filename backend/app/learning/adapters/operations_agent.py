from contextlib import nullcontext
from typing import Callable, ContextManager

from app.learning.adapters.schemas import AgentExecutionResult
from app.schemas.agent import AgentRunRead
from app.services.agent.service import AgentService


class OperationsAgentAdapter:
    """Adapter from LearningRuntime to the unchanged existing Agent/LangGraph workflow."""

    def __init__(
        self,
        agent_service: AgentService,
        lock_provider: Callable[[int], ContextManager] | None = None,
    ):
        self.agent_service = agent_service
        self.lock_provider = lock_provider or (lambda _conversation_id: nullcontext())

    @staticmethod
    def _result(run: AgentRunRead) -> AgentExecutionResult:
        return AgentExecutionResult(
            agent_run_id=run.id,
            status=run.status,
            answer=run.final_answer,
            confirmation=run.confirmation.model_dump(mode="json") if run.confirmation else None,
            citations=run.citations,
            error_code=run.error_code,
        )

    def execute(
        self,
        *,
        conversation_id: int,
        user_input: str,
        request_id: str,
        harness_run_id: int,
    ) -> AgentExecutionResult:
        with self.lock_provider(conversation_id):
            run = self.agent_service.start_run(
                conversation_id,
                user_input,
                request_id,
                harness_run_id=harness_run_id,
            )
        return self._result(run)

    def resume(
        self,
        *,
        conversation_id: int,
        agent_run_id: int,
        decision: str,
    ) -> AgentExecutionResult:
        with self.lock_provider(conversation_id):
            run = self.agent_service.confirm(agent_run_id, decision)
        return self._result(run)
