from app.core.clock import Clock
from app.learning.events.schemas import EventRecordResult, LearningEventEnvelope
from app.models.learning_event import LearningEvent


class LearningEventRecorder:
    """Append-only local Event Module; V11B intentionally has no dispatcher."""

    def __init__(self, db, clock: Clock):
        self.db = db
        self.clock = clock

    def record(self, event: LearningEventEnvelope) -> EventRecordResult:
        existing = self.db.get(LearningEvent, event.event_id)
        if existing is not None:
            return EventRecordResult(event_id=event.event_id, recorded=False)
        row = LearningEvent(
            **event.model_dump(exclude={"occurred_at"}),
            occurred_at=event.occurred_at or self.clock.now(),
        )
        self.db.add(row)
        self.db.commit()
        return EventRecordResult(event_id=row.event_id, recorded=True)
