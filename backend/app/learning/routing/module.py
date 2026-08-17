from app.learning.context.schemas import SurfaceContext
from app.learning.routing.schemas import RouteDecision, RoutingRequest, UserIntent


class AgentRouter:
    """Deterministic routing for Curriculum, Tutor, and Operations capabilities."""

    _curriculum_signals = (
        "learning path",
        "curriculum",
        "study plan for",
        "learn ",
        "学习路径",
        "课程路径",
        "学习路线",
        "课程规划",
        "我要学习",
        "我想学习",
        "规划学习",
    )
    _learning_question_signals = (
        "explain ",
        "why ",
        "how does ",
        "what is ",
        "解释",
        "为什么",
        "怎么理解",
        "是什么",
        "举例",
    )

    _operation_signals = (
        "create ",
        "add ",
        "delete ",
        "remove ",
        "update ",
        "edit ",
        "archive ",
        "list ",
        "show ",
        "complete ",
        "pause ",
        "resume ",
        "创建",
        "新增",
        "添加",
        "删除",
        "移除",
        "修改",
        "更新",
        "归档",
        "列出",
        "查看",
        "显示",
        "查询",
        "安排",
        "完成任务",
        "暂停会话",
        "继续会话",
        "结束会话",
        "保存笔记",
        "改成",
        "有什么任务",
    )

    def classify_user_intent(
        self, text: str, routing_context: SurfaceContext
    ) -> UserIntent:
        normalized = " ".join(text.lower().split())
        if any(signal in normalized for signal in self._curriculum_signals):
            return "curriculum"
        if any(signal in normalized for signal in self._operation_signals):
            return "operation"
        if any(signal in normalized for signal in self._learning_question_signals):
            return "learning_question"
        has_learning_surface = any(
            (
                routing_context.course_id,
                routing_context.knowledge_point_id,
                routing_context.learning_session_id,
            )
        )
        if has_learning_surface:
            return "learning_question"
        return "operation"

    def route(self, routing_request: RoutingRequest) -> RouteDecision:
        if routing_request.user_intent == "curriculum":
            return RouteDecision(
                selected_agent="curriculum",
                adapter_key="curriculum_agent",
                reason_code="goal_curriculum_request",
            )
        if routing_request.user_intent == "learning_question":
            return RouteDecision(
                selected_agent="tutor",
                adapter_key="tutor_agent",
                reason_code="contextual_learning_question",
            )
        return RouteDecision(
            selected_agent="operations",
            adapter_key="operations_agent",
            reason_code="learning_operation_or_unscoped_request",
        )
