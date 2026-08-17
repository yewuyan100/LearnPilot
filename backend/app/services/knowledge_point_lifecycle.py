from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Callable

from fastapi import status
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.models import (
    DailyTask,
    KnowledgeMastery,
    KnowledgePoint,
    KnowledgePointLifecycleChange,
    KnowledgePointPrerequisite,
    LearningActivity,
    LearningSession,
    ReviewSchedule,
    StudyPlan,
    StudyPlanItem,
    StudyPlanVersion,
)
from app.schemas.course import KnowledgePointRead
from app.schemas.knowledge_point_lifecycle import (
    KnowledgePointApplyRequest,
    KnowledgePointChangeRequest,
    KnowledgePointChangeResult,
    KnowledgePointImpact,
)


class KnowledgePointLifecycleService:
    """Deep module for inspect-confirm-apply knowledge-point transitions.

    Historical facts remain attached to the original knowledge point. This
    module only marks downstream executable state stale, blocked, or invalid.
    """

    _PLAN_ACTIONABLE_STATUSES = ("draft", "validating", "ready", "infeasible", "active")
    _TASK_ACTIONABLE_STATUSES = ("pending", "in_progress")
    _SESSION_ACTIONABLE_STATUSES = ("active", "paused")

    def __init__(self, db, now: Callable[[], datetime] | None = None):
        self.db = db
        self._now = now or (lambda: datetime.now(timezone.utc))

    def inspect_change(
        self, point_id: int, request: KnowledgePointChangeRequest
    ) -> KnowledgePointImpact:
        point = self._require_active_point(point_id)
        self._validate_replacement(point, request)

        edge_ids = list(
            self.db.scalars(
                select(KnowledgePointPrerequisite.id).where(
                    or_(
                        KnowledgePointPrerequisite.prerequisite_knowledge_point_id == point.id,
                        KnowledgePointPrerequisite.dependent_knowledge_point_id == point.id,
                    )
                )
            )
        )
        plan_items = list(
            self.db.scalars(
                select(StudyPlanItem).where(StudyPlanItem.knowledge_point_id == point.id)
            )
        )
        all_version_ids = sorted({item.study_plan_version_id for item in plan_items})
        plan_versions = (
            list(
                self.db.scalars(
                    select(StudyPlanVersion).where(StudyPlanVersion.id.in_(all_version_ids))
                )
            )
            if all_version_ids
            else []
        )
        affected_versions = sorted(
            version.id
            for version in plan_versions
            if version.status in self._PLAN_ACTIONABLE_STATUSES and version.stale_at is None
        )
        plan_ids = sorted(
            {
                version.study_plan_id
                for version in plan_versions
                if version.id in set(affected_versions)
            }
        )

        tasks = list(
            self.db.scalars(select(DailyTask).where(DailyTask.knowledge_point_id == point.id))
        )
        sessions = list(
            self.db.scalars(
                select(LearningSession).where(LearningSession.knowledge_point_id == point.id)
            )
        )
        activity_ids = list(
            self.db.scalars(
                select(LearningActivity.id).where(LearningActivity.knowledge_point_id == point.id)
            )
        )
        mastery_ids = list(
            self.db.scalars(
                select(KnowledgeMastery.id).where(KnowledgeMastery.knowledge_point_id == point.id)
            )
        )
        review_ids = list(
            self.db.scalars(
                select(ReviewSchedule.id).where(ReviewSchedule.knowledge_point_id == point.id)
            )
        )

        canonical = {
            "knowledge_point_id": point.id,
            "point_version": point.version,
            "lifecycle_status": point.lifecycle_status,
            "action": request.action,
            "superseded_by_id": request.superseded_by_id,
            "lifecycle_reason": request.lifecycle_reason,
            "prerequisite_edge_ids": sorted(edge_ids),
            "study_plan_ids": plan_ids,
            "study_plan_version_ids": affected_versions,
            "study_plan_item_ids": sorted(item.id for item in plan_items),
            "daily_task_ids": sorted(task.id for task in tasks),
            "actionable_daily_task_ids": sorted(
                task.id
                for task in tasks
                if task.status in self._TASK_ACTIONABLE_STATUSES and task.blocked_at is None
            ),
            "learning_session_ids": sorted(session.id for session in sessions),
            "active_learning_session_ids": sorted(
                session.id
                for session in sessions
                if session.status in self._SESSION_ACTIONABLE_STATUSES
                and session.invalidated_at is None
            ),
            "activity_ids": sorted(activity_ids),
            "mastery_ids": sorted(mastery_ids),
            "review_schedule_ids": sorted(review_ids),
        }
        impact_hash = self._hash(canonical)
        return KnowledgePointImpact(
            knowledge_point_title=point.title,
            course_id=point.course_id,
            impact_hash=impact_hash,
            requires_confirmation=True,
            **{key: value for key, value in canonical.items() if key != "lifecycle_reason"},
        )

    def apply_change(
        self, point_id: int, request: KnowledgePointApplyRequest
    ) -> KnowledgePointChangeResult:
        arguments_hash = self._arguments_hash(point_id, request)
        existing = self.db.scalar(
            select(KnowledgePointLifecycleChange).where(
                KnowledgePointLifecycleChange.request_id == request.request_id
            )
        )
        if existing is not None:
            return self._replay(existing, arguments_hash)

        point = self._require_active_point(point_id)
        if point.version != request.expected_version:
            raise AppError(
                "knowledge_point_version_conflict",
                "知识点已更新，请重新检查影响后再确认",
                status.HTTP_409_CONFLICT,
                {"current_version": point.version, "expected_version": request.expected_version},
            )

        impact = self.inspect_change(
            point_id,
            KnowledgePointChangeRequest(
                action=request.action,
                superseded_by_id=request.superseded_by_id,
                lifecycle_reason=request.lifecycle_reason,
            ),
        )
        if impact.impact_hash != request.impact_hash:
            raise AppError(
                "knowledge_point_impact_changed",
                "知识点影响范围已变化，请重新检查并确认",
                status.HTTP_409_CONFLICT,
                {"current_impact": impact.model_dump(mode="json")},
            )

        now = self._now()
        target_status = "archived" if request.action == "archive" else "superseded"
        try:
            result = self.db.execute(
                update(KnowledgePoint)
                .where(
                    KnowledgePoint.id == point_id,
                    KnowledgePoint.version == request.expected_version,
                    KnowledgePoint.lifecycle_status == "active",
                )
                .values(
                    lifecycle_status=target_status,
                    superseded_by_id=request.superseded_by_id,
                    lifecycle_reason=request.lifecycle_reason,
                    archived_at=now if request.action == "archive" else None,
                    version=KnowledgePoint.version + 1,
                    updated_at=now,
                )
            )
            if result.rowcount != 1:
                raise AppError(
                    "knowledge_point_version_conflict",
                    "知识点已更新，请重新检查影响后再确认",
                    status.HTTP_409_CONFLICT,
                )

            stale_reason = f"知识点“{point.title}”已{('归档' if request.action == 'archive' else '被替代')}，需要重新生成学习计划"
            if impact.study_plan_version_ids:
                self.db.execute(
                    update(StudyPlanVersion)
                    .where(StudyPlanVersion.id.in_(impact.study_plan_version_ids))
                    .values(
                        stale_at=now,
                        stale_reason=stale_reason,
                        stale_source_type="knowledge_point",
                        stale_source_id=point.id,
                        updated_at=now,
                    )
                )
            if impact.actionable_daily_task_ids:
                self.db.execute(
                    update(DailyTask)
                    .where(DailyTask.id.in_(impact.actionable_daily_task_ids))
                    .values(
                        blocked_at=now,
                        blocked_reason="该任务对应课程内容已变化，需要重新规划",
                        blocked_source_type="knowledge_point",
                        blocked_source_id=point.id,
                        updated_at=now,
                    )
                )
            if impact.active_learning_session_ids:
                self.db.execute(
                    update(LearningSession)
                    .where(LearningSession.id.in_(impact.active_learning_session_ids))
                    .values(
                        invalidated_at=now,
                        invalidation_reason="该学习会话关联的知识点已失效，不能继续学习",
                        updated_at=now,
                    )
                )

            audit = KnowledgePointLifecycleChange(
                knowledge_point_id=point.id,
                request_id=request.request_id,
                action=request.action,
                arguments_hash=arguments_hash,
                from_status="active",
                to_status=target_status,
                superseded_by_id=request.superseded_by_id,
                expected_version=request.expected_version,
                resulting_version=request.expected_version + 1,
                impact_snapshot=impact.model_dump(mode="json"),
                applied_at=now,
            )
            self.db.add(audit)
            self.db.commit()
        except AppError:
            self.db.rollback()
            raise
        except IntegrityError as exc:
            self.db.rollback()
            raced = self.db.scalar(
                select(KnowledgePointLifecycleChange).where(
                    KnowledgePointLifecycleChange.request_id == request.request_id
                )
            )
            if raced is not None:
                return self._replay(raced, arguments_hash)
            raise AppError(
                "knowledge_point_lifecycle_conflict",
                "知识点生命周期变更发生并发冲突，所有写入已回滚",
                status.HTTP_409_CONFLICT,
            ) from exc
        except Exception:
            self.db.rollback()
            raise

        changed = self.db.get(KnowledgePoint, point_id)
        self.db.refresh(changed)
        return KnowledgePointChangeResult(
            point=KnowledgePointRead.model_validate(changed),
            impact=impact,
            idempotent_replay=False,
        )

    def _require_active_point(self, point_id: int) -> KnowledgePoint:
        point = self.db.get(KnowledgePoint, point_id)
        if point is None:
            raise AppError(
                "knowledge_point_not_found", "知识点不存在", status.HTTP_404_NOT_FOUND
            )
        if point.lifecycle_status != "active":
            raise AppError(
                "knowledge_point_not_active",
                "只有有效知识点可以执行生命周期变更",
                status.HTTP_409_CONFLICT,
                {"lifecycle_status": point.lifecycle_status},
            )
        return point

    def _validate_replacement(
        self, point: KnowledgePoint, request: KnowledgePointChangeRequest
    ) -> None:
        if request.action != "supersede":
            return
        replacement = self.db.get(KnowledgePoint, request.superseded_by_id)
        if replacement is None:
            raise AppError(
                "knowledge_point_replacement_not_found",
                "替代知识点不存在",
                status.HTTP_404_NOT_FOUND,
            )
        if replacement.id == point.id:
            raise AppError(
                "knowledge_point_replacement_self",
                "知识点不能替代自身",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if replacement.course_id != point.course_id:
            raise AppError(
                "knowledge_point_replacement_cross_course",
                "替代知识点必须属于同一课程",
                status.HTTP_409_CONFLICT,
            )
        if replacement.lifecycle_status != "active":
            raise AppError(
                "knowledge_point_replacement_not_active",
                "替代知识点必须处于有效状态",
                status.HTTP_409_CONFLICT,
            )

    def _replay(
        self, record: KnowledgePointLifecycleChange, arguments_hash: str
    ) -> KnowledgePointChangeResult:
        if record.arguments_hash != arguments_hash:
            raise AppError(
                "knowledge_point_request_id_conflict",
                "相同 request_id 已用于不同的生命周期变更",
                status.HTTP_409_CONFLICT,
            )
        point = self.db.get(KnowledgePoint, record.knowledge_point_id)
        if point is None:
            raise AppError(
                "knowledge_point_lifecycle_audit_broken",
                "生命周期审计记录关联的知识点不存在",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return KnowledgePointChangeResult(
            point=KnowledgePointRead.model_validate(point),
            impact=KnowledgePointImpact.model_validate(record.impact_snapshot),
            idempotent_replay=True,
        )

    @staticmethod
    def _hash(payload: dict) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sha256(raw.encode("utf-8")).hexdigest()

    def _arguments_hash(self, point_id: int, request: KnowledgePointApplyRequest) -> str:
        return self._hash(
            {
                "point_id": point_id,
                "action": request.action,
                "superseded_by_id": request.superseded_by_id,
                "lifecycle_reason": request.lifecycle_reason,
                "expected_version": request.expected_version,
                "impact_hash": request.impact_hash,
                "confirmed": request.confirmed,
            }
        )
