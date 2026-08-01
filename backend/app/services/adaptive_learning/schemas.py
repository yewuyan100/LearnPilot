from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SelfAssessmentRequest(StrictModel):
    rating: int = Field(ge=1, le=5)
    request_id: str = Field(min_length=8, max_length=64)


class RebuildRequest(StrictModel):
    course_id: int | None = Field(default=None, gt=0)
    knowledge_point_id: int | None = Field(default=None, gt=0)


class RecommendationDecisionRequest(StrictModel):
    request_id: str = Field(min_length=8, max_length=64)
    confirmed: bool = False


class EvidenceRead(BaseModel):
    id: int
    evidence_type: str
    source_type: str
    source_id: str
    occurred_at: datetime
    normalized_score: float
    weight: float
    metadata: dict[str, Any]


class SnapshotRead(BaseModel):
    id: int
    mastery_score: float | None
    confidence_score: float
    mastery_level: str
    evidence_count: int
    trigger_type: str
    calculated_at: datetime


class ScheduleRead(BaseModel):
    id: int
    knowledge_point_id: int
    knowledge_point_title: str
    status: str
    priority_score: float
    recommended_at: datetime
    due_at: datetime
    overdue: bool
    reason_code: str
    reason_summary: str
    completed_task_id: int | None


class RecommendationRead(BaseModel):
    id: int
    knowledge_point_id: int
    recommendation_type: str
    status: str
    priority: str
    title: str
    reason_code: str
    reason_details: dict[str, Any]
    suggested_date: date
    suggested_minutes: int
    created_task_id: int | None


class MasteryListItem(BaseModel):
    knowledge_point_id: int
    knowledge_point_title: str
    course_id: int
    course_title: str
    mastery_score: float | None
    confidence_score: float
    mastery_level: str
    evidence_count: int
    active_wrong_answers: int
    last_practiced_at: datetime | None
    next_review_at: datetime | None


class MasteryPage(BaseModel):
    items: list[MasteryListItem]
    total: int
    page: int
    page_size: int
    pages: int


class MasteryDetail(MasteryListItem):
    algorithm_version: str
    calculated_at: datetime
    evidence_summary: dict[str, Any]
    evidence: list[EvidenceRead]
    snapshots: list[SnapshotRead]
    review_schedule: ScheduleRead | None
    recommendation: RecommendationRead | None


class WeakPointRead(MasteryListItem):
    classification: str
    weakness_score: float | None
    recent_failure: bool
    overdue: bool
    review_status: str | None


class RebuildResult(BaseModel):
    processed: int
    evidence_created: int
    snapshots_created: int
    schedules_created: int
    recommendations_created: int
    failures: list[dict[str, Any]]
