from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RagConversationCreate(BaseModel):
    title: str = Field(default="新建资料问答", min_length=1, max_length=255)
    default_top_k: int | None = Field(default=None, ge=1)


class RagConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: str
    default_top_k: int | None
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RagConversationPage(BaseModel):
    items: list[RagConversationRead]
    total: int
    page: int
    page_size: int
    pages: int


class RagCitationRead(BaseModel):
    id: int
    source_label: str
    chunk_id: int | None
    material_id: int | None
    rank: int
    score: float
    original_filename: str
    chunk_index: int
    page_number: int | None
    section_title: str | None
    content_excerpt: str
    source_available: bool
    learning_context: dict = {}
    created_at: datetime


class RagMessageRead(BaseModel):
    id: int
    conversation_id: int
    reply_to_message_id: int | None
    role: str
    content: str
    status: str
    request_id: str | None
    original_query: str | None
    retrieval_query: str | None
    retrieval_scope: dict = {}
    answerable: bool | None
    refusal_reason: str | None
    prompt_version: str | None
    model_name: str | None
    latency_ms: int | None
    created_at: datetime
    updated_at: datetime
    citations: list[RagCitationRead] = []


class RagConversationDetail(RagConversationRead):
    messages: list[RagMessageRead]
    message_total: int
    message_page: int
    message_page_size: int
    message_pages: int


class RagAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    request_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
    top_k: int | None = Field(default=None, ge=1)
    material_ids: list[int] | None = Field(default=None, max_length=100)
    learning_goal_id: int | None = Field(default=None, gt=0)
    course_id: int | None = Field(default=None, gt=0)
    knowledge_point_id: int | None = Field(default=None, gt=0)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("问题不能为空")
        return cleaned

    @field_validator("material_ids")
    @classmethod
    def unique_material_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if any(item <= 0 for item in value):
            raise ValueError("资料 ID 必须大于 0")
        return list(dict.fromkeys(value))


class RagRetrievalSummary(BaseModel):
    query: str
    top_k: int
    candidate_count: int
    source_count: int
    min_score: float
    index_version: str | None
    duration_ms: int
    requested_scope: dict = {}
    resolved_material_ids: list[int] | None = None
    retrieved_count: int = 0
    filtered_count: int = 0
    final_count: int = 0
    retrieval_mode: str = "dense_only"
    reranker_status: str = "disabled"
    reranker_device: str | None = None
    reranker_dtype: str | None = None
    reranker_batch_count: int = 0
    reranker_fallback_reason: str | None = None


class RagModelSummary(BaseModel):
    provider: str
    model: str | None
    fallback_used: bool


class RagAnswerResponse(BaseModel):
    conversation_id: int
    user_message: RagMessageRead
    assistant_message: RagMessageRead
    retrieval: RagRetrievalSummary
    model: RagModelSummary
    idempotent_replay: bool = False


class RagStatus(BaseModel):
    llm_configured: bool
    provider: str
    model: str | None
    index_available: bool
    index_stale: bool
    index_version: str | None
    rag_prompt_version: str
    rewrite_prompt_version: str
