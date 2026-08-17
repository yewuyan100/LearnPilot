from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StudyPlanCreateRequest(StrictModel):
    request_id: str = Field(min_length=8, max_length=100)
    learning_goal_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    start_date: date
    target_date: date
    daily_minutes: int = Field(gt=0, le=720)
    available_weekdays: list[int] = Field(min_length=1, max_length=7)
    allow_weekends: bool = False
    intensity: Literal["basic", "standard", "intensive"] = "standard"
    include_due_reviews: bool = True
    use_latest_diagnostic: bool = True
    use_existing_mastery: bool = True

    @model_validator(mode="after")
    def validate_dates_and_days(self) -> "StudyPlanCreateRequest":
        if self.target_date <= self.start_date:
            raise ValueError("截止日期必须晚于开始日期")
        if any(day < 0 or day > 6 for day in self.available_weekdays):
            raise ValueError("可学习日必须使用 0 到 6 表示周一到周日")
        if len(set(self.available_weekdays)) != len(self.available_weekdays):
            raise ValueError("可学习日不能重复")
        if not self.allow_weekends and any(day >= 5 for day in self.available_weekdays):
            raise ValueError("未允许周末学习时不能选择周六或周日")
        return self


class StudyPlanPublishRequest(StrictModel):
    request_id: str = Field(min_length=8, max_length=100)
    expected_version: int = Field(ge=1)
    confirmed: bool

    @model_validator(mode="after")
    def require_confirmation(self) -> "StudyPlanPublishRequest":
        if not self.confirmed:
            raise ValueError("必须明确确认计划")
        return self


class StudyPlanReplanRequest(StrictModel):
    request_id: str = Field(min_length=8, max_length=100)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=2000)
    start_date: date | None = None
    target_date: date | None = None
    daily_minutes: int | None = Field(default=None, gt=0, le=720)
    available_weekdays: list[int] | None = Field(default=None, min_length=1, max_length=7)
    allow_weekends: bool | None = None
    intensity: Literal["basic", "standard", "intensive"] | None = None
    include_due_reviews: bool | None = None
    use_latest_diagnostic: bool | None = None
    use_existing_mastery: bool | None = None

    @model_validator(mode="after")
    def validate_optional_days(self) -> "StudyPlanReplanRequest":
        if self.available_weekdays is not None:
            if any(day < 0 or day > 6 for day in self.available_weekdays):
                raise ValueError("可学习日必须使用 0 到 6")
            if len(set(self.available_weekdays)) != len(self.available_weekdays):
                raise ValueError("可学习日不能重复")
        return self


class StudyPlanCancelRequest(StrictModel):
    request_id: str = Field(min_length=8, max_length=100)
    expected_version: int = Field(ge=1)
    confirmed: bool

    @model_validator(mode="after")
    def require_confirmation(self) -> "StudyPlanCancelRequest":
        if not self.confirmed:
            raise ValueError("必须明确确认取消")
        return self


class StudyPlanItemRead(BaseModel):
    id: int
    scheduled_date: date
    order_index: int
    logical_key: str
    learning_goal_id: int
    course_id: int
    course_title: str
    knowledge_point_id: int | None
    knowledge_point_title: str | None
    lesson_id: int | None
    lesson_title: str | None
    title: str
    activity_type: str
    estimated_minutes: int
    scheduling_reason: str
    prerequisite_ids: list[int]
    is_due_review: bool
    review_schedule_id: int | None
    diagnostic_result_id: int | None
    daily_task_id: int | None
    task_status: str | None


class StudyPlanVersionRead(BaseModel):
    id: int
    version_number: int
    status: str
    generation_request_id: str | None
    replan_request_id: str | None
    publish_request_id: str | None
    parameters: dict
    diagnostic_session_id: int | None
    required_minutes: int
    available_minutes: int
    gap_minutes: int
    conflicts: list
    suggestions: list
    quality_report: dict
    reason: str
    published_at: datetime | None
    stale_at: datetime | None
    stale_reason: str | None
    stale_source_type: str | None
    stale_source_id: int | None
    created_at: datetime
    items: list[StudyPlanItemRead]


class StudyPlanRead(BaseModel):
    id: int
    public_id: str
    learning_goal_id: int
    learning_goal_title: str
    course_id: int
    course_title: str
    status: str
    version: int
    current_version_number: int
    active_version_number: int | None
    latest_version: StudyPlanVersionRead
    active_version: StudyPlanVersionRead | None
    created_at: datetime
    updated_at: datetime
    idempotent_replay: bool = False


class StudyPlanHistoryResponse(BaseModel):
    items: list[StudyPlanVersionRead]
    total: int


class StudyPlanPublishResult(BaseModel):
    plan: StudyPlanRead
    created_task_ids: list[int]
    reused_task_ids: list[int]
    rescheduled_task_ids: list[int]
    idempotent_replay: bool = False
