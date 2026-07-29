from enum import StrEnum


class GoalStatus(StrEnum):
    active = "active"
    paused = "paused"
    completed = "completed"
    archived = "archived"


class MaterialStatus(StrEnum):
    uploaded = "uploaded"
    ready = "ready"
    failed = "failed"


class IngestionStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class IndexingStatus(StrEnum):
    pending = "pending"
    indexing = "indexing"
    completed = "completed"
    failed = "failed"


class RagConversationStatus(StrEnum):
    active = "active"
    archived = "archived"


class RagMessageRole(StrEnum):
    user = "user"
    assistant = "assistant"


class RagMessageStatus(StrEnum):
    pending = "pending"
    completed = "completed"
    failed = "failed"


class CourseStatus(StrEnum):
    draft = "draft"
    active = "active"
    completed = "completed"
    archived = "archived"


class KnowledgePointStatus(StrEnum):
    not_started = "not_started"
    learning = "learning"
    completed = "completed"
    locked = "locked"


class DailyTaskStatus(StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    skipped = "skipped"


class LearningSessionStatus(StrEnum):
    active = "active"
    paused = "paused"
    completed = "completed"
    cancelled = "cancelled"
