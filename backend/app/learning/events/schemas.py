from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LearningEventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    event_type: str = Field(min_length=1, max_length=100)
    schema_version: int = Field(default=1, ge=1)
    actor_key: str = Field(min_length=1, max_length=200)
    aggregate_type: str = Field(min_length=1, max_length=64)
    aggregate_id: str = Field(min_length=1, max_length=100)
    correlation_id: str | None = Field(default=None, max_length=100)
    causation_id: str | None = Field(default=None, max_length=100)
    harness_run_id: int | None = None
    payload: dict = Field(default_factory=dict)
    occurred_at: datetime | None = None
    published_at: datetime | None = None


class EventRecordResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    recorded: bool
