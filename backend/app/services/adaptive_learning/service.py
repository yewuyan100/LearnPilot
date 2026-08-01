from datetime import date, datetime, timezone
from math import ceil
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.core.errors import AppError
from app.models import (
    AdaptiveRecommendation, Course, KnowledgeMastery, KnowledgePoint,
    MasteryEvidence, MasterySnapshot, ReviewSchedule, WrongAnswer,
)
from app.services.adaptive_learning.evidence_collector import LearningEvidenceCollector
from app.services.adaptive_learning.lifecycle import refresh_adaptive_learning
from app.services.adaptive_learning.recommendations import AdaptiveRecommendationService
from app.services.adaptive_learning.schemas import (
    EvidenceRead, MasteryDetail, MasteryListItem, MasteryPage,
    RecommendationRead, RebuildResult, ScheduleRead, SnapshotRead, WeakPointRead,
)
from app.services.adaptive_learning.weak_points import WeakPointService, aware


class AdaptiveLearningService:
    def __init__(self, db, settings, *, now: datetime | None = None):
        self.db = db
        self.settings = settings
        self.now = now or settings.adaptive_fixed_now or datetime.now(timezone.utc)
        self.zone = ZoneInfo(settings.app_timezone)

    def _ensure_current(self, point_id: int) -> KnowledgeMastery:
        mastery = self.db.scalar(select(KnowledgeMastery).where(
            KnowledgeMastery.knowledge_point_id == point_id
        ))
        if mastery:
            return mastery
        result = refresh_adaptive_learning(
            self.db, self.settings, point_id, trigger_type="manual_rebuild", now=self.now
        )
        mastery = self.db.scalar(select(KnowledgeMastery).where(
            KnowledgeMastery.knowledge_point_id == point_id
        ))
        if not mastery:
            raise AppError("mastery_calculation_failed", "掌握度状态创建失败", 500, result)
        return mastery

    def _active_wrong_count(self, point_id: int) -> int:
        return int(self.db.scalar(select(func.count(WrongAnswer.id)).where(
            WrongAnswer.knowledge_point_id == point_id,
            WrongAnswer.status == "active",
        )) or 0)

    def _item(self, point: KnowledgePoint, course: Course, mastery: KnowledgeMastery) -> MasteryListItem:
        return MasteryListItem(
            knowledge_point_id=point.id, knowledge_point_title=point.title,
            course_id=course.id, course_title=course.title,
            mastery_score=float(mastery.mastery_score) if mastery.mastery_score is not None else None,
            confidence_score=float(mastery.confidence_score), mastery_level=mastery.mastery_level,
            evidence_count=mastery.evidence_count, active_wrong_answers=self._active_wrong_count(point.id),
            last_practiced_at=mastery.last_practiced_at, next_review_at=mastery.next_review_at,
        )

    def list_mastery(self, *, course_id=None, mastery_level=None, sort="weakness", page=1, page_size=20) -> MasteryPage:
        query = select(KnowledgePoint, Course).join(Course, Course.id == KnowledgePoint.course_id)
        if course_id:
            query = query.where(KnowledgePoint.course_id == course_id)
        rows = self.db.execute(query.order_by(Course.title, KnowledgePoint.order_index, KnowledgePoint.id)).all()
        items = []
        for point, course in rows:
            mastery = self._ensure_current(point.id)
            if mastery_level and mastery.mastery_level != mastery_level:
                continue
            items.append(self._item(point, course, mastery))
        if sort == "mastery_desc":
            items.sort(key=lambda x: (x.mastery_score is None, -(x.mastery_score or 0), x.knowledge_point_id))
        elif sort == "recent":
            items.sort(key=lambda x: (x.last_practiced_at is None, -(x.last_practiced_at.timestamp() if x.last_practiced_at else 0)))
        else:
            items.sort(key=lambda x: (x.mastery_score is None, x.mastery_score if x.mastery_score is not None else 101, x.confidence_score))
        total = len(items)
        start = (page - 1) * page_size
        return MasteryPage(items=items[start:start + page_size], total=total, page=page, page_size=page_size, pages=ceil(total / page_size) if total else 0)

    def detail(self, point_id: int) -> MasteryDetail:
        point = self.db.get(KnowledgePoint, point_id)
        if not point:
            raise AppError("mastery_not_found", "知识点不存在", 404)
        course = self.db.get(Course, point.course_id)
        mastery = self._ensure_current(point_id)
        evidence = self.db.scalars(select(MasteryEvidence).where(
            MasteryEvidence.knowledge_point_id == point_id
        ).order_by(MasteryEvidence.occurred_at.desc(), MasteryEvidence.id.desc()).limit(100)).all()
        snapshots = self.db.scalars(select(MasterySnapshot).where(
            MasterySnapshot.knowledge_point_id == point_id
        ).order_by(MasterySnapshot.calculated_at.desc(), MasterySnapshot.id.desc()).limit(50)).all()
        schedule = self.db.scalar(select(ReviewSchedule).where(
            ReviewSchedule.knowledge_point_id == point_id,
            ReviewSchedule.status.in_(("pending", "scheduled")),
        ).order_by(ReviewSchedule.id.desc()))
        recommendation = self.db.scalar(select(AdaptiveRecommendation).where(
            AdaptiveRecommendation.knowledge_point_id == point_id,
            AdaptiveRecommendation.status.in_(("pending", "accepted", "executed")),
        ).order_by(AdaptiveRecommendation.id.desc()))
        base = self._item(point, course, mastery).model_dump()
        return MasteryDetail(
            **base, algorithm_version=mastery.algorithm_version, calculated_at=mastery.calculated_at,
            evidence_summary=snapshots[0].evidence_summary_json if snapshots else {},
            evidence=[EvidenceRead(
                id=row.id, evidence_type=row.evidence_type, source_type=row.source_type,
                source_id=row.source_id, occurred_at=row.occurred_at,
                normalized_score=float(row.normalized_score), weight=float(row.weight),
                metadata=row.metadata_json,
            ) for row in evidence],
            snapshots=[SnapshotRead(
                id=row.id,
                mastery_score=float(row.mastery_score) if row.mastery_score is not None else None,
                confidence_score=float(row.confidence_score), mastery_level=row.mastery_level,
                evidence_count=row.evidence_count, trigger_type=row.trigger_type,
                calculated_at=row.calculated_at,
            ) for row in snapshots],
            review_schedule=self.serialize_schedule(schedule) if schedule else None,
            recommendation=self.serialize_recommendation(recommendation) if recommendation else None,
        )

    def weak_points(self, *, course_id=None, limit=20, include_unassessed=True) -> list[WeakPointRead]:
        page = self.list_mastery(course_id=course_id, page=1, page_size=1000)
        items = []
        for base in page.items:
            mastery = self._ensure_current(base.knowledge_point_id)
            facts = WeakPointService(self.db, now=self.now).facts(mastery)
            if facts["classification"] == "unassessed" and not include_unassessed:
                continue
            items.append(WeakPointRead(**base.model_dump(), **{k: facts[k] for k in (
                "classification", "weakness_score", "recent_failure", "overdue", "review_status"
            )}))
        items.sort(key=lambda x: (x.classification == "unassessed", -(x.weakness_score or -1), x.knowledge_point_id))
        return items[:limit]

    def rebuild(self, *, course_id=None, knowledge_point_id=None) -> RebuildResult:
        query = select(KnowledgePoint)
        if knowledge_point_id:
            query = query.where(KnowledgePoint.id == knowledge_point_id)
        if course_id:
            query = query.where(KnowledgePoint.course_id == course_id)
        points = self.db.scalars(query.order_by(KnowledgePoint.id)).all()
        if knowledge_point_id and not points:
            raise AppError("mastery_not_found", "知识点不存在", 404)
        totals = dict(evidence_created=0, snapshots_created=0, schedules_created=0, recommendations_created=0)
        failures = []
        processed = 0
        for point in points:
            try:
                result = refresh_adaptive_learning(
                    self.db, self.settings, point.id, trigger_type="manual_rebuild", now=self.now
                )
                for key in totals:
                    totals[key] += int(result[key])
                processed += 1
            except Exception as exc:
                failures.append({"knowledge_point_id": point.id, "error": type(exc).__name__})
        return RebuildResult(processed=processed, failures=failures, **totals)

    def self_assessment(self, point_id: int, *, rating: int, request_id: str) -> MasteryDetail:
        if not self.db.get(KnowledgePoint, point_id):
            raise AppError("mastery_not_found", "知识点不存在", 404)
        _, created = LearningEvidenceCollector(self.db, self.settings, now=self.now).record_self_assessment(
            point_id, rating, request_id
        )
        self.db.commit()
        refresh_adaptive_learning(
            self.db, self.settings, point_id, trigger_type="self_assessment_updated",
            trigger_source_id=request_id, now=self.now,
        )
        return self.detail(point_id)

    def serialize_schedule(self, row: ReviewSchedule) -> ScheduleRead:
        point = self.db.get(KnowledgePoint, row.knowledge_point_id)
        return ScheduleRead(
            id=row.id, knowledge_point_id=row.knowledge_point_id,
            knowledge_point_title=point.title if point else "知识点已删除",
            status=row.status, priority_score=row.priority_score,
            recommended_at=row.recommended_at, due_at=row.due_at,
            overdue=row.status in {"pending", "scheduled"} and aware(row.due_at) < aware(self.now),
            reason_code="review_overdue" if row.status in {"pending", "scheduled"} and aware(row.due_at) < aware(self.now) else row.reason_code,
            reason_summary=row.reason_summary, completed_task_id=row.completed_task_id,
        )

    def serialize_recommendation(self, row: AdaptiveRecommendation) -> RecommendationRead:
        return RecommendationRead(
            id=row.id, knowledge_point_id=row.knowledge_point_id,
            recommendation_type=row.recommendation_type, status=row.status,
            priority=row.priority, title=row.title, reason_code=row.reason_code,
            reason_details=row.reason_details_json, suggested_date=row.suggested_date,
            suggested_minutes=row.suggested_minutes, created_task_id=row.created_task_id,
        )

    def list_reviews(self, *, status=None, course_id=None, start_date: date | None=None, end_date: date | None=None, overdue=False, limit=100) -> list[ScheduleRead]:
        query = select(ReviewSchedule).join(KnowledgePoint, KnowledgePoint.id == ReviewSchedule.knowledge_point_id)
        if status:
            query = query.where(ReviewSchedule.status == status)
        if course_id:
            query = query.where(KnowledgePoint.course_id == course_id)
        rows = self.db.scalars(query.order_by(ReviewSchedule.due_at, ReviewSchedule.priority_score.desc()).limit(limit)).all()
        result = []
        for row in rows:
            local_date = aware(row.due_at).astimezone(self.zone).date()
            item = self.serialize_schedule(row)
            if start_date and local_date < start_date:
                continue
            if end_date and local_date > end_date:
                continue
            if overdue and not item.overdue:
                continue
            result.append(item)
        return result

    def list_recommendations(self, *, status="pending", course_id=None, limit=100) -> list[RecommendationRead]:
        query = select(AdaptiveRecommendation).join(KnowledgePoint, KnowledgePoint.id == AdaptiveRecommendation.knowledge_point_id)
        if status:
            query = query.where(AdaptiveRecommendation.status == status)
        if course_id:
            query = query.where(KnowledgePoint.course_id == course_id)
        rows = self.db.scalars(query.order_by(AdaptiveRecommendation.suggested_date, AdaptiveRecommendation.id).limit(limit)).all()
        return [self.serialize_recommendation(row) for row in rows]

    def accept_recommendation(self, recommendation_id: int, *, request_id: str, confirmed: bool):
        return AdaptiveRecommendationService(self.db, self.settings, now=self.now).accept(
            recommendation_id, request_id=request_id, confirmed=confirmed
        )

    def reject_recommendation(self, recommendation_id: int):
        return AdaptiveRecommendationService(self.db, self.settings, now=self.now).reject(recommendation_id)
