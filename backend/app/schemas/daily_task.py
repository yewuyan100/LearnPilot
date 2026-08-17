from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import DailyTaskStatus
from app.schemas.common import Timestamped


class DailyTaskCreate(BaseModel):
    learning_goal_id: int = Field(gt=0)
    course_id: int | None = Field(default=None, gt=0)
    knowledge_point_id: int | None = Field(default=None, gt=0)
    activity_id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=200)
    task_type: str = Field(default="learning", max_length=32)
    estimated_minutes: int = Field(default=20, ge=1, le=1440)
    scheduled_date: date
    status: DailyTaskStatus = DailyTaskStatus.pending


class DailyTaskUpdate(BaseModel):
    activity_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    task_type: str | None = Field(default=None, max_length=32)
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)
    scheduled_date: date | None = None
    status: DailyTaskStatus | None = None


class DailyTaskRead(Timestamped):
    learning_goal_id: int
    course_id: int | None
    knowledge_point_id: int | None
    activity_id: int | None
    title: str
    task_type: str
    estimated_minutes: int
    scheduled_date: date
    status: str
    blocked_at: datetime | None
    blocked_reason: str | None
    blocked_source_type: str | None
    blocked_source_id: int | None


class TodayResponse(BaseModel):
    date: date
    current_goal: dict | None
    tasks: list[DailyTaskRead]
    pending_count: int
    blocked_count: int = 0
    recent_course: dict | None
    recent_session: dict | None
