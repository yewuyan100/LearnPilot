from datetime import datetime, timezone

from sqlalchemy import func, select

from app.models import KnowledgeMastery, ReviewSchedule, WrongAnswer


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class WeakPointService:
    def __init__(self, db, *, now: datetime | None = None):
        self.db = db
        self.now = now or datetime.now(timezone.utc)

    def facts(self, mastery: KnowledgeMastery) -> dict:
        active_wrong = self.db.scalar(select(func.count(WrongAnswer.id)).where(
            WrongAnswer.knowledge_point_id == mastery.knowledge_point_id,
            WrongAnswer.status == "active",
        )) or 0
        recent_failure = self.db.scalar(select(func.count(WrongAnswer.id)).where(
            WrongAnswer.knowledge_point_id == mastery.knowledge_point_id,
            WrongAnswer.status == "active",
            WrongAnswer.review_count > 0,
        )) or 0
        schedule = self.db.scalar(select(ReviewSchedule).where(
            ReviewSchedule.knowledge_point_id == mastery.knowledge_point_id,
            ReviewSchedule.status.in_(("pending", "scheduled")),
        ).order_by(ReviewSchedule.id.desc()))
        overdue = bool(schedule and aware(schedule.due_at) < aware(self.now))
        if mastery.mastery_score is None:
            weakness = None
            classification = "unassessed"
        else:
            failure_score = 100 if active_wrong or recent_failure else 0
            overdue_score = 100 if overdue else 0
            weakness = round(
                (100 - float(mastery.mastery_score)) * .50
                + (100 - float(mastery.confidence_score)) * .15
                + failure_score * .20 + overdue_score * .15,
                2,
            )
            classification = "weak"
        return {
            "classification": classification, "weakness_score": weakness,
            "active_wrong_answers": int(active_wrong), "recent_failure": bool(recent_failure or active_wrong),
            "overdue": overdue, "review_status": schedule.status if schedule else None,
            "schedule": schedule,
        }
