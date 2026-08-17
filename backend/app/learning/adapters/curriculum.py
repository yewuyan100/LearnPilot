from app.learning.adapters.schemas import CurriculumExecutionResult
from app.learning.curriculum.schemas import CurriculumGenerateRequest


class CurriculumAdapter:
    """Harness adapter for the Goal-aware Curriculum Module."""

    def __init__(self, curriculum_module) -> None:
        self.curriculum_module = curriculum_module

    def execute(
        self,
        *,
        learner_context,
        user_input: str,
        request_id: str,
        harness_run_id: int,
    ) -> CurriculumExecutionResult:
        proposal = self.curriculum_module.generate(
            learner_context,
            CurriculumGenerateRequest(
                request_id=request_id,
                actor_key=learner_context.actor_key,
                instruction=user_input,
            ),
            source_harness_run_id=harness_run_id,
        )
        return CurriculumExecutionResult(
            answer="学习路径提案已生成，请审查知识点、前置关系和课节蓝图后再接受与发布。",
            proposal=self.curriculum_module.envelope(proposal),
        )
