from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import ORMModel, Timestamped


DraftStatus = Literal[
    "draft", "generating", "review_required", "ready", "publishing", "published", "failed", "archived"
]
SourceRole = Literal["primary", "supporting", "example", "prerequisite_context"]


class VersionedWrite(BaseModel):
    version: int = Field(ge=1)


class CourseArchitectureDraftCreate(BaseModel):
    learning_goal_id: int = Field(gt=0)
    material_ids: list[int] = Field(min_length=1, max_length=10)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)

    @field_validator("material_ids")
    @classmethod
    def unique_materials(cls, value: list[int]) -> list[int]:
        if any(item <= 0 for item in value):
            raise ValueError("material_ids must be positive")
        if len(set(value)) != len(value):
            raise ValueError("material_ids must be unique")
        return value


class CourseArchitectureDraftUpdate(VersionedWrite):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class DraftMaterialsReplace(VersionedWrite):
    material_ids: list[int] = Field(min_length=1, max_length=10)

    @field_validator("material_ids")
    @classmethod
    def unique_materials(cls, value: list[int]) -> list[int]:
        if any(item <= 0 for item in value) or len(set(value)) != len(value):
            raise ValueError("material_ids must contain unique positive IDs")
        return value


class DraftCourseCreate(VersionedWrite):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    order_index: int = Field(default=0, ge=0)
    learning_outcomes: list[str] = Field(default_factory=list, max_length=20)


class DraftCourseUpdate(VersionedWrite):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    learning_outcomes: list[str] | None = Field(default=None, max_length=20)
    is_locked: bool | None = None


class ReorderItem(BaseModel):
    id: int = Field(gt=0)
    order_index: int = Field(ge=0)


class DraftReorder(VersionedWrite):
    items: list[ReorderItem] = Field(min_length=1, max_length=200)


class DraftKnowledgePointCreate(VersionedWrite):
    draft_course_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    order_index: int = Field(default=0, ge=0)
    learning_objectives: list[str] = Field(default_factory=list, max_length=20)
    key_terms: list[str] = Field(default_factory=list, max_length=30)
    granularity_label: str | None = Field(default=None, max_length=40)
    difficulty_label: str | None = Field(default=None, max_length=40)


class DraftKnowledgePointUpdate(VersionedWrite):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    learning_objectives: list[str] | None = Field(default=None, max_length=20)
    key_terms: list[str] | None = Field(default=None, max_length=30)
    granularity_label: str | None = Field(default=None, max_length=40)
    difficulty_label: str | None = Field(default=None, max_length=40)
    is_locked: bool | None = None


class DraftKnowledgePointMove(VersionedWrite):
    knowledge_point_id: int = Field(gt=0)
    target_course_id: int = Field(gt=0)
    order_index: int = Field(ge=0)


class DraftKnowledgePointMerge(VersionedWrite):
    keep_knowledge_point_id: int = Field(gt=0)
    merge_knowledge_point_ids: list[int] = Field(min_length=1, max_length=20)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class DraftSourceCreate(VersionedWrite):
    material_id: int = Field(gt=0)
    material_chunk_id: int = Field(gt=0)
    source_role: SourceRole = "primary"
    source_locator: str | None = Field(default=None, max_length=500)
    quoted_text: str | None = Field(default=None, max_length=2000)
    relevance_score: float | None = Field(default=None, ge=0, le=1)


class DraftPrerequisiteCreate(VersionedWrite):
    prerequisite_knowledge_point_id: int = Field(gt=0)
    dependent_knowledge_point_id: int = Field(gt=0)
    rationale: str | None = Field(default=None, max_length=2000)
    confidence: float | None = Field(default=None, ge=0, le=1)


class DraftGenerationRequest(VersionedWrite):
    request_id: str = Field(min_length=8, max_length=100)


class DraftPublishRequest(VersionedWrite):
    publish_request_id: str = Field(min_length=8, max_length=100)
    confirmed: bool


class DraftMaterialRead(Timestamped):
    draft_id: int
    material_id: int
    material_title: str
    original_filename: str
    order_index: int
    material_updated_at_snapshot: datetime
    chunk_count_snapshot: int
    index_state_snapshot: str
    current_chunk_count: int
    current_indexing_status: str
    stale: bool


class DraftSourceRead(Timestamped):
    draft_knowledge_point_id: int
    material_id: int
    material_title: str
    material_chunk_id: int
    chunk_index: int
    source_locator: str | None
    quoted_text: str | None
    source_role: str
    relevance_score: float | None
    origin: str
    context_url: str


class DraftKnowledgePointRead(Timestamped):
    draft_course_id: int
    title: str
    description: str
    order_index: int
    learning_objectives: list[str]
    key_terms: list[str]
    granularity_label: str | None
    difficulty_label: str | None
    origin: str
    is_locked: bool
    user_modified: bool
    source_status: str
    validation_status: str
    published_knowledge_point_id: int | None
    sources: list[DraftSourceRead] = Field(default_factory=list)


class DraftCourseRead(Timestamped):
    draft_id: int
    title: str
    description: str
    order_index: int
    learning_outcomes: list[str]
    origin: str
    is_locked: bool
    user_modified: bool
    published_course_id: int | None
    knowledge_points: list[DraftKnowledgePointRead] = Field(default_factory=list)


class DraftPrerequisiteRead(Timestamped):
    draft_id: int
    prerequisite_knowledge_point_id: int
    prerequisite_title: str
    dependent_knowledge_point_id: int
    dependent_title: str
    rationale: str | None
    confidence: float | None
    origin: str
    validation_status: str


class QualityIssue(BaseModel):
    code: str
    severity: Literal["blocker", "warning", "info"]
    message: str
    course_id: int | None = None
    knowledge_point_id: int | None = None


class CourseArchitectureQualityReport(BaseModel):
    status: Literal["blocked", "ready", "stale"]
    blocker_count: int
    warning_count: int
    info_count: int
    source_coverage: float
    issues: list[QualityIssue]


class DraftRead(Timestamped):
    public_id: str
    learning_goal_id: int
    learning_goal_title: str
    title: str
    description: str
    status: DraftStatus
    generation_status: str
    version: int
    source_snapshot_version: int
    generation_mode: str
    model_name: str | None
    prompt_version: str | None
    generation_progress: dict
    last_error_code: str | None
    last_error_message: str | None
    quality_status: str
    quality_report: dict
    publish_request_id: str | None
    published_at: datetime | None
    archived_at: datetime | None
    materials: list[DraftMaterialRead] = Field(default_factory=list)
    courses: list[DraftCourseRead] = Field(default_factory=list)
    prerequisites: list[DraftPrerequisiteRead] = Field(default_factory=list)


class DraftListItem(Timestamped):
    public_id: str
    learning_goal_id: int
    learning_goal_title: str
    title: str
    status: DraftStatus
    generation_status: str
    version: int
    quality_status: str
    material_count: int
    course_count: int
    knowledge_point_count: int


class DraftListResponse(BaseModel):
    items: list[DraftListItem]
    total: int


class PublishResult(BaseModel):
    draft_id: int
    publish_request_id: str
    course_ids: list[int]
    knowledge_point_ids: list[int]
    material_link_count: int
    source_count: int
    prerequisite_count: int
    published_at: datetime


class ArchitectureImportKnowledgePoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    learning_objectives: list[str] = Field(default_factory=list, max_length=20)
    key_terms: list[str] = Field(default_factory=list, max_length=30)
    difficulty_label: str | None = Field(default=None, max_length=40)
    source_chunk_ids: list[int] = Field(default_factory=list, max_length=6)


class ArchitectureImportCourse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    learning_outcomes: list[str] = Field(default_factory=list, max_length=20)
    knowledge_points: list[ArchitectureImportKnowledgePoint] = Field(min_length=1, max_length=80)


class ArchitectureImportPrerequisite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prerequisite_title: str = Field(min_length=1, max_length=200)
    dependent_title: str = Field(min_length=1, max_length=200)
    rationale: str = Field(default="", max_length=2000)
    confidence: float = Field(default=0.8, ge=0, le=1)


class CourseArchitectureImport(BaseModel):
    """Stable aggregate import seam used by reviewed proposal sources."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    learning_goal_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    material_ids: list[int] = Field(default_factory=list, max_length=10)
    generation_mode: Literal["curriculum_goal_only", "curriculum_source_grounded"]
    generation_request_id: str = Field(min_length=8, max_length=100)
    model_name: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=100)
    courses: list[ArchitectureImportCourse] = Field(min_length=1, max_length=8)
    prerequisites: list[ArchitectureImportPrerequisite] = Field(default_factory=list, max_length=100)


# Provider-facing structured output. Extra fields are rejected so model drift is visible.
class KnowledgePointCandidateOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    learning_objectives: list[str] = Field(default_factory=list, max_length=10)
    key_terms: list[str] = Field(default_factory=list, max_length=15)
    difficulty_label: str | None = Field(default=None, max_length=40)
    source_chunk_ids: list[int] = Field(min_length=1, max_length=6)
    prerequisite_titles: list[str] = Field(default_factory=list, max_length=10)


class CourseCandidateOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    learning_outcomes: list[str] = Field(default_factory=list, max_length=10)
    knowledge_points: list[KnowledgePointCandidateOutput] = Field(min_length=1, max_length=30)


class PrerequisiteCandidateOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prerequisite_title: str = Field(min_length=1, max_length=200)
    dependent_title: str = Field(min_length=1, max_length=200)
    rationale: str = Field(default="", max_length=1000)
    confidence: float = Field(ge=0, le=1)


class MaterialSectionAnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section_summary: str = Field(max_length=2000)
    courses: list[CourseCandidateOutput] = Field(min_length=1, max_length=6)
    prerequisites: list[PrerequisiteCandidateOutput] = Field(default_factory=list, max_length=40)
    unresolved_issues: list[str] = Field(default_factory=list, max_length=20)


class CourseArchitectureGenerationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    courses: list[CourseCandidateOutput] = Field(min_length=1, max_length=12)
    prerequisites: list[PrerequisiteCandidateOutput] = Field(default_factory=list, max_length=100)
