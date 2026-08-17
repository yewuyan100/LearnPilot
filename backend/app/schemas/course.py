from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import CourseStatus, KnowledgePointStatus
from app.schemas.common import Timestamped


class CourseCreate(BaseModel):
    learning_goal_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    status: CourseStatus = CourseStatus.draft


class CourseUpdate(BaseModel):
    learning_goal_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: CourseStatus | None = None


class CourseRead(Timestamped):
    learning_goal_id: int
    title: str
    description: str
    status: str
    knowledge_point_count: int = 0
    learning_goal_title: str | None = None


class KnowledgePointCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    order_index: int = Field(default=0, ge=0)
    estimated_minutes: int = Field(default=20, ge=1, le=1440)
    status: KnowledgePointStatus = KnowledgePointStatus.not_started


class KnowledgePointUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    order_index: int | None = Field(default=None, ge=0)
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)
    status: KnowledgePointStatus | None = None


class KnowledgePointRead(Timestamped):
    course_id: int
    title: str
    description: str
    order_index: int
    estimated_minutes: int
    status: str
    lifecycle_status: str
    superseded_by_id: int | None
    lifecycle_reason: str | None
    archived_at: datetime | None
    version: int
