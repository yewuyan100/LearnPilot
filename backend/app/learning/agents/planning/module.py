from app.learning.agents.planning.prompts import (
    PLANNING_PROMPT_VERSION,
    adjustment_reason,
)
from app.learning.agents.planning.schemas import (
    AffectedPlanItem,
    PlanAdjustmentProposal,
    PlanningAgentRequest,
)


class PlanningAgent:
    """Deterministic explanation Module with no Plan or Task write authority."""

    prompt_version = PLANNING_PROMPT_VERSION
    adjustable_levels = {"beginner", "developing"}

    def propose(
        self, request: PlanningAgentRequest
    ) -> PlanAdjustmentProposal | None:
        change = request.mastery_changes[-1]
        if change.new_level not in self.adjustable_levels:
            return None
        deadline = (
            f"，并继续以 {request.goal_deadline.isoformat()} 为目标检查可行性"
            if request.goal_deadline is not None
            else ""
        )
        return PlanAdjustmentProposal(
            reason=adjustment_reason(change, len(request.recent_evidence)),
            suggestion=f"在正式计划中为《{change.knowledge_point_title}》增加一次复习。",
            impact=(
                "接受后，确定性调度器会按现有时间预算、冲突和前置条件生成并发布一个新计划版本"
                f"{deadline}；确认前现有计划和每日任务保持不变。"
            ),
            affected_items=[
                AffectedPlanItem(
                    id=change.knowledge_point_id,
                    title=change.knowledge_point_title,
                )
            ],
            mastery_evidence_ids=change.evidence_ids,
        )
