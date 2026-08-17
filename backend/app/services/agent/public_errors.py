from app.schemas.agent import AgentPublicError


def public_agent_error(internal_code: str | None) -> AgentPublicError:
    code = internal_code or "agent_execution_failed"
    if code in {
        "tool_arguments_invalid",
        "tool_not_allowed",
        "plan_too_many_steps",
        "tool_limit_exceeded",
        "read_after_write",
        "empty_plan",
    }:
        return AgentPublicError(
            code="agent_plan_invalid",
            safe_message="AI中心暂时无法理解这项请求，请换一种说法后重试。",
            retryable=True,
        )
    if code in {"llm_unavailable", "agent_execution_failed", "agent_resume_failed"}:
        return AgentPublicError(
            code="agent_temporarily_unavailable",
            safe_message="AI中心暂时无法完成这项请求，请稍后重试。",
            retryable=True,
        )
    if code == "grounded_answer_invalid":
        return AgentPublicError(
            code="agent_grounding_failed",
            safe_message="资料回答暂时无法可靠生成，请稍后重试。",
            retryable=True,
        )
    if code == "confirmation_expired":
        return AgentPublicError(
            code="agent_confirmation_expired",
            safe_message="本次确认已过期，请重新发起操作。",
            retryable=True,
        )
    return AgentPublicError(
        code="agent_action_failed",
        safe_message="这项操作没有完成，请检查输入后重试。",
        retryable=False,
    )
