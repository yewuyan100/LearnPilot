from fastapi import APIRouter, Query

from app.api.deps import AppClock, AppSettings, DbSession
from app.learning.agents.planning import PlanningAgent
from app.learning.planning import (
    PlanAdjustmentDecisionRequest,
    PlanAdjustmentModule,
    PlanAdjustmentProposalRead,
)


router = APIRouter(prefix="/plan-adjustments", tags=["plan adjustments"])


def service(db, settings, clock) -> PlanAdjustmentModule:
    return PlanAdjustmentModule(db, settings, PlanningAgent(), clock)


@router.get("", response_model=list[PlanAdjustmentProposalRead])
def list_plan_adjustments(
    db: DbSession,
    settings: AppSettings,
    clock: AppClock,
    proposal_status: str | None = Query(default=None, alias="status"),
) -> list[PlanAdjustmentProposalRead]:
    return service(db, settings, clock).list(proposal_status)


@router.get("/{proposal_id}", response_model=PlanAdjustmentProposalRead)
def get_plan_adjustment(
    proposal_id: str,
    db: DbSession,
    settings: AppSettings,
    clock: AppClock,
) -> PlanAdjustmentProposalRead:
    return service(db, settings, clock).get(proposal_id)


@router.post("/{proposal_id}/decision", response_model=PlanAdjustmentProposalRead)
def decide_plan_adjustment(
    proposal_id: str,
    payload: PlanAdjustmentDecisionRequest,
    db: DbSession,
    settings: AppSettings,
    clock: AppClock,
) -> PlanAdjustmentProposalRead:
    return service(db, settings, clock).decide(proposal_id, payload)
