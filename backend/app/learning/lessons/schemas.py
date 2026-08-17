from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LessonCreate(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    order_index: int | None = Field(default=None, ge=1)


class LessonGenerateRequest(StrictModel):
    request_id: str = Field(min_length=8, max_length=100)
    knowledge_point_ids: list[int] = Field(min_length=1, max_length=12)
    primary_knowledge_point_id: int | None = Field(default=None, gt=0)
    target_minutes: int = Field(default=30, ge=5, le=240)

    @model_validator(mode="after")
    def validate_point_ids(self):
        if any(point_id <= 0 for point_id in self.knowledge_point_ids):
            raise ValueError("knowledge_point_ids must be positive")
        if len(set(self.knowledge_point_ids)) != len(self.knowledge_point_ids):
            raise ValueError("knowledge_point_ids cannot contain duplicates")
        if (
            self.primary_knowledge_point_id is not None
            and self.primary_knowledge_point_id not in self.knowledge_point_ids
        ):
            raise ValueError("primary_knowledge_point_id must be selected")
        return self


class LessonPublishRequest(StrictModel):
    expected_version_number: int = Field(ge=1)
    confirmed: bool

    @model_validator(mode="after")
    def require_confirmation(self):
        if not self.confirmed:
            raise ValueError("Lesson publishing requires explicit confirmation")
        return self


class LessonArchiveRequest(StrictModel):
    confirmed: bool

    @model_validator(mode="after")
    def require_confirmation(self):
        if not self.confirmed:
            raise ValueError("Lesson archival requires explicit confirmation")
        return self


class LessonKnowledgePointRead(BaseModel):
    knowledge_point_id: int
    title: str
    order_index: int
    role: str


class LessonSourceRead(BaseModel):
    material_id: int
    material_title: str
    material_chunk_id: int | None
    source_role: str
    source_locator: str
    quoted_text: str


class LessonVersionRead(BaseModel):
    id: int
    lesson_id: int
    version_number: int
    status: str
    objectives: list[str]
    content_markdown: str
    examples: list[dict]
    guided_practice: list[dict]
    checks: list[dict]
    estimated_minutes: int
    source_snapshot_hash: str
    generation_request_id: str
    model_name: str
    prompt_version: str
    quality_report: dict
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    knowledge_points: list[LessonKnowledgePointRead]
    sources: list[LessonSourceRead]


class LessonRead(BaseModel):
    id: int
    public_id: str
    course_id: int
    course_title: str
    learning_goal_id: int
    title: str
    description: str
    order_index: int
    status: str
    current_version_number: int
    active_version_number: int | None
    created_at: datetime
    updated_at: datetime
    latest_version: LessonVersionRead | None
    active_version: LessonVersionRead | None
    idempotent_replay: bool = False
