from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    conversation_id: int
    run_id: int
    thread_id: str
    request_id: str
    user_input: str
    history: list[dict[str, str]]
    current_time: str
    timezone: str
    intent: str
    confidence: float
    clarification_question: str | None
    entities: dict[str, Any]
    plan: list[dict[str, Any]]
    current_step: int
    completed_steps: list[int]
    pending_tool_name: str | None
    pending_tool_args: dict[str, Any] | None
    pending_tool_args_hash: str | None
    confirmation_id: int | None
    confirmation_decision: str | None
    tool_results: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    final_answer: str | None
    citations: list[dict[str, Any]]
    status: str
    failure_code: str | None
    step_count: int
    max_steps: int
