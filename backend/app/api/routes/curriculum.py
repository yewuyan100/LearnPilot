from fastapi import APIRouter, status

from app.api.deps import AppClock, AppSettings, DbSession, LLMProviderDep
from app.learning.agents.curriculum import CurriculumAgent
from app.learning.context import ContextQuery, LearnerContextModule, SurfaceContext
from app.learning.curriculum import (
    CurriculumDecisionRequest,
    CurriculumGenerateRequest,
    CurriculumModule,
    CurriculumProposalRead,
    CurriculumPublishRequest,
    CurriculumPublishResult,
)


router = APIRouter(tags=["curriculum"])


def _module(db, settings, provider, clock) -> CurriculumModule:
    return CurriculumModule(db, settings, CurriculumAgent(provider, settings), clock)


@router.post(
    "/learning-goals/{goal_id}/curriculum-proposals",
    response_model=CurriculumProposalRead,
    status_code=status.HTTP_201_CREATED,
)
def generate_curriculum(
    goal_id: int,
    payload: CurriculumGenerateRequest,
    db: DbSession,
    settings: AppSettings,
    provider: LLMProviderDep,
    clock: AppClock,
):
    context = LearnerContextModule(db, settings, clock).load(
        ContextQuery(
            actor_key=payload.actor_key,
            surface_context=SurfaceContext(goal_id=goal_id),
            expected_context_version=payload.expected_context_version,
        )
    )
    return _module(db, settings, provider, clock).generate(context, payload)


@router.get(
    "/curriculum-proposals/{proposal_id}",
    response_model=CurriculumProposalRead,
)
def get_curriculum_proposal(
    proposal_id: str,
    db: DbSession,
    settings: AppSettings,
    provider: LLMProviderDep,
    clock: AppClock,
):
    return _module(db, settings, provider, clock).get(proposal_id)


@router.post(
    "/curriculum-proposals/{proposal_id}/decision",
    response_model=CurriculumProposalRead,
)
def decide_curriculum_proposal(
    proposal_id: str,
    payload: CurriculumDecisionRequest,
    db: DbSession,
    settings: AppSettings,
    provider: LLMProviderDep,
    clock: AppClock,
):
    return _module(db, settings, provider, clock).decide(proposal_id, payload)


@router.post(
    "/curriculum-proposals/{proposal_id}/publish",
    response_model=CurriculumPublishResult,
)
def publish_curriculum_proposal(
    proposal_id: str,
    payload: CurriculumPublishRequest,
    db: DbSession,
    settings: AppSettings,
    provider: LLMProviderDep,
    clock: AppClock,
):
    return _module(db, settings, provider, clock).publish(proposal_id, payload)
