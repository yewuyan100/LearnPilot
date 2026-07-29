from datetime import date

from pydantic import BaseModel, Field

from app.models.enums import GoalStatus
from app.schemas.common import Timestamped


class LearningGoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    target_date: date | None = None
    daily_minutes: int = Field(default=30, ge=5, le=1440)
    current_level: str = Field(default="", max_length=200)
    status: GoalStatus = GoalStatus.active


class LearningGoalUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    target_date: date | None = None
    daily_minutes: int | None = Field(default=None, ge=5, le=1440)
    current_level: str | None = Field(default=None, max_length=200)
    status: GoalStatus | None = None


class LearningGoalRead(Timestamped):
    title: str
    description: str
    target_date: date | None
    daily_minutes: int
    current_level: str
    status: str
    is_demo: bool
