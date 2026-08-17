from fastapi import APIRouter, Request, status

from app.api.deps import AppClock, AppSettings, DbSession, EmbedderDep, LLMProviderDep
from app.learning.adapters.operations_agent import OperationsAgentAdapter
from app.learning.adapters.curriculum import CurriculumAdapter
from app.learning.agents.curriculum import CurriculumAgent
from app.learning.agents.tutor import ScopedTutorRetrieval, TutorAgent
from app.learning.context.module import LearnerContextModule
from app.learning.curriculum.module import CurriculumModule
from app.learning.events.module import LearningEventRecorder
from app.learning.policies.module import ContextPolicyEngine
from app.learning.routing.module import AgentRouter
from app.learning.runtime.module import LearningRuntime
from app.learning.runtime.schemas import LearningRequest, LearningResponse, ResumeRequest
from app.learning.runtime.store import HarnessRunStore
from app.models.agent import AgentConversation
from app.services.agent.service import AgentService

router = APIRouter(prefix="/learning/runtime", tags=["learning-runtime"])


def _runtime(request, db, settings, embedder, provider, clock) -> LearningRuntime:
    agent_service = AgentService(
        db,
        settings,
        embedder,
        provider,
        request.app.state.agent_runtime.checkpointer,
        clock,
    )

    def lock_provider(conversation_id: int):
        conversation = db.get(AgentConversation, conversation_id)
        key = conversation.thread_id if conversation is not None else str(conversation_id)
        return request.app.state.agent_runtime.lock(key)

    return LearningRuntime(
        run_store=HarnessRunStore(db),
        context_module=LearnerContextModule(db, settings, clock),
        policy_engine=ContextPolicyEngine(),
        router=AgentRouter(),
        operations_adapter=OperationsAgentAdapter(agent_service, lock_provider),
        curriculum_adapter=CurriculumAdapter(
            CurriculumModule(db, settings, CurriculumAgent(provider, settings), clock)
        ),
        tutor_agent=TutorAgent(
            ScopedTutorRetrieval(db, settings, embedder),
            provider,
        ),
        event_recorder=LearningEventRecorder(db, clock),
        clock=clock,
    )


@router.post(
    "/runs",
    response_model=LearningResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_learning_run(
    payload: LearningRequest,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
    clock: AppClock,
):
    return _runtime(request, db, settings, embedder, provider, clock).handle(payload)


@router.post("/runs/{run_id}/resume", response_model=LearningResponse)
def resume_learning_run(
    run_id: str,
    payload: ResumeRequest,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    embedder: EmbedderDep,
    provider: LLMProviderDep,
    clock: AppClock,
):
    return _runtime(request, db, settings, embedder, provider, clock).resume(
        run_id,
        payload.decision,
        payload.request_id,
    )
