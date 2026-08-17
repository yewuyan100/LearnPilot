from datetime import timezone

from sqlalchemy import select

from app.learning.policies.schemas import PolicyDecision
from app.models.course_architecture import KnowledgePointPrerequisite
from app.models.knowledge_point import KnowledgePoint
from app.models.learning_proposal import LearningProposal
from app.models.mastery_evidence import MasteryEvidence
from app.models.study_plan import StudyPlan, StudyPlanVersion


class PlanTransitionPolicy:
    """Validation seam between a pending suggestion and formal Plan mutation."""

    def __init__(self, db, clock) -> None:
        self.db = db
        self.clock = clock

    @staticmethod
    def _utc(value):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _deny(code: str, reason: str) -> PolicyDecision:
        return PolicyDecision(allowed=False, code=code, reason=reason)

    def evaluate(
        self,
        *,
        proposal: LearningProposal,
        context,
        expected_context_version: str,
        confirmed: bool,
    ) -> PolicyDecision:
        if not confirmed:
            return self._deny(
                "plan_adjustment_confirmation_required",
                "接受或拒绝计划调整前必须明确确认。",
            )
        if proposal.status != "pending":
            return self._deny(
                "plan_adjustment_not_pending",
                "只有待处理的计划调整提案可以决策。",
            )
        expires_at = self._utc(proposal.expires_at)
        if expires_at is not None and expires_at <= self.clock.now():
            return self._deny(
                "plan_adjustment_expired",
                "计划调整提案已经过期，请等待新的学习证据。",
            )
        if (
            proposal.context_version is None
            or proposal.context_version != expected_context_version
            or context.context_version != expected_context_version
        ):
            return self._deny(
                "plan_adjustment_context_conflict",
                "提案所依据的学习上下文已经变化，请刷新后重新审查。",
            )
        plan = self.db.get(StudyPlan, int(proposal.target_id or 0))
        if (
            plan is None
            or plan.status != "active"
            or plan.active_version_number is None
            or context.study_plan is None
            or context.study_plan.id != plan.id
        ):
            return self._deny(
                "plan_adjustment_plan_unavailable",
                "提案对应的正式学习计划已不可用。",
            )
        active_version = self.db.scalar(
            select(StudyPlanVersion).where(
                StudyPlanVersion.study_plan_id == plan.id,
                StudyPlanVersion.version_number == plan.active_version_number,
                StudyPlanVersion.status == "active",
            )
        )
        if active_version is None or active_version.stale_at is not None:
            return self._deny(
                "plan_adjustment_plan_stale",
                "正式学习计划已失效，不能在其上应用调整。",
            )

        summary = proposal.summary or {}
        affected_ids = {
            int(item["id"])
            for item in summary.get("affected_items") or []
            if item.get("kind") == "knowledge_point" and item.get("id")
        }
        points = list(
            self.db.scalars(select(KnowledgePoint).where(KnowledgePoint.id.in_(affected_ids)))
        )
        if (
            not affected_ids
            or {point.id for point in points} != affected_ids
            or any(
                point.course_id != plan.course_id or point.lifecycle_status != "active"
                for point in points
            )
        ):
            return self._deny(
                "plan_adjustment_prerequisite_invalid",
                "提案引用的知识点已失效或不属于当前正式课程。",
            )
        edges = list(
            self.db.scalars(
                select(KnowledgePointPrerequisite).where(
                    KnowledgePointPrerequisite.dependent_knowledge_point_id.in_(affected_ids)
                )
            )
        )
        prerequisite_ids = {edge.prerequisite_knowledge_point_id for edge in edges}
        if prerequisite_ids:
            prerequisites = list(
                self.db.scalars(
                    select(KnowledgePoint).where(KnowledgePoint.id.in_(prerequisite_ids))
                )
            )
            if {point.id for point in prerequisites} != prerequisite_ids or any(
                point.course_id != plan.course_id or point.lifecycle_status != "active"
                for point in prerequisites
            ):
                return self._deny(
                    "plan_adjustment_prerequisite_invalid",
                    "计划调整依赖的知识点前置关系已经失效。",
                )

        evidence_ids = {int(item) for item in summary.get("mastery_evidence_ids") or []}
        evidence = list(
            self.db.scalars(select(MasteryEvidence).where(MasteryEvidence.id.in_(evidence_ids)))
        )
        if (
            not evidence_ids
            or {item.id for item in evidence} != evidence_ids
            or any(item.knowledge_point_id not in affected_ids for item in evidence)
        ):
            return self._deny(
                "plan_adjustment_evidence_missing",
                "计划调整所依据的掌握度证据不存在或已不匹配。",
            )
        return PolicyDecision(allowed=True)
