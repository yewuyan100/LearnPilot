from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentConversationCreate(StrictModel):
    title: str = Field(default="新建学习助手会话", min_length=1, max_length=200)


class AgentRunCreate(StrictModel):
    input: str = Field(min_length=1, max_length=4000)
    request_id: str = Field(min_length=8, max_length=64)


class AgentConfirmRequest(StrictModel):
    decision: Literal["approve", "reject"]


class AgentCitation(BaseModel):
    source_label: str
    material_id: int | None = None
    chunk_id: int | None = None
    original_filename: str
    page_number: int | None = None
    section_title: str | None = None
    content_excerpt: str


class AgentMessageRead(BaseModel):
    id: int
    role: str
    content: str
    citations: list[dict]
    run_id: int | None
    created_at: datetime


class AgentConversationRead(BaseModel):
    id: int
    title: str
    status: str
    thread_id: str
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AgentConversationDetail(AgentConversationRead):
    messages: list[AgentMessageRead]


class AgentConfirmationRead(BaseModel):
    id: int
    summary: str
    tool_name: str
    arguments: dict[str, Any]
    status: str
    expires_at: datetime


class AgentToolCallRead(BaseModel):
    id: int
    step_index: int
    tool_name: str
    tool_kind: str
    arguments: dict[str, Any]
    status: str
    result: dict[str, Any] | None
    duration_ms: int | None


class AgentRunRead(BaseModel):
    id: int
    conversation_id: int
    request_id: str
    input: str
    status: str
    intent: str | None
    final_answer: str | None
    citations: list[dict]
    error_code: str | None
    idempotent_replay: bool = False
    confirmation: AgentConfirmationRead | None = None
    tool_calls: list[AgentToolCallRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AgentStatusRead(BaseModel):
    enabled: bool
    checkpoint_enabled: bool
    llm_configured: bool
    model: str | None
    max_steps: int
    read_tools: list[str]
    write_tools: list[str]


class IntentClassification(StrictModel):
    intent: Literal[
        "answer_materials", "search_materials", "list_courses", "list_knowledge_points",
        "list_daily_tasks", "get_learning_progress", "list_learning_activities",
        "get_activity_summary", "list_quiz_attempts", "get_wrong_answers",
        "create_daily_task", "update_daily_task_status", "save_learning_note",
        "generate_learning_activity", "create_wrong_answer_review", "start_quiz_attempt",
        "compound", "clarification", "unsupported"
    ]
    confidence: float = Field(ge=0, le=1)
    clarification_question: str | None = Field(default=None, max_length=500)
    entities: dict[str, Any] = Field(default_factory=dict)


class PlannedTool(StrictModel):
    tool_name: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentPlan(StrictModel):
    steps: list[PlannedTool] = Field(default_factory=list, max_length=4)
    response_hint: str = Field(default="", max_length=500)


class AgentResponseDraft(StrictModel):
    answer: str = Field(min_length=1, max_length=8000)
