from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.clock import clock_from_settings
from app.models import DailyTask, MasterySnapshot, ReviewSchedule, WrongAnswer
from app.services.adaptive_learning.enums import ACTIVE_SCHEDULE_STATUSES
from app.services.adaptive_learning.weak_points import WeakPointService, aware


class ReviewScheduler:
    def __init__(self, db, settings, *, now: datetime | None = None):
        self.db = db
        self.settings = settings
        self.now = now or clock_from_settings(settings).now()
        self.zone = ZoneInfo(settings.app_timezone)

    def _midnight_utc(self, value) -> datetime:
        return datetime.combine(value, time.min, tzinfo=self.zone).astimezone(timezone.utc)

    def schedule(self, mastery) -> tuple[ReviewSchedule | None, bool]:
        if mastery.mastery_score is None:
            return None, False
        current = self.db.scalar(select(ReviewSchedule).where(
            ReviewSchedule.knowledge_point_id == mastery.knowledge_point_id,
            ReviewSchedule.status.in_(ACTIVE_SCHEDULE_STATUSES),
        ).order_by(ReviewSchedule.id.desc()))
        if current and aware(current.due_at) < aware(self.now):
            mastery.next_review_at = current.due_at
            return current, False

        score = float(mastery.mastery_score)
        confidence = float(mastery.confidence_score)
        if score < 40:
            days, reason = self.settings.review_interval_beginner_days, "low_mastery"
        elif score < 60:
            days, reason = self.settings.review_interval_developing_days, "low_mastery"
        elif score < 80:
            days, reason = self.settings.review_interval_proficient_days, "low_mastery"
        elif confidence < 60:
            days, reason = self.settings.review_interval_proficient_days, "low_confidence"
        else:
            days, reason = self.settings.review_interval_strong_days, "confidence_decay"

        active_wrongs = self.db.scalars(select(WrongAnswer).where(
            WrongAnswer.knowledge_point_id == mastery.knowledge_point_id,
            WrongAnswer.status == "active",
        ).order_by(WrongAnswer.updated_at.desc())).all()
        latest_failed_review = next((row for row in active_wrongs if row.review_count > 0 and row.last_reviewed_at), None)
        anchor = mastery.last_evidence_at or mastery.calculated_at
        due_date = aware(anchor).astimezone(self.zone).date() + timedelta(days=days)
        if latest_failed_review:
            due_date = aware(latest_failed_review.last_reviewed_at).astimezone(self.zone).date() + timedelta(
                days=self.settings.review_failed_interval_days
            )
            reason = "recent_failure"
        elif active_wrongs:
            wrong_anchor = min(aware(row.created_at).astimezone(self.zone).date() for row in active_wrongs)
            wrong_due = wrong_anchor + timedelta(days=self.settings.review_unresolved_wrong_answer_days)
            if wrong_due <= due_date:
                due_date, reason = wrong_due, "wrong_answer_due"
        due_at = self._midnight_utc(due_date)
        existing_task = self.db.scalar(select(DailyTask).where(
            DailyTask.knowledge_point_id == mastery.knowledge_point_id,
            DailyTask.scheduled_date == due_date,
            DailyTask.status.in_(("pending", "in_progress")),
        ))
        if existing_task and current:
            current.status = "scheduled"
            current.completed_task_id = existing_task.id
            mastery.next_review_at = current.due_at
            return current, False

        weakness = WeakPointService(self.db, now=self.now).facts(mastery)["weakness_score"] or 0
        snapshot = self.db.scalar(select(MasterySnapshot).where(
            MasterySnapshot.knowledge_point_id == mastery.knowledge_point_id
        ).order_by(MasterySnapshot.calculated_at.desc(), MasterySnapshot.id.desc()))
        summary = {
            "low_mastery": f"当前掌握度为 {score:.0f}，建议在 {days} 天内复习。",
            "low_confidence": f"当前掌握度较高，但置信度仅 {confidence:.0f}，建议验证性复习。",
            "recent_failure": "最近一次复习再次出现错误，建议次日复习。",
            "wrong_answer_due": f"存在 {len(active_wrongs)} 条未解决错题，建议尽快复习。",
            "confidence_decay": "当前表现较强，按规则安排周期复习以补充近期证据。",
        }[reason]
        if current and aware(current.due_at) == due_at and current.reason_code == reason:
            current.priority_score = weakness
            current.reason_summary = summary
            mastery.next_review_at = current.due_at
            return current, False
        if current:
            current.status = "superseded"
            self.db.flush()
        schedule = ReviewSchedule(
            knowledge_point_id=mastery.knowledge_point_id, status="pending",
            priority_score=weakness, recommended_at=self.now, due_at=due_at,
            reason_code=reason, reason_summary=summary,
            source_snapshot_id=snapshot.id if snapshot else None,
        )
        self.db.add(schedule)
        self.db.flush()
        mastery.next_review_at = due_at
        return schedule, True

    def complete_for_task(self, task: DailyTask) -> bool:
        if task.status != "completed":
            return False
        schedule = self.db.scalar(select(ReviewSchedule).where(
            ReviewSchedule.completed_task_id == task.id,
            ReviewSchedule.status == "scheduled",
        ))
        if not schedule:
            return False
        schedule.status = "completed"
        schedule.completed_at = self.now
        return True
