from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from math import ceil

from sqlalchemy import select

from app.models import (
    DailyTask,
    DiagnosticKnowledgeResult,
    DiagnosticSession,
    KnowledgeMastery,
    KnowledgePoint,
    ReviewSchedule,
)
from app.services.course_state import CourseStateService


@dataclass
class PlannedItem:
    logical_key: str
    title: str
    activity_type: str
    minutes: int
    knowledge_point_id: int | None
    reason: str
    prerequisite_ids: list[int] = field(default_factory=list)
    is_due_review: bool = False
    review_schedule_id: int | None = None
    diagnostic_result_id: int | None = None
    daily_task_id: int | None = None
    scheduled_date: date | None = None


@dataclass
class PlanComputation:
    status: str
    study_dates: list[date]
    required_minutes: int
    available_minutes: int
    gap_minutes: int
    conflicts: list[dict]
    suggestions: list[dict]
    quality_report: dict
    items: list[PlannedItem]
    diagnostic_session_id: int | None


class DeterministicStudyScheduler:
    def __init__(self, db, clock):
        self.db = db
        self.clock = clock

    @staticmethod
    def _dates(parameters: dict) -> list[date]:
        current = date.fromisoformat(parameters["start_date"])
        target = date.fromisoformat(parameters["target_date"])
        allowed = set(parameters["available_weekdays"])
        dates: list[date] = []
        while current <= target:
            if current.weekday() in allowed:
                dates.append(current)
            current += timedelta(days=1)
        return dates

    @staticmethod
    def _split(total: int, cap: int) -> list[int]:
        if total <= cap:
            return [max(1, total)]
        count = ceil(total / cap)
        base, remainder = divmod(total, count)
        return [base + (1 if index < remainder else 0) for index in range(count)]

    def compute(
        self,
        *,
        course,
        points: list[KnowledgePoint],
        parameters: dict,
        movable_tasks: dict[str, DailyTask] | None = None,
        completed_logical_keys: set[str] | None = None,
    ) -> PlanComputation:
        movable_tasks = movable_tasks or {}
        completed_logical_keys = completed_logical_keys or set()
        study_dates = self._dates(parameters)
        daily_budget = int(parameters["daily_minutes"])
        conflicts: list[dict] = []
        suggestions: list[dict] = []
        if not study_dates:
            conflicts.append(
                {"code": "no_available_dates", "message": "日期范围内没有可学习日"}
            )
            return PlanComputation(
                "infeasible", [], 0, 0, 0, conflicts,
                [{"action": "change_available_weekdays", "message": "增加可学习日期"}],
                self._quality([], [], points, []), [], None,
            )

        latest_diagnostic = None
        diagnostic_results: dict[int, DiagnosticKnowledgeResult] = {}
        if parameters.get("use_latest_diagnostic"):
            latest_diagnostic = self.db.scalar(
                select(DiagnosticSession)
                .where(
                    DiagnosticSession.course_id == course.id,
                    DiagnosticSession.status.in_(("submitted", "review_required", "evidence_insufficient")),
                )
                .order_by(DiagnosticSession.submitted_at.desc(), DiagnosticSession.id.desc())
            )
            if latest_diagnostic:
                diagnostic_results = {
                    row.knowledge_point_id: row
                    for row in self.db.scalars(
                        select(DiagnosticKnowledgeResult).where(
                            DiagnosticKnowledgeResult.diagnostic_session_id == latest_diagnostic.id
                        )
                    )
                }
        masteries: dict[int, KnowledgeMastery] = {}
        if parameters.get("use_existing_mastery"):
            masteries = {
                row.knowledge_point_id: row
                for row in self.db.scalars(
                    select(KnowledgeMastery).where(
                        KnowledgeMastery.knowledge_point_id.in_([point.id for point in points])
                    )
                )
            }
        priority: dict[int, float] = {}
        for point in points:
            result = diagnostic_results.get(point.id)
            mastery = masteries.get(point.id)
            priority[point.id] = (
                (result.priority if result else 0)
                + (40 if result and result.is_skill_gap else 0)
                + (30 if mastery and mastery.mastery_level in {"beginner", "developing"} else 0)
            )
        ordered_ids = CourseStateService(self.db).topological_ids(points, priority)
        point_by_id = {point.id: point for point in points}
        edge_rows = CourseStateService(self.db).edges(points)
        prerequisites: dict[int, list[int]] = defaultdict(list)
        for edge in edge_rows:
            prerequisites[edge.dependent_knowledge_point_id].append(
                edge.prerequisite_knowledge_point_id
            )

        intensity = {"basic": 0.75, "standard": 1.0, "intensive": 1.25}[
            parameters["intensity"]
        ]
        candidates: list[PlannedItem] = []
        covered_completed_points: set[int] = set()
        for point_id in ordered_ids:
            point = point_by_id[point_id]
            mastery = masteries.get(point.id)
            result = diagnostic_results.get(point.id)
            if point.status == "completed":
                covered_completed_points.add(point.id)
                continue
            if mastery and mastery.mastery_level == "strong" and float(mastery.confidence_score) >= 60:
                total = min(10, daily_budget)
                activity_types = ["quick_verify"]
                reason = "现有证据显示已熟练，安排快速验证而不是重复学习"
            else:
                total = max(10, round(point.estimated_minutes * intensity))
                if result and result.is_skill_gap:
                    total = max(10, round(total * 1.5))
                    reason = "初始诊断识别为技能缺口，提高学习与练习优先级"
                elif mastery and mastery.mastery_level == "proficient":
                    total = max(10, round(total * 0.5))
                    reason = "现有掌握证据较强，缩短学习并保留验证"
                else:
                    reason = "按课程前置关系和预计耗时安排"
                activity_types = ["learn", "practice"] if total >= 20 else ["learn"]
            chunks = self._split(total, daily_budget)
            for index, minutes in enumerate(chunks):
                activity_type = activity_types[min(index, len(activity_types) - 1)]
                logical_key = f"point:{point.id}:{activity_type}:{index + 1}"
                if logical_key in completed_logical_keys:
                    covered_completed_points.add(point.id)
                    continue
                movable = movable_tasks.get(logical_key)
                candidates.append(
                    PlannedItem(
                        logical_key=logical_key,
                        title=f"{activity_type == 'practice' and '练习' or activity_type == 'quick_verify' and '快速验证' or '学习'}：{point.title}",
                        activity_type=activity_type,
                        minutes=minutes,
                        knowledge_point_id=point.id,
                        reason=reason,
                        prerequisite_ids=sorted(prerequisites.get(point.id, [])),
                        diagnostic_result_id=result.id if result else None,
                        daily_task_id=movable.id if movable else None,
                    )
                )

        if parameters.get("include_due_reviews"):
            due_reviews = list(
                self.db.scalars(
                    select(ReviewSchedule)
                    .where(
                        ReviewSchedule.knowledge_point_id.in_([point.id for point in points]),
                        ReviewSchedule.status.in_(("pending", "scheduled")),
                        ReviewSchedule.due_at
                        <= datetime.combine(
                            date.fromisoformat(parameters["target_date"]), time.max
                        ),
                    )
                    .order_by(ReviewSchedule.due_at, ReviewSchedule.priority_score.desc())
                )
            )
            target_date = date.fromisoformat(parameters["target_date"])
            for review in due_reviews:
                due_date = review.due_at.date()
                if due_date > target_date:
                    continue
                logical_key = f"review:{review.id}"
                if logical_key in completed_logical_keys:
                    continue
                movable = movable_tasks.get(logical_key)
                point = point_by_id.get(review.knowledge_point_id)
                candidates.insert(
                    0,
                    PlannedItem(
                        logical_key=logical_key,
                        title=f"到期复习：{point.title if point else '知识点'}",
                        activity_type="review",
                        minutes=min(20, daily_budget),
                        knowledge_point_id=review.knowledge_point_id,
                        reason=review.reason_summary,
                        is_due_review=True,
                        review_schedule_id=review.id,
                        daily_task_id=movable.id if movable else None,
                    ),
                )

        date_set = set(study_dates)
        movable_ids = {task.id for task in movable_tasks.values()}
        existing = list(
            self.db.scalars(
                select(DailyTask).where(
                    DailyTask.learning_goal_id == course.learning_goal_id,
                    DailyTask.status.in_(("pending", "in_progress")),
                    DailyTask.scheduled_date >= date.fromisoformat(parameters["start_date"]),
                    DailyTask.scheduled_date <= date.fromisoformat(parameters["target_date"]),
                )
            )
        )
        fixed_tasks = [task for task in existing if task.id not in movable_ids]
        fixed_items: list[PlannedItem] = []
        used_candidate_indexes: set[int] = set()
        for task in fixed_tasks:
            match_index = next(
                (
                    index for index, item in enumerate(candidates)
                    if index not in used_candidate_indexes
                    and item.knowledge_point_id is not None
                    and item.knowledge_point_id == task.knowledge_point_id
                    and item.daily_task_id is None
                ),
                None,
            )
            if match_index is not None:
                item = candidates[match_index]
                used_candidate_indexes.add(match_index)
                item.daily_task_id = task.id
                item.scheduled_date = task.scheduled_date
                item.minutes = task.estimated_minutes
                item.reason = "复用现有未完成 DailyTask；其执行状态保持不变"
                fixed_items.append(item)
            else:
                fixed_items.append(
                    PlannedItem(
                        logical_key=f"existing-task:{task.id}",
                        title=task.title,
                        activity_type=task.task_type,
                        minutes=task.estimated_minutes,
                        knowledge_point_id=task.knowledge_point_id,
                        reason="现有未完成任务占用学习预算",
                        daily_task_id=task.id,
                        scheduled_date=task.scheduled_date,
                    )
                )
        unscheduled = [
            item for index, item in enumerate(candidates) if index not in used_candidate_indexes
        ]
        usage: dict[date, int] = defaultdict(int)
        for item in fixed_items:
            if item.scheduled_date not in date_set:
                conflicts.append(
                    {
                        "code": "existing_task_on_unavailable_date",
                        "daily_task_id": item.daily_task_id,
                        "scheduled_date": item.scheduled_date.isoformat(),
                    }
                )
            usage[item.scheduled_date] += item.minutes
        overloaded = [day for day, minutes in usage.items() if minutes > daily_budget]
        if overloaded:
            conflicts.append(
                {
                    "code": "existing_tasks_over_capacity",
                    "dates": [day.isoformat() for day in overloaded],
                    "message": "现有任务已超过部分日期的每日预算",
                }
            )
        available_minutes = len(study_dates) * daily_budget
        required_minutes = sum(item.minutes for item in fixed_items + unscheduled)
        gap = max(0, required_minutes - available_minutes)
        if gap:
            conflicts.append(
                {
                    "code": "total_time_insufficient",
                    "required_minutes": required_minutes,
                    "available_minutes": available_minutes,
                    "gap_minutes": gap,
                    "message": "当前日期范围和每日预算不足以覆盖计划",
                }
            )
            suggestions.extend(
                [
                    {"action": "extend_target_date", "message": "延长截止日期"},
                    {"action": "increase_daily_minutes", "message": "增加每日学习时间"},
                    {"action": "reduce_scope", "message": "减少课程范围或先生成第一阶段"},
                    {"action": "lower_intensity", "message": "降低学习强度"},
                ]
            )
        if conflicts:
            quality = self._quality([], study_dates, points, edge_rows)
            return PlanComputation(
                "infeasible", study_dates, required_minutes, available_minutes, gap,
                conflicts, suggestions, quality, [], latest_diagnostic.id if latest_diagnostic else None,
            )

        scheduled: list[PlannedItem] = list(fixed_items)
        previous_point_date_index = 0
        for item in unscheduled:
            start_index = 0 if item.is_due_review else previous_point_date_index
            placed = False
            for index in range(start_index, len(study_dates)):
                day = study_dates[index]
                if usage[day] + item.minutes <= daily_budget:
                    item.scheduled_date = day
                    usage[day] += item.minutes
                    scheduled.append(item)
                    if not item.is_due_review:
                        previous_point_date_index = index
                    placed = True
                    break
            if not placed:
                conflicts.append(
                    {"code": "daily_capacity_exhausted", "logical_key": item.logical_key}
                )
                break
        if conflicts:
            return PlanComputation(
                "infeasible", study_dates, required_minutes, available_minutes,
                max(1, required_minutes - sum(usage.values())), conflicts,
                [{"action": "increase_daily_minutes", "message": "增加每日学习时间或延长截止日期"}],
                self._quality([], study_dates, points, edge_rows), [],
                latest_diagnostic.id if latest_diagnostic else None,
            )
        # Python's sort is stable: within the same date keep the scheduler's
        # prerequisite/diagnostic priority order instead of re-sorting by ids.
        scheduled.sort(key=lambda item: (item.scheduled_date, item.is_due_review is False))
        quality = self._quality(scheduled, study_dates, points, edge_rows, covered_completed_points)
        quality["time_budget_constraint_rate"] = 1.0
        if quality["prerequisite_constraint_rate"] < 1.0:
            conflicts.append(
                {
                    "code": "prerequisite_order_violation",
                    "message": "现有任务位置与课程前置关系冲突，不能发布该计划",
                }
            )
        if quality["available_date_constraint_rate"] < 1.0:
            conflicts.append(
                {
                    "code": "unavailable_date_violation",
                    "message": "计划包含不可学习日期，不能发布该计划",
                }
            )
        if quality["duplicate_task_count"]:
            conflicts.append(
                {
                    "code": "duplicate_plan_items",
                    "count": quality["duplicate_task_count"],
                    "message": "计划包含重复任务，不能发布该计划",
                }
            )
        if quality["uncovered_required_knowledge_point_ids"]:
            conflicts.append(
                {
                    "code": "knowledge_coverage_incomplete",
                    "knowledge_point_ids": quality["uncovered_required_knowledge_point_ids"],
                    "message": "计划未覆盖全部必需知识点，不能发布该计划",
                }
            )
        if conflicts:
            return PlanComputation(
                "infeasible",
                study_dates,
                required_minutes,
                available_minutes,
                0,
                conflicts,
                [
                    {
                        "action": "reschedule_existing_tasks",
                        "message": "先调整冲突中的现有任务，再重新生成计划",
                    }
                ],
                quality,
                [],
                latest_diagnostic.id if latest_diagnostic else None,
            )
        return PlanComputation(
            "ready", study_dates, required_minutes, available_minutes, 0, [], [], quality,
            scheduled, latest_diagnostic.id if latest_diagnostic else None,
        )

    @staticmethod
    def _quality(
        items: list[PlannedItem],
        study_dates: list[date],
        points: list[KnowledgePoint],
        edges,
        completed_points: set[int] | None = None,
    ) -> dict:
        completed_points = completed_points or set()
        position = {}
        for index, item in enumerate(items):
            if item.knowledge_point_id is not None and not item.is_due_review:
                position.setdefault(item.knowledge_point_id, (item.scheduled_date, index))
        prerequisite_checks = []
        for edge in edges:
            prerequisite = edge.prerequisite_knowledge_point_id
            dependent = edge.dependent_knowledge_point_id
            satisfied = (
                prerequisite in completed_points
                or dependent not in position
                or prerequisite in position and position[prerequisite] <= position[dependent]
            )
            prerequisite_checks.append(satisfied)
        available = set(study_dates)
        eligible_points = {p.id for p in points if p.status != "completed"}
        covered = completed_points | {
            item.knowledge_point_id for item in items if item.knowledge_point_id is not None
        }
        duplicate_count = len(items) - len({item.logical_key for item in items})
        return {
            "prerequisite_constraint_rate": (
                sum(prerequisite_checks) / len(prerequisite_checks) if prerequisite_checks else 1.0
            ),
            "available_date_constraint_rate": (
                sum(item.scheduled_date in available for item in items) / len(items) if items else 1.0
            ),
            "duplicate_task_count": duplicate_count,
            "uncovered_required_knowledge_point_ids": sorted(eligible_points - covered),
        }
