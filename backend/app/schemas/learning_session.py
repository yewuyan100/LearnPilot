from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import DailyTaskStatus, KnowledgePointStatus, LearningSessionStatus
from app.schemas.common import Timestamped


class LearningSessionCreate(BaseModel):
    learning_goal_id: int = Field(gt=0)
    course_id: int | None = Field(default=None, gt=0)
    knowledge_point_id: int | None = Field(default=None, gt=0)
    daily_task_id: int | None = Field(default=None, gt=0)
    notes: str = Field(default="", max_length=20000)


class LearningSessionUpdate(BaseModel):
    status: LearningSessionStatus | None = None
    notes: str | None = Field(default=None, max_length=20000)
    ended_at: datetime | None = None
    knowledge_point_status: KnowledgePointStatus | None = None
    daily_task_status: DailyTaskStatus | None = None

    @model_validator(mode="after")
    def completed_session_has_end_time(self):
        if self.status == LearningSessionStatus.completed and self.ended_at is None:
            self.ended_at = datetime.now()
        return self


class LearningSessionRead(Timestamped):
    learning_goal_id: int
    course_id: int | None
    knowledge_point_id: int | None
    daily_task_id: int | None
    started_at: datetime
    ended_at: datetime | None
    status: str
    notes: str
    goal_title: str | None = None
    course_title: str | None = None
    knowledge_point_title: str | None = None
    task_title: str | None = None
