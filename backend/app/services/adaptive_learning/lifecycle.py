import logging
from datetime import datetime, timezone

from app.services.adaptive_learning.evidence_collector import LearningEvidenceCollector
from app.services.adaptive_learning.mastery import KnowledgeMasteryService
from app.services.adaptive_learning.recommendations import AdaptiveRecommendationService
from app.services.adaptive_learning.scheduler import ReviewScheduler


logger = logging.getLogger(__name__)


def refresh_adaptive_learning(db, settings, knowledge_point_id: int, *, trigger_type: str, trigger_source_id=None, now: datetime | None = None) -> dict:
    now = now or settings.adaptive_fixed_now or datetime.now(timezone.utc)
    try:
        created_evidence = LearningEvidenceCollector(db, settings, now=now).collect(knowledge_point_id)
        mastery, snapshot_created = KnowledgeMasteryService(db, settings, now=now).recalculate(
            knowledge_point_id, trigger_type=trigger_type, trigger_source_id=trigger_source_id
        )
        schedule, schedule_created = ReviewScheduler(db, settings, now=now).schedule(mastery)
        recommendation, recommendation_created = AdaptiveRecommendationService(db, settings, now=now).generate(mastery, schedule)
        db.commit()
        return {
            "knowledge_point_id": knowledge_point_id, "evidence_created": created_evidence,
            "snapshot_created": snapshot_created, "schedule_created": schedule_created,
            "recommendation_created": recommendation_created,
            "mastery_score": float(mastery.mastery_score) if mastery.mastery_score is not None else None,
            "confidence_score": float(mastery.confidence_score),
            "schedule_id": schedule.id if schedule else None,
            "recommendation_id": recommendation.id if recommendation else None,
        }
    except Exception:
        db.rollback()
        logger.exception("adaptive_learning_refresh_failed knowledge_point_id=%s trigger=%s", knowledge_point_id, trigger_type)
        raise


def try_refresh_adaptive_learning(db, settings, knowledge_point_id: int | None, *, trigger_type: str, trigger_source_id=None, now: datetime | None = None) -> dict | None:
    """Refresh after the primary transaction; adaptive failure never falsifies business success."""
    if not knowledge_point_id:
        return None
    try:
        return refresh_adaptive_learning(
            db, settings, knowledge_point_id, trigger_type=trigger_type,
            trigger_source_id=trigger_source_id, now=now,
        )
    except Exception:
        return None
