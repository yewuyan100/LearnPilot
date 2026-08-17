import logging
from datetime import datetime
from hashlib import sha256

from sqlalchemy import select

from app.core.clock import Clock, clock_from_settings
from app.models.knowledge_mastery import KnowledgeMastery
from app.models.maintenance_task import MaintenanceTask
from app.models.mastery_snapshot import MasterySnapshot
from app.services.maintenance import MaintenanceTaskStore
from app.services.adaptive_learning.evidence_collector import LearningEvidenceCollector
from app.services.adaptive_learning.mastery import KnowledgeMasteryService
from app.services.adaptive_learning.recommendations import AdaptiveRecommendationService
from app.services.adaptive_learning.scheduler import ReviewScheduler


logger = logging.getLogger(__name__)


class AdaptiveRefreshError(RuntimeError):
    def __init__(self, stage: str, cause: Exception):
        super().__init__(str(cause))
        self.stage = stage
        self.cause = cause


def refresh_adaptive_learning(db, settings, knowledge_point_id: int, *, trigger_type: str, trigger_source_id=None, now: datetime | None = None, clock: Clock | None = None) -> dict:
    clock = clock or clock_from_settings(settings)
    now = now or clock.now()
    previous_mastery = db.scalar(select(KnowledgeMastery).where(
        KnowledgeMastery.knowledge_point_id == knowledge_point_id
    ))
    old_level = previous_mastery.mastery_level if previous_mastery else "unassessed"
    stage = "collect_evidence"
    try:
        created_evidence = LearningEvidenceCollector(db, settings, now=now).collect(knowledge_point_id)
        stage = "recalculate_mastery"
        mastery, snapshot_created = KnowledgeMasteryService(db, settings, now=now).recalculate(
            knowledge_point_id, trigger_type=trigger_type, trigger_source_id=trigger_source_id
        )
        stage = "schedule_review"
        schedule, schedule_created = ReviewScheduler(db, settings, now=now).schedule(mastery)
        stage = "generate_recommendation"
        recommendation, recommendation_created = AdaptiveRecommendationService(db, settings, now=now).generate(mastery, schedule)
        snapshot = None
        evidence_ids: list[int] = []
        if snapshot_created:
            snapshot = db.scalar(select(MasterySnapshot).where(
                MasterySnapshot.knowledge_point_id == knowledge_point_id
            ).order_by(MasterySnapshot.calculated_at.desc(), MasterySnapshot.id.desc()))
            if snapshot is not None:
                evidence_ids = [
                    int(item)
                    for item in snapshot.evidence_summary_json.get("selected_evidence_ids", [])
                ]
        db.commit()
        return {
            "knowledge_point_id": knowledge_point_id, "evidence_created": created_evidence,
            "snapshot_created": snapshot_created, "schedule_created": schedule_created,
            "recommendation_created": recommendation_created,
            "mastery_score": float(mastery.mastery_score) if mastery.mastery_score is not None else None,
            "confidence_score": float(mastery.confidence_score),
            "mastery_changed": snapshot_created,
            "old_level": old_level,
            "new_level": mastery.mastery_level,
            "evidence_ids": evidence_ids,
            "snapshot_id": snapshot.id if snapshot is not None else None,
            "schedule_id": schedule.id if schedule else None,
            "recommendation_id": recommendation.id if recommendation else None,
        }
    except Exception as exc:
        db.rollback()
        logger.exception(
            "adaptive_learning_refresh_failed knowledge_point_id=%s trigger=%s stage=%s",
            knowledge_point_id,
            trigger_type,
            stage,
        )
        raise AdaptiveRefreshError(stage, exc) from exc


def _refresh_key(knowledge_point_id: int, trigger_type: str, trigger_source_id) -> str:
    raw = f"{knowledge_point_id}:{trigger_type}:{trigger_source_id or '-'}"
    return "adaptive-refresh:" + sha256(raw.encode()).hexdigest()


def try_refresh_adaptive_learning(db, settings, knowledge_point_id: int | None, *, trigger_type: str, trigger_source_id=None, now: datetime | None = None, clock: Clock | None = None) -> dict | None:
    """Refresh after the primary transaction; adaptive failure never falsifies business success."""
    if not knowledge_point_id:
        return None
    clock = clock or clock_from_settings(settings)
    store = MaintenanceTaskStore(db, clock)
    task = store.get_or_create(
        task_type="adaptive_refresh",
        entity_type="knowledge_point",
        entity_id=knowledge_point_id,
        request_key=_refresh_key(knowledge_point_id, trigger_type, trigger_source_id),
        payload={
            "knowledge_point_id": knowledge_point_id,
            "trigger_type": trigger_type,
            "trigger_source_id": trigger_source_id,
        },
    )
    if task.status == "completed":
        return store.serialize(task)
    store.start(task, "collect_evidence")
    try:
        result = refresh_adaptive_learning(
            db, settings, knowledge_point_id, trigger_type=trigger_type,
            trigger_source_id=trigger_source_id, now=now, clock=clock,
        )
        task = db.get(MaintenanceTask, task.id)
        return store.serialize(store.complete(task, result))
    except AdaptiveRefreshError as exc:
        task = db.get(MaintenanceTask, task.id)
        task = store.fail(
            task,
            stage=exc.stage,
            error_code="adaptive_refresh_failed",
            error_message=type(exc.cause).__name__,
        )
        return store.serialize(task)


def retry_adaptive_refresh(db, settings, task_id: int, *, clock: Clock | None = None) -> dict:
    task = db.get(MaintenanceTask, task_id)
    if task is None or task.task_type != "adaptive_refresh":
        raise ValueError("adaptive_refresh_task_not_found")
    if task.status == "completed":
        return MaintenanceTaskStore.serialize(task)
    payload = task.payload
    task.status = "pending"
    db.commit()
    return try_refresh_adaptive_learning(
        db,
        settings,
        int(payload["knowledge_point_id"]),
        trigger_type=payload["trigger_type"],
        trigger_source_id=payload.get("trigger_source_id"),
        clock=clock,
    )


def adaptive_refresh_status(db, knowledge_point_id: int) -> dict | None:
    task = db.scalar(
        select(MaintenanceTask)
        .where(
            MaintenanceTask.task_type == "adaptive_refresh",
            MaintenanceTask.entity_type == "knowledge_point",
            MaintenanceTask.entity_id == str(knowledge_point_id),
        )
        .order_by(MaintenanceTask.updated_at.desc(), MaintenanceTask.id.desc())
    )
    return MaintenanceTaskStore.serialize(task) if task else None
