from __future__ import annotations

import json
from datetime import date
from hashlib import sha256
from uuid import uuid4

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.models import (
    Course,
    DailyTask,
    KnowledgePoint,
    LearningGoal,
    Lesson,
    StudyPlan,
    StudyPlanItem,
    StudyPlanVersion,
)
from app.schemas.study_plan import (
    StudyPlanCancelRequest,
    StudyPlanCreateRequest,
    StudyPlanHistoryResponse,
    StudyPlanItemRead,
    StudyPlanPublishRequest,
    StudyPlanPublishResult,
    StudyPlanRead,
    StudyPlanReplanRequest,
    StudyPlanVersionRead,
)
from app.services.course_state import CourseStateService
from app.services.study_plans.scheduler import DeterministicStudyScheduler, PlanComputation


def _hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode()).hexdigest()


class StudyPlanService:
    """Versioned planning interface; DailyTask remains the execution truth source."""

    def __init__(self, db, settings, clock):
        self.db = db
        self.settings = settings
        self.clock = clock

    def _plan(self, plan_id: int) -> StudyPlan:
        plan = self.db.get(StudyPlan, plan_id)
        if plan is None:
            raise AppError("study_plan_not_found", "学习计划不存在", status.HTTP_404_NOT_FOUND)
        return plan

    def _version(self, plan: StudyPlan, version_number: int) -> StudyPlanVersion:
        version = self.db.scalar(
            select(StudyPlanVersion).where(
                StudyPlanVersion.study_plan_id == plan.id,
                StudyPlanVersion.version_number == version_number,
            )
        )
        if version is None:
            raise AppError("study_plan_version_not_found", "计划版本不存在", status.HTTP_404_NOT_FOUND)
        return version

    @staticmethod
    def _parameters(payload: StudyPlanCreateRequest) -> dict:
        return {
            **payload.model_dump(mode="json", exclude={"request_id", "learning_goal_id", "course_id"}),
            "start_date": payload.start_date.isoformat(),
            "target_date": payload.target_date.isoformat(),
        }

    def _validate_scope(self, learning_goal_id: int, course_id: int):
        goal = self.db.get(LearningGoal, learning_goal_id)
        if goal is None:
            raise AppError("learning_goal_not_found", "学习目标不存在", status.HTTP_404_NOT_FOUND)
        if goal.status == "archived":
            raise AppError("study_plan_goal_archived", "已归档目标不能创建计划", status.HTTP_409_CONFLICT)
        course, points = CourseStateService(self.db).require_formal(course_id)
        if course.learning_goal_id != goal.id:
            raise AppError(
                "study_plan_scope_mismatch",
                "课程不属于所选学习目标",
                status.HTTP_409_CONFLICT,
            )
        return goal, course, points

    def create(self, payload: StudyPlanCreateRequest) -> StudyPlanRead:
        goal, course, points = self._validate_scope(payload.learning_goal_id, payload.course_id)
        parameters = self._parameters(payload)
        config_hash = _hash(
            {"learning_goal_id": goal.id, "course_id": course.id, "parameters": parameters}
        )
        existing = self.db.scalar(
            select(StudyPlan).where(StudyPlan.generation_request_id == payload.request_id)
        )
        if existing:
            if existing.generation_config_hash != config_hash:
                raise AppError(
                    "study_plan_request_conflict",
                    "相同 request_id 已用于不同计划参数",
                    status.HTTP_409_CONFLICT,
                )
            return self.serialize(existing, idempotent_replay=True)
        snapshot = CourseStateService(self.db).snapshot_hash(course, points)
        computation = DeterministicStudyScheduler(self.db, self.clock).compute(
            course=course, points=points, parameters=parameters
        )
        plan = StudyPlan(
            public_id=str(uuid4()),
            learning_goal_id=goal.id,
            course_id=course.id,
            status=computation.status,
            current_version_number=1,
            generation_request_id=payload.request_id,
            generation_config_hash=config_hash,
        )
        self.db.add(plan)
        try:
            self.db.flush()
            version = self._persist_version(
                plan=plan,
                version_number=1,
                parameters=parameters,
                snapshot=snapshot,
                computation=computation,
                reason="初始计划",
                generation_request_id=payload.request_id,
            )
            self.db.commit()
            return self.serialize(plan)
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(
                "study_plan_request_conflict",
                "计划生成发生并发冲突，请重放原请求",
                status.HTTP_409_CONFLICT,
            ) from exc

    def _persist_version(
        self,
        *,
        plan: StudyPlan,
        version_number: int,
        parameters: dict,
        snapshot: str,
        computation: PlanComputation,
        reason: str,
        generation_request_id: str | None = None,
        replan_request_id: str | None = None,
    ) -> StudyPlanVersion:
        version = StudyPlanVersion(
            study_plan_id=plan.id,
            version_number=version_number,
            status=computation.status,
            generation_request_id=generation_request_id,
            replan_request_id=replan_request_id,
            parameters=parameters,
            course_snapshot_hash=snapshot,
            diagnostic_session_id=computation.diagnostic_session_id,
            required_minutes=computation.required_minutes,
            available_minutes=computation.available_minutes,
            gap_minutes=computation.gap_minutes,
            conflicts=computation.conflicts,
            suggestions=computation.suggestions,
            quality_report=computation.quality_report,
            reason=reason,
        )
        self.db.add(version)
        self.db.flush()
        for index, item in enumerate(computation.items, start=1):
            assert item.scheduled_date is not None
            self.db.add(
                StudyPlanItem(
                    study_plan_version_id=version.id,
                    learning_goal_id=plan.learning_goal_id,
                    course_id=plan.course_id,
                    knowledge_point_id=item.knowledge_point_id,
                    scheduled_date=item.scheduled_date,
                    order_index=index,
                    logical_key=item.logical_key,
                    title=item.title,
                    activity_type=item.activity_type,
                    estimated_minutes=item.minutes,
                    scheduling_reason=item.reason,
                    prerequisite_ids=item.prerequisite_ids,
                    is_due_review=item.is_due_review,
                    review_schedule_id=item.review_schedule_id,
                    diagnostic_result_id=item.diagnostic_result_id,
                    daily_task_id=item.daily_task_id,
                )
            )
        self.db.flush()
        return version

    def replan(self, plan_id: int, payload: StudyPlanReplanRequest) -> StudyPlanRead:
        plan = self._plan(plan_id)
        existing = self.db.scalar(
            select(StudyPlanVersion).where(
                StudyPlanVersion.replan_request_id == payload.request_id
            )
        )
        if existing:
            if existing.study_plan_id != plan.id:
                raise AppError(
                    "study_plan_replan_request_conflict",
                    "重新规划 request_id 已用于另一份计划",
                    status.HTTP_409_CONFLICT,
                )
            return self.serialize(plan, idempotent_replay=True)
        if plan.status in {"cancelled", "completed", "superseded"}:
            raise AppError(
                "study_plan_not_replannable",
                "当前计划状态不能重新规划",
                status.HTTP_409_CONFLICT,
            )
        if plan.version != payload.expected_version:
            raise AppError(
                "study_plan_version_conflict",
                "计划已更新，请刷新后重试",
                status.HTTP_409_CONFLICT,
                {"current_version": plan.version},
            )
        goal, course, points = self._validate_scope(plan.learning_goal_id, plan.course_id)
        latest = self._version(plan, plan.current_version_number)
        parameters = dict(latest.parameters)
        updates = payload.model_dump(
            mode="json",
            exclude={"request_id", "expected_version", "reason"},
            exclude_none=True,
        )
        parameters.update(updates)
        parameters["start_date"] = max(
            self.clock.today(), date.fromisoformat(parameters["start_date"])
        ).isoformat()
        validated = StudyPlanCreateRequest(
            request_id=payload.request_id,
            learning_goal_id=plan.learning_goal_id,
            course_id=plan.course_id,
            **parameters,
        )
        parameters = self._parameters(validated)
        movable: dict[str, DailyTask] = {}
        completed: set[str] = set()
        if plan.active_version_number:
            active = self._version(plan, plan.active_version_number)
            active_items = list(
                self.db.scalars(
                    select(StudyPlanItem).where(StudyPlanItem.study_plan_version_id == active.id)
                )
            )
            for item in active_items:
                if not item.daily_task_id:
                    continue
                task = self.db.get(DailyTask, item.daily_task_id)
                if not task:
                    continue
                if task.status == "completed":
                    completed.add(item.logical_key)
                elif task.status in {"pending", "in_progress"}:
                    movable[item.logical_key] = task
        snapshot = CourseStateService(self.db).snapshot_hash(course, points)
        computation = DeterministicStudyScheduler(self.db, self.clock).compute(
            course=course,
            points=points,
            parameters=parameters,
            movable_tasks=movable,
            completed_logical_keys=completed,
        )
        new_number = plan.current_version_number + 1
        if latest.status != "active":
            latest.status = "superseded"
        self._persist_version(
            plan=plan,
            version_number=new_number,
            parameters=parameters,
            snapshot=snapshot,
            computation=computation,
            reason=payload.reason,
            replan_request_id=payload.request_id,
        )
        plan.current_version_number = new_number
        if plan.active_version_number is None:
            plan.status = computation.status
        plan.version += 1
        try:
            self.db.commit()
            return self.serialize(plan)
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(
                "study_plan_replan_request_conflict",
                "重新规划发生并发冲突，请重放原请求",
                status.HTTP_409_CONFLICT,
            ) from exc

    def apply_plan_adjustment(
        self,
        plan_id: int,
        *,
        proposal_id: str,
        reason: str,
    ) -> StudyPlanPublishResult:
        """Apply a confirmed proposal through the existing deterministic lifecycle."""

        plan = self._plan(plan_id)
        replanned = self.replan(
            plan_id,
            StudyPlanReplanRequest(
                request_id=f"plan-adjust:{proposal_id}:replan",
                expected_version=plan.version,
                reason=reason,
            ),
        )
        return self.publish(
            plan_id,
            StudyPlanPublishRequest(
                request_id=f"plan-adjust:{proposal_id}:publish",
                expected_version=replanned.version,
                confirmed=True,
            ),
        )

    def publish(self, plan_id: int, payload: StudyPlanPublishRequest) -> StudyPlanPublishResult:
        plan = self._plan(plan_id)
        replay_version = self.db.scalar(
            select(StudyPlanVersion).where(
                StudyPlanVersion.publish_request_id == payload.request_id
            )
        )
        if replay_version:
            if replay_version.study_plan_id != plan.id:
                raise AppError(
                    "study_plan_publish_request_conflict",
                    "发布 request_id 已用于另一份计划",
                    status.HTTP_409_CONFLICT,
                )
            item_rows = list(
                self.db.scalars(
                    select(StudyPlanItem).where(
                        StudyPlanItem.study_plan_version_id == replay_version.id
                    )
                )
            )
            task_ids = [item.daily_task_id for item in item_rows if item.daily_task_id]
            return StudyPlanPublishResult(
                plan=self.serialize(plan, idempotent_replay=True),
                created_task_ids=[],
                reused_task_ids=task_ids,
                rescheduled_task_ids=[],
                idempotent_replay=True,
            )
        if plan.version != payload.expected_version:
            raise AppError(
                "study_plan_version_conflict",
                "计划已更新，请刷新后重试",
                status.HTTP_409_CONFLICT,
                {"current_version": plan.version},
            )
        version = self._version(plan, plan.current_version_number)
        if version.stale_at is not None:
            raise AppError(
                "study_plan_source_stale",
                version.stale_reason or "课程内容已变化，请重新生成计划",
                status.HTTP_409_CONFLICT,
                {
                    "stale_at": version.stale_at.isoformat(),
                    "stale_source_type": version.stale_source_type,
                    "stale_source_id": version.stale_source_id,
                },
            )
        if version.status != "ready":
            raise AppError(
                "study_plan_not_publishable",
                "只有已通过质量检查的可行计划才能确认",
                status.HTTP_409_CONFLICT,
                {"version_status": version.status},
            )
        _, course, points = self._validate_scope(plan.learning_goal_id, plan.course_id)
        if CourseStateService(self.db).snapshot_hash(course, points) != version.course_snapshot_hash:
            raise AppError(
                "study_plan_source_stale",
                "课程结构或资料已变化，请重新生成计划",
                status.HTTP_409_CONFLICT,
            )
        created: list[int] = []
        reused: list[int] = []
        rescheduled: list[int] = []
        try:
            items = list(
                self.db.scalars(
                    select(StudyPlanItem)
                    .where(StudyPlanItem.study_plan_version_id == version.id)
                    .order_by(StudyPlanItem.order_index)
                )
            )
            for item in items:
                task = self.db.get(DailyTask, item.daily_task_id) if item.daily_task_id else None
                if task is None:
                    task = self.db.scalar(
                        select(DailyTask).where(
                            DailyTask.learning_goal_id == item.learning_goal_id,
                            DailyTask.course_id == item.course_id,
                            DailyTask.knowledge_point_id == item.knowledge_point_id,
                            DailyTask.task_type == item.activity_type,
                            DailyTask.scheduled_date == item.scheduled_date,
                            DailyTask.status.in_(("pending", "in_progress", "completed")),
                        )
                    )
                if task is None:
                    task = self._create_daily_task(item)
                    self.db.flush()
                    created.append(task.id)
                else:
                    if task.status != "completed" and (
                        task.scheduled_date != item.scheduled_date
                        or task.estimated_minutes != item.estimated_minutes
                    ):
                        task.scheduled_date = item.scheduled_date
                        task.estimated_minutes = item.estimated_minutes
                        task.title = item.title
                        task.task_type = item.activity_type
                        rescheduled.append(task.id)
                    else:
                        reused.append(task.id)
                item.daily_task_id = task.id
            if plan.active_version_number:
                previous = self._version(plan, plan.active_version_number)
                if previous.id != version.id:
                    previous.status = "superseded"
            other_plans = list(
                self.db.scalars(
                    select(StudyPlan).where(
                        StudyPlan.learning_goal_id == plan.learning_goal_id,
                        StudyPlan.course_id == plan.course_id,
                        StudyPlan.status == "active",
                        StudyPlan.id != plan.id,
                    )
                )
            )
            for other in other_plans:
                other.status = "superseded"
            version.publish_request_id = payload.request_id
            version.status = "active"
            version.published_at = self.clock.now()
            plan.status = "active"
            plan.active_version_number = version.version_number
            plan.version += 1
            self.db.commit()
            return StudyPlanPublishResult(
                plan=self.serialize(plan),
                created_task_ids=created,
                reused_task_ids=reused,
                rescheduled_task_ids=rescheduled,
            )
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(
                "study_plan_publish_conflict",
                "计划发布发生并发冲突，所有本次任务写入已回滚",
                status.HTTP_409_CONFLICT,
            ) from exc
        except AppError:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            raise AppError(
                "study_plan_publish_failed",
                "计划发布失败，所有本次任务写入已回滚",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                {"reason": type(exc).__name__},
            ) from exc

    def _create_daily_task(self, item: StudyPlanItem) -> DailyTask:
        task = DailyTask(
            learning_goal_id=item.learning_goal_id,
            course_id=item.course_id,
            knowledge_point_id=item.knowledge_point_id,
            title=item.title,
            task_type=item.activity_type,
            estimated_minutes=item.estimated_minutes,
            scheduled_date=item.scheduled_date,
            status="pending",
        )
        self.db.add(task)
        return task

    def cancel(self, plan_id: int, payload: StudyPlanCancelRequest) -> StudyPlanRead:
        plan = self._plan(plan_id)
        if plan.status == "cancelled" and plan.cancel_request_id == payload.request_id:
            return self.serialize(plan, idempotent_replay=True)
        conflict = self.db.scalar(
            select(StudyPlan).where(
                StudyPlan.cancel_request_id == payload.request_id,
                StudyPlan.id != plan.id,
            )
        )
        if conflict:
            raise AppError(
                "study_plan_cancel_request_conflict",
                "取消 request_id 已用于另一份计划",
                status.HTTP_409_CONFLICT,
            )
        if plan.version != payload.expected_version:
            raise AppError(
                "study_plan_version_conflict",
                "计划已更新，请刷新后重试",
                status.HTTP_409_CONFLICT,
                {"current_version": plan.version},
            )
        plan.status = "cancelled"
        plan.cancel_request_id = payload.request_id
        plan.cancelled_at = self.clock.now()
        plan.version += 1
        current = self._version(plan, plan.current_version_number)
        if current.status != "superseded":
            current.status = "cancelled"
        if plan.active_version_number and plan.active_version_number != current.version_number:
            self._version(plan, plan.active_version_number).status = "cancelled"
        self.db.commit()
        return self.serialize(plan)

    def get(self, plan_id: int) -> StudyPlanRead:
        return self.serialize(self._plan(plan_id))

    def active(self, learning_goal_id: int | None = None, course_id: int | None = None) -> StudyPlanRead | None:
        query = select(StudyPlan).where(StudyPlan.status == "active")
        if learning_goal_id:
            query = query.where(StudyPlan.learning_goal_id == learning_goal_id)
        if course_id:
            query = query.where(StudyPlan.course_id == course_id)
        plan = self.db.scalar(query.order_by(StudyPlan.updated_at.desc(), StudyPlan.id.desc()))
        return self.serialize(plan) if plan else None

    def history(self, plan_id: int) -> StudyPlanHistoryResponse:
        plan = self._plan(plan_id)
        versions = list(
            self.db.scalars(
                select(StudyPlanVersion)
                .where(StudyPlanVersion.study_plan_id == plan.id)
                .order_by(StudyPlanVersion.version_number.desc())
            )
        )
        return StudyPlanHistoryResponse(
            items=[self._serialize_version(version) for version in versions], total=len(versions)
        )

    def _serialize_item(self, item: StudyPlanItem) -> StudyPlanItemRead:
        course = self.db.get(Course, item.course_id)
        point = self.db.get(KnowledgePoint, item.knowledge_point_id) if item.knowledge_point_id else None
        lesson = self.db.get(Lesson, item.lesson_id) if item.lesson_id else None
        task = self.db.get(DailyTask, item.daily_task_id) if item.daily_task_id else None
        return StudyPlanItemRead(
            id=item.id,
            scheduled_date=item.scheduled_date,
            order_index=item.order_index,
            logical_key=item.logical_key,
            learning_goal_id=item.learning_goal_id,
            course_id=item.course_id,
            course_title=course.title if course else "已删除课程",
            knowledge_point_id=item.knowledge_point_id,
            knowledge_point_title=point.title if point else None,
            lesson_id=item.lesson_id,
            lesson_title=lesson.title if lesson else None,
            title=item.title,
            activity_type=item.activity_type,
            estimated_minutes=item.estimated_minutes,
            scheduling_reason=item.scheduling_reason,
            prerequisite_ids=item.prerequisite_ids,
            is_due_review=item.is_due_review,
            review_schedule_id=item.review_schedule_id,
            diagnostic_result_id=item.diagnostic_result_id,
            daily_task_id=item.daily_task_id,
            task_status=task.status if task else None,
        )

    def _serialize_version(self, version: StudyPlanVersion) -> StudyPlanVersionRead:
        items = list(
            self.db.scalars(
                select(StudyPlanItem)
                .where(StudyPlanItem.study_plan_version_id == version.id)
                .order_by(StudyPlanItem.order_index)
            )
        )
        return StudyPlanVersionRead(
            id=version.id,
            version_number=version.version_number,
            status=version.status,
            generation_request_id=version.generation_request_id,
            replan_request_id=version.replan_request_id,
            publish_request_id=version.publish_request_id,
            parameters=version.parameters,
            diagnostic_session_id=version.diagnostic_session_id,
            required_minutes=version.required_minutes,
            available_minutes=version.available_minutes,
            gap_minutes=version.gap_minutes,
            conflicts=version.conflicts,
            suggestions=version.suggestions,
            quality_report=version.quality_report,
            reason=version.reason,
            published_at=version.published_at,
            stale_at=version.stale_at,
            stale_reason=version.stale_reason,
            stale_source_type=version.stale_source_type,
            stale_source_id=version.stale_source_id,
            created_at=version.created_at,
            items=[self._serialize_item(item) for item in items],
        )

    def serialize(self, plan: StudyPlan, *, idempotent_replay: bool = False) -> StudyPlanRead:
        goal = self.db.get(LearningGoal, plan.learning_goal_id)
        course = self.db.get(Course, plan.course_id)
        latest = self._version(plan, plan.current_version_number)
        active = self._version(plan, plan.active_version_number) if plan.active_version_number else None
        return StudyPlanRead(
            id=plan.id,
            public_id=plan.public_id,
            learning_goal_id=plan.learning_goal_id,
            learning_goal_title=goal.title if goal else "已删除目标",
            course_id=plan.course_id,
            course_title=course.title if course else "已删除课程",
            status=plan.status,
            version=plan.version,
            current_version_number=plan.current_version_number,
            active_version_number=plan.active_version_number,
            latest_version=self._serialize_version(latest),
            active_version=self._serialize_version(active) if active else None,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
            idempotent_replay=idempotent_replay,
        )
