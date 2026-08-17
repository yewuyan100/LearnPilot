from datetime import timedelta, timezone
from uuid import uuid4

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.learning.agents.planning.schemas import (
    CurrentStudyPlanInput,
    MasteryChangeInput,
    PlanningAgentRequest,
    RecentMasteryEvidence,
)
from app.learning.context.module import LearnerContextModule
from app.learning.context.schemas import ContextQuery, SurfaceContext
from app.learning.planning.schemas import (
    PlanAdjustmentDecisionRequest,
    PlanAdjustmentProposalRead,
)
from app.learning.policies.plan_transition import PlanTransitionPolicy
from app.models.knowledge_point import KnowledgePoint
from app.models.learning_event import LearningEvent
from app.models.learning_proposal import LearningProposal
from app.models.mastery_evidence import MasteryEvidence
from app.models.study_plan import StudyPlan
from app.services.study_plans import StudyPlanService


class PlanAdjustmentModule:
    """Deep Event -> Proposal -> confirmed PlanVersion transition Module."""

    proposal_type = "plan_adjustment"

    def __init__(self, db, settings, agent, clock) -> None:
        self.db = db
        self.settings = settings
        self.agent = agent
        self.clock = clock

    @staticmethod
    def _utc(value):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def _proposal(self, public_id: str) -> LearningProposal:
        proposal = self.db.scalar(
            select(LearningProposal).where(
                LearningProposal.public_id == public_id,
                LearningProposal.proposal_type == self.proposal_type,
            )
        )
        if proposal is None:
            raise AppError(
                "plan_adjustment_not_found",
                "计划调整提案不存在。",
                status.HTTP_404_NOT_FOUND,
            )
        expires_at = self._utc(proposal.expires_at)
        if (
            proposal.status == "pending"
            and expires_at is not None
            and expires_at <= self.clock.now()
        ):
            proposal.status = "expired"
            proposal.version += 1
            self.db.commit()
            self.db.refresh(proposal)
        return proposal

    def _context(self, actor_key: str, course_id: int, knowledge_point_id: int):
        return LearnerContextModule(self.db, self.settings, self.clock).load(
            ContextQuery(
                actor_key=actor_key,
                surface_context=SurfaceContext(
                    course_id=course_id,
                    knowledge_point_id=knowledge_point_id,
                ),
            )
        )

    def consume_mastery_changed(
        self, event_id: str
    ) -> PlanAdjustmentProposalRead | None:
        event = self.db.get(LearningEvent, event_id)
        if event is None or event.event_type != "MasteryChanged":
            raise AppError(
                "mastery_changed_event_invalid",
                "只有 MasteryChanged 事件可以生成计划调整提案。",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        request_id = f"plan-adjustment:{event.event_id}"
        replay = self.db.scalar(
            select(LearningProposal).where(
                LearningProposal.generation_request_id == request_id
            )
        )
        if replay is not None:
            return self.serialize(replay)

        payload = event.payload or {}
        knowledge_point_id = int(payload["knowledge_point_id"])
        point = self.db.get(KnowledgePoint, knowledge_point_id)
        if point is None:
            return None
        context = self._context(event.actor_key, point.course_id, point.id)
        if context.study_plan is None or context.study_plan.active_version_number is None:
            return None
        evidence_ids = [int(item) for item in payload.get("evidence_ids") or []]
        evidence = list(
            self.db.scalars(
                select(MasteryEvidence)
                .where(MasteryEvidence.id.in_(evidence_ids))
                .order_by(MasteryEvidence.occurred_at.desc(), MasteryEvidence.id.desc())
            )
        )
        if not evidence or {item.id for item in evidence} != set(evidence_ids):
            return None
        change = MasteryChangeInput(
            knowledge_point_id=point.id,
            knowledge_point_title=point.title,
            old_level=str(payload["old_level"]),
            new_level=str(payload["new_level"]),
            confidence=float(payload["confidence"]),
            evidence_ids=evidence_ids,
        )
        draft = self.agent.propose(
            PlanningAgentRequest(
                learner_context=context,
                mastery_changes=[change],
                recent_evidence=[
                    RecentMasteryEvidence(
                        evidence_id=item.id,
                        evidence_type=item.evidence_type,
                        normalized_score=float(item.normalized_score),
                        occurred_at=item.occurred_at,
                    )
                    for item in evidence
                ],
                current_plan=CurrentStudyPlanInput(
                    study_plan_id=context.study_plan.id,
                    version=context.study_plan.version,
                    active_version_number=context.study_plan.active_version_number,
                    status=context.study_plan.status,
                ),
                goal_deadline=context.goal.target_date if context.goal else None,
            )
        )
        if draft is None:
            return None

        proposal = LearningProposal(
            public_id=str(uuid4()),
            proposal_type=self.proposal_type,
            status="pending",
            version=1,
            generation_request_id=request_id,
            source_event_id=event.event_id,
            target_type="study_plan",
            target_id=str(context.study_plan.id),
            context_version=context.context_version,
            summary={
                "actor_key": event.actor_key,
                "course_id": point.course_id,
                "knowledge_point_id": point.id,
                "mastery_change": change.model_dump(mode="json"),
                **draft.model_dump(mode="json"),
                "study_plan_version": context.study_plan.version,
                "active_plan_version": context.study_plan.active_version_number,
                "goal_deadline": (
                    context.goal.target_date.isoformat()
                    if context.goal and context.goal.target_date
                    else None
                ),
            },
            rationale=draft.reason,
            expires_at=self.clock.now() + timedelta(days=7),
        )
        self.db.add(proposal)
        try:
            self.db.commit()
            self.db.refresh(proposal)
        except IntegrityError:
            self.db.rollback()
            replay = self.db.scalar(
                select(LearningProposal).where(
                    LearningProposal.generation_request_id == request_id
                )
            )
            if replay is not None:
                return self.serialize(replay)
            raise

        stable_context = self._context(event.actor_key, point.course_id, point.id)
        proposal.context_version = stable_context.context_version
        self.db.commit()
        self.db.refresh(proposal)
        return self.serialize(proposal)

    def get(self, public_id: str) -> PlanAdjustmentProposalRead:
        return self.serialize(self._proposal(public_id))

    def list(self, proposal_status: str | None = None) -> list[PlanAdjustmentProposalRead]:
        query = select(LearningProposal).where(
            LearningProposal.proposal_type == self.proposal_type
        )
        if proposal_status is not None:
            query = query.where(LearningProposal.status == proposal_status)
        rows = list(
            self.db.scalars(query.order_by(LearningProposal.created_at.desc()))
        )
        return [self.serialize(self._proposal(row.public_id)) for row in rows]

    def decide(
        self,
        public_id: str,
        payload: PlanAdjustmentDecisionRequest,
    ) -> PlanAdjustmentProposalRead:
        proposal = self._proposal(public_id)
        if proposal.decision_request_id == payload.request_id:
            expected = "accepted" if payload.decision == "accept" else "rejected"
            if proposal.status != expected:
                raise AppError(
                    "plan_adjustment_decision_request_conflict",
                    "相同 request_id 已用于另一项决策。",
                    status.HTTP_409_CONFLICT,
                )
            if proposal.status == "accepted" and not (proposal.summary or {}).get(
                "application"
            ):
                return self._apply(proposal)
            return self.serialize(proposal)
        if proposal.version != payload.expected_version:
            raise AppError(
                "plan_adjustment_version_conflict",
                "计划调整提案已经变化，请刷新后重试。",
                status.HTTP_409_CONFLICT,
            )
        used = self.db.scalar(
            select(LearningProposal).where(
                LearningProposal.decision_request_id == payload.request_id,
                LearningProposal.id != proposal.id,
            )
        )
        if used is not None:
            raise AppError(
                "plan_adjustment_decision_request_conflict",
                "相同 request_id 已用于另一份提案。",
                status.HTTP_409_CONFLICT,
            )
        summary = proposal.summary or {}
        context = self._context(
            str(summary["actor_key"]),
            int(summary["course_id"]),
            int(summary["knowledge_point_id"]),
        )
        decision = PlanTransitionPolicy(self.db, self.clock).evaluate(
            proposal=proposal,
            context=context,
            expected_context_version=payload.context_version,
            confirmed=payload.confirmed,
        )
        if not decision.allowed:
            raise AppError(
                decision.code or "plan_adjustment_denied",
                decision.reason or "计划调整未通过策略检查。",
                status.HTTP_409_CONFLICT,
            )
        proposal.status = "accepted" if payload.decision == "accept" else "rejected"
        proposal.version += 1
        proposal.decision_request_id = payload.request_id
        proposal.decided_at = self.clock.now()
        self.db.commit()
        self.db.refresh(proposal)
        if proposal.status == "rejected":
            return self.serialize(proposal)
        return self._apply(proposal)

    def _apply(self, proposal: LearningProposal) -> PlanAdjustmentProposalRead:
        summary = dict(proposal.summary or {})
        if summary.get("application"):
            return self.serialize(proposal)
        result = StudyPlanService(
            self.db, self.settings, self.clock
        ).apply_plan_adjustment(
            int(proposal.target_id or 0),
            proposal_id=proposal.public_id,
            reason=str(summary["suggestion"]),
        )
        summary["application"] = {
            "new_plan_version": result.plan.current_version_number,
            "active_plan_version": result.plan.active_version_number,
            "created_task_ids": result.created_task_ids,
            "reused_task_ids": result.reused_task_ids,
            "rescheduled_task_ids": result.rescheduled_task_ids,
            "idempotent_replay": result.idempotent_replay,
        }
        proposal.summary = summary
        self.db.commit()
        self.db.refresh(proposal)
        return self.serialize(proposal)

    def serialize(self, proposal: LearningProposal) -> PlanAdjustmentProposalRead:
        summary = proposal.summary or {}
        plan = self.db.get(StudyPlan, int(proposal.target_id or 0))
        return PlanAdjustmentProposalRead(
            proposal_id=proposal.public_id,
            status=proposal.status,
            version=proposal.version,
            context_version=proposal.context_version or "0" * 64,
            source_event_id=proposal.source_event_id or "",
            study_plan_id=plan.id if plan else int(proposal.target_id or 0),
            study_plan_version=int(summary["study_plan_version"]),
            active_plan_version=int(summary["active_plan_version"]),
            reason=str(summary["reason"]),
            suggestion=str(summary["suggestion"]),
            impact=str(summary["impact"]),
            adjustment_kind=summary["adjustment_kind"],
            affected_items=summary["affected_items"],
            mastery_change=summary["mastery_change"],
            mastery_evidence_ids=[
                int(item) for item in summary.get("mastery_evidence_ids") or []
            ],
            application=summary.get("application"),
            expires_at=self._utc(proposal.expires_at),
            decided_at=self._utc(proposal.decided_at),
            created_at=self._utc(proposal.created_at),
            updated_at=self._utc(proposal.updated_at),
        )
