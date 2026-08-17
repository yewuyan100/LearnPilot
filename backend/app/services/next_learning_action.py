from __future__ import annotations

import json
from hashlib import sha256

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.models import (
    Course,
    DailyTask,
    DiagnosticKnowledgeResult,
    DiagnosticSession,
    KnowledgeMastery,
    KnowledgePoint,
    LearningGoal,
    LearningProposal,
    LearningSession,
    NextActionAcceptance,
    ReviewSchedule,
    StudyPlan,
    StudyPlanItem,
    StudyPlanVersion,
    WrongAnswer,
)
from app.schemas.next_learning_action import (
    NextActionAcceptRequest,
    NextActionAcceptResponse,
    NextLearningActionRead,
)
from app.learning.lessons.validation import (
    lesson_url_for_session,
    resolve_session_lesson_version,
)


def _hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode()).hexdigest()


class NextLearningActionService:
    """Deterministic global priority policy over existing execution truth sources."""

    def __init__(self, db, settings, clock):
        self.db = db
        self.settings = settings
        self.clock = clock

    def get(self, available_minutes: int | None = None) -> NextLearningActionRead:
        action = (
            self._pending_plan_adjustment(available_minutes)
            or self._resume_session(available_minutes)
            or self._unfinished_diagnostic(available_minutes)
            or self._stale_plan(available_minutes)
            or self._due_review(available_minutes)
            or self._today_plan_item(available_minutes)
            or self._skill_gap(available_minutes)
            or self._ordinary_task(available_minutes)
            or self._replan(available_minutes)
        )
        return self._finalize(action, available_minutes)

    def _pending_plan_adjustment(self, available_minutes: int | None) -> dict | None:
        proposals = list(
            self.db.scalars(
                select(LearningProposal)
                .where(
                    LearningProposal.proposal_type == "plan_adjustment",
                    LearningProposal.status == "pending",
                )
                .order_by(LearningProposal.created_at.desc(), LearningProposal.id.desc())
            )
        )
        now = self.clock.now()
        for proposal in proposals:
            expires_at = proposal.expires_at
            if expires_at is not None:
                if expires_at.tzinfo is None and now.tzinfo is not None:
                    expires_at = expires_at.replace(tzinfo=now.tzinfo)
                if expires_at <= now:
                    continue
            summary = proposal.summary or {}
            plan = self.db.get(StudyPlan, int(proposal.target_id or 0))
            if plan is None or plan.status != "active":
                continue
            point = self.db.get(
                KnowledgePoint, int(summary.get("knowledge_point_id") or 0)
            )
            course = self.db.get(Course, plan.course_id)
            if (
                point is None
                or point.lifecycle_status != "active"
                or course is None
                or course.status != "active"
            ):
                continue
            return self._action(
                action_type="review_proposal",
                target_kind="learning_proposal",
                target_id=proposal.id,
                goal_id=plan.learning_goal_id,
                course=course,
                point=point,
                title=f"审查学习计划调整：{point.title}",
                reason_code="pending_plan_adjustment",
                reason=str(summary.get("reason") or proposal.rationale),
                priority=100,
                minutes=0,
                cta_label="审查调整",
                cta_href=f"/plan-adjustments/{proposal.public_id}",
                plan_id=plan.id,
                state={
                    "proposal_id": proposal.public_id,
                    "proposal_status": proposal.status,
                    "proposal_version": proposal.version,
                    "expires_at": expires_at,
                },
            )
        return None

    def _finalize(self, action: dict, available_minutes: int | None) -> NextLearningActionRead:
        signature_state = action.pop("_signature_state", {})
        action["available_minutes"] = available_minutes
        action["action_signature"] = _hash(
            {
                "action_type": action["action_type"],
                "target_kind": action["target_kind"],
                "target_id": action["target_id"],
                "plan_id": action.get("plan_id"),
                "plan_item_id": action.get("plan_item_id"),
                "available_minutes": available_minutes,
                "state": signature_state,
            }
        )
        return NextLearningActionRead.model_validate(action)

    def _resume_session(self, available_minutes: int | None) -> dict | None:
        sessions = list(
            self.db.scalars(
                select(LearningSession)
                .where(
                    LearningSession.status.in_(("active", "paused")),
                    LearningSession.invalidated_at.is_(None),
                )
                .order_by(LearningSession.started_at.desc(), LearningSession.id.desc())
            )
        )
        for session in sessions:
            task = self.db.get(DailyTask, session.daily_task_id) if session.daily_task_id else None
            course = self.db.get(Course, session.course_id) if session.course_id else None
            if task and task.status in {"completed", "skipped"}:
                continue
            if task and task.blocked_at is not None:
                continue
            if course and course.status != "active":
                continue
            point = self.db.get(KnowledgePoint, session.knowledge_point_id) if session.knowledge_point_id else None
            if session.knowledge_point_id and (
                point is None or point.lifecycle_status != "active"
            ):
                continue
            minutes = task.estimated_minutes if task else 0
            return self._action(
                action_type="resume_session",
                target_kind="learning_session",
                target_id=session.id,
                goal_id=session.learning_goal_id,
                course=course,
                point=point,
                title=task.title if task else "继续未完成的学习",
                reason_code="unfinished_session",
                reason="已有学习会话尚未结束，先恢复现场可以避免丢失当前进度。",
                priority=100,
                minutes=minutes,
                cta_label="继续学习",
                cta_href=f"/learning-sessions/{session.id}",
                state={
                    "session_status": session.status,
                    "session_updated_at": session.updated_at,
                    "task_status": task.status if task else None,
                    "task_updated_at": task.updated_at if task else None,
                },
            )
        return None

    def _stale_plan(self, available_minutes: int | None) -> dict | None:
        plan, version = self._active_plan()
        if plan is None or version is None or version.stale_at is None:
            return None
        goal = self.db.get(LearningGoal, plan.learning_goal_id)
        course = self.db.get(Course, plan.course_id)
        return self._action(
            action_type="replan_required",
            target_kind="study_plan",
            target_id=plan.id,
            goal_id=goal.id if goal else plan.learning_goal_id,
            course=course,
            point=None,
            title="调整学习计划",
            reason_code="study_plan_stale",
            reason=version.stale_reason or "课程内容已变化，需要重新生成学习计划。",
            priority=85,
            minutes=0,
            cta_label="调整计划",
            cta_href="/goals",
            plan_id=plan.id,
            state={
                "plan_version": plan.version,
                "active_version": plan.active_version_number,
                "stale_at": version.stale_at,
                "stale_source_type": version.stale_source_type,
                "stale_source_id": version.stale_source_id,
            },
        )

    def _unfinished_diagnostic(self, available_minutes: int | None) -> dict | None:
        rows = list(
            self.db.scalars(
                select(DiagnosticSession)
                .where(DiagnosticSession.status == "pending")
                .order_by(DiagnosticSession.created_at.desc(), DiagnosticSession.id.desc())
            )
        )
        for diagnostic in rows:
            course = self.db.get(Course, diagnostic.course_id)
            if course is None or course.status != "active":
                continue
            return self._action(
                action_type="complete_assessment",
                target_kind="diagnostic_session",
                target_id=diagnostic.id,
                goal_id=course.learning_goal_id,
                course=course,
                point=None,
                title=f"完成《{course.title}》初始诊断",
                reason_code="unfinished_diagnostic",
                reason="这份诊断已生成但尚未提交；完成后才能形成可靠的能力基线。",
                priority=90,
                minutes=15,
                cta_label="继续诊断",
                cta_href=f"/courses?course_id={course.id}&diagnostic_id={diagnostic.id}",
                state={"diagnostic_status": diagnostic.status, "version": diagnostic.version},
            )
        return None

    def _due_review(self, available_minutes: int | None) -> dict | None:
        if available_minutes is not None and available_minutes < 10:
            return None
        rows = list(
            self.db.scalars(
                select(ReviewSchedule)
                .where(
                    ReviewSchedule.status.in_(("pending", "scheduled")),
                    ReviewSchedule.due_at <= self.clock.now(),
                )
                .order_by(
                    ReviewSchedule.priority_score.desc(),
                    ReviewSchedule.due_at,
                    ReviewSchedule.id,
                )
            )
        )
        for review in rows:
            point = self.db.get(KnowledgePoint, review.knowledge_point_id)
            course = self.db.get(Course, point.course_id) if point else None
            if (
                point is None
                or point.lifecycle_status != "active"
                or course is None
                or course.status != "active"
            ):
                continue
            task = self.db.scalar(
                select(DailyTask)
                .where(
                    DailyTask.knowledge_point_id == point.id,
                    DailyTask.task_type == "review",
                    DailyTask.status.in_(("pending", "in_progress")),
                    DailyTask.blocked_at.is_(None),
                )
                .order_by(DailyTask.scheduled_date, DailyTask.id)
            )
            return self._action(
                action_type="review",
                target_kind="daily_task" if task else "review_schedule",
                target_id=task.id if task else review.id,
                goal_id=course.learning_goal_id,
                course=course,
                point=point,
                title=task.title if task else f"复习：{point.title}",
                reason_code="critical_review_due",
                reason=f"复习已到期；{review.reason_summary}",
                priority=80,
                minutes=task.estimated_minutes if task else 20,
                cta_label="开始复习",
                cta_href="/today",
                due_review=True,
                state={
                    "review_id": review.id,
                    "review_status": review.status,
                    "review_due_at": review.due_at,
                    "task_status": task.status if task else None,
                    "task_updated_at": task.updated_at if task else None,
                },
            )
        return None

    def _active_plan(self) -> tuple[StudyPlan | None, StudyPlanVersion | None]:
        plan = self.db.scalar(
            select(StudyPlan)
            .where(StudyPlan.status == "active")
            .order_by(StudyPlan.updated_at.desc(), StudyPlan.id.desc())
        )
        if plan is None or plan.active_version_number is None:
            return None, None
        version = self.db.scalar(
            select(StudyPlanVersion).where(
                StudyPlanVersion.study_plan_id == plan.id,
                StudyPlanVersion.version_number == plan.active_version_number,
                StudyPlanVersion.status == "active",
            )
        )
        return plan, version

    def _today_plan_item(self, available_minutes: int | None) -> dict | None:
        plan, version = self._active_plan()
        if plan is None or version is None:
            return None
        if version.stale_at is not None:
            return None
        all_items = list(
            self.db.scalars(
                select(StudyPlanItem)
                .where(StudyPlanItem.study_plan_version_id == version.id)
                .order_by(StudyPlanItem.order_index)
            )
        )
        for item in all_items:
            if item.scheduled_date != self.clock.today() or item.daily_task_id is None:
                continue
            task = self.db.get(DailyTask, item.daily_task_id)
            if (
                task is None
                or task.status not in {"pending", "in_progress"}
                or task.blocked_at is not None
            ):
                continue
            if available_minutes is not None and task.estimated_minutes > available_minutes:
                continue
            if not self._prerequisites_satisfied(item, all_items):
                continue
            course = self.db.get(Course, item.course_id)
            point = self.db.get(KnowledgePoint, item.knowledge_point_id) if item.knowledge_point_id else None
            if (
                course is None
                or course.status != "active"
                or point is None
                or point.lifecycle_status != "active"
            ):
                continue
            action_type = self._task_action_type(task)
            return self._action(
                action_type=action_type,
                target_kind="daily_task",
                target_id=task.id,
                goal_id=item.learning_goal_id,
                course=course,
                point=point,
                title=task.title,
                reason_code="today_formal_plan",
                reason=f"这是当前正式计划中今天最先满足前置条件的任务；{item.scheduling_reason}",
                priority=70,
                minutes=task.estimated_minutes,
                cta_label="开始任务" if task.status == "pending" else "继续任务",
                cta_href="/today",
                formal_plan=True,
                due_review=item.is_due_review,
                plan_id=plan.id,
                plan_item_id=item.id,
                state={
                    "plan_version": plan.version,
                    "active_version": plan.active_version_number,
                    "task_status": task.status,
                    "task_updated_at": task.updated_at,
                },
            )
        return None

    def _prerequisites_satisfied(
        self, item: StudyPlanItem, all_items: list[StudyPlanItem]
    ) -> bool:
        for point_id in item.prerequisite_ids:
            point = self.db.get(KnowledgePoint, point_id)
            if (
                point
                and point.lifecycle_status == "active"
                and point.status == "completed"
            ):
                continue
            if point is None or point.lifecycle_status != "active":
                return False
            prerequisite_items = [
                candidate
                for candidate in all_items
                if candidate.knowledge_point_id == point_id and not candidate.is_due_review
            ]
            if not prerequisite_items:
                return False
            tasks = [
                self.db.get(DailyTask, candidate.daily_task_id)
                for candidate in prerequisite_items
                if candidate.daily_task_id
            ]
            if len(tasks) != len(prerequisite_items) or any(
                task is None or task.status != "completed" for task in tasks
            ):
                return False
        return True

    def _skill_gap(self, available_minutes: int | None) -> dict | None:
        if available_minutes is not None and available_minutes < 10:
            return None
        sessions = list(
            self.db.scalars(
                select(DiagnosticSession)
                .where(
                    DiagnosticSession.status.in_(
                        ("submitted", "review_required", "evidence_insufficient")
                    )
                )
                .order_by(DiagnosticSession.submitted_at.desc(), DiagnosticSession.id.desc())
            )
        )
        latest_by_course: dict[int, DiagnosticSession] = {}
        for session in sessions:
            latest_by_course.setdefault(session.course_id, session)
        results: list[DiagnosticKnowledgeResult] = []
        for session in latest_by_course.values():
            results.extend(
                self.db.scalars(
                    select(DiagnosticKnowledgeResult).where(
                        DiagnosticKnowledgeResult.diagnostic_session_id == session.id,
                        DiagnosticKnowledgeResult.is_skill_gap.is_(True),
                        DiagnosticKnowledgeResult.evidence_insufficient.is_(False),
                    )
                )
            )
        results.sort(key=lambda result: (-result.priority, result.knowledge_point_id))
        for gap in results:
            point = self.db.get(KnowledgePoint, gap.knowledge_point_id)
            course = self.db.get(Course, point.course_id) if point else None
            if (
                point is None
                or point.lifecycle_status != "active"
                or course is None
                or course.status != "active"
            ):
                continue
            task = self.db.scalar(
                select(DailyTask)
                .where(
                    DailyTask.knowledge_point_id == point.id,
                    DailyTask.status.in_(("pending", "in_progress")),
                    DailyTask.scheduled_date <= self.clock.today(),
                    DailyTask.blocked_at.is_(None),
                )
                .order_by(DailyTask.scheduled_date, DailyTask.id)
            )
            minutes = task.estimated_minutes if task else min(20, point.estimated_minutes)
            if available_minutes is not None and minutes > available_minutes:
                continue
            wrong_count = self.db.scalar(
                select(func.count())
                .select_from(WrongAnswer)
                .where(
                    WrongAnswer.knowledge_point_id == point.id,
                    WrongAnswer.status == "active",
                )
            ) or 0
            mastery = self.db.scalar(
                select(KnowledgeMastery).where(KnowledgeMastery.knowledge_point_id == point.id)
            )
            evidence = []
            if wrong_count:
                evidence.append(f"仍有 {wrong_count} 道活跃错题")
            if mastery and mastery.mastery_level in {"beginner", "developing"}:
                evidence.append(f"当前掌握等级为 {mastery.mastery_level}")
            suffix = f"；{'，'.join(evidence)}" if evidence else ""
            return self._action(
                action_type="practice" if wrong_count else "learn",
                target_kind="daily_task" if task else "knowledge_point",
                target_id=task.id if task else point.id,
                goal_id=course.learning_goal_id,
                course=course,
                point=point,
                title=task.title if task else f"补强：{point.title}",
                reason_code="diagnostic_skill_gap",
                reason=f"最近一次诊断将该知识点识别为高优先级技能缺口{suffix}。",
                priority=60,
                minutes=minutes,
                cta_label="开始练习" if wrong_count else "开始学习",
                cta_href="/today",
                state={
                    "diagnostic_result_id": gap.id,
                    "diagnostic_result_version": gap.version,
                    "task_status": task.status if task else None,
                    "wrong_count": wrong_count,
                    "mastery_updated_at": mastery.updated_at if mastery else None,
                },
            )
        return None

    def _ordinary_task(self, available_minutes: int | None) -> dict | None:
        tasks = list(
            self.db.scalars(
                select(DailyTask)
                .where(
                    DailyTask.status.in_(("pending", "in_progress")),
                    DailyTask.scheduled_date <= self.clock.today(),
                    DailyTask.blocked_at.is_(None),
                )
                .order_by(DailyTask.scheduled_date, DailyTask.id)
            )
        )
        for task in tasks:
            if available_minutes is not None and task.estimated_minutes > available_minutes:
                continue
            course = self.db.get(Course, task.course_id) if task.course_id else None
            if course and course.status != "active":
                continue
            point = self.db.get(KnowledgePoint, task.knowledge_point_id) if task.knowledge_point_id else None
            if task.knowledge_point_id and (
                point is None or point.lifecycle_status != "active"
            ):
                continue
            action_type = self._task_action_type(task)
            return self._action(
                action_type=action_type,
                target_kind="daily_task",
                target_id=task.id,
                goal_id=task.learning_goal_id,
                course=course,
                point=point,
                title=task.title,
                reason_code="pending_daily_task",
                reason="这是当前日期之前仍未完成、且符合可用时间的最早任务。",
                priority=50,
                minutes=task.estimated_minutes,
                cta_label="开始任务" if task.status == "pending" else "继续任务",
                cta_href="/today",
                due_review=task.task_type == "review",
                state={"task_status": task.status, "task_updated_at": task.updated_at},
            )
        return None

    def _replan(self, available_minutes: int | None) -> dict:
        plan, _ = self._active_plan()
        goal = None
        course = None
        if plan:
            goal = self.db.get(LearningGoal, plan.learning_goal_id)
            course = self.db.get(Course, plan.course_id)
            reason = "当前正式计划没有可立即执行的任务，请检查可用时间、前置条件或发起重新规划。"
        else:
            goal = self.db.scalar(
                select(LearningGoal)
                .where(LearningGoal.status == "active")
                .order_by(LearningGoal.updated_at.desc(), LearningGoal.id.desc())
            )
            reason = "当前没有可执行任务或生效计划，请先生成并确认一份学习计划。"
        return self._action(
            action_type="replan_required",
            target_kind="study_plan" if plan else "learning_goal",
            target_id=plan.id if plan else (goal.id if goal else None),
            goal_id=goal.id if goal else None,
            course=course,
            point=None,
            title="调整学习计划" if plan else "创建学习计划",
            reason_code="no_executable_action",
            reason=reason,
            priority=10,
            minutes=0,
            cta_label="调整计划" if plan else "制定计划",
            cta_href="/goals",
            plan_id=plan.id if plan else None,
            state={
                "plan_version": plan.version if plan else None,
                "plan_status": plan.status if plan else None,
                "goal_updated_at": goal.updated_at if goal else None,
            },
        )

    @staticmethod
    def _task_action_type(task: DailyTask) -> str:
        if task.task_type == "review":
            return "review"
        if task.task_type in {"practice", "quick_verify", "quiz", "assessment"}:
            return "practice"
        return "learn"

    @staticmethod
    def _action(
        *,
        action_type: str,
        target_kind: str,
        target_id: int | None,
        goal_id: int | None,
        course: Course | None,
        point: KnowledgePoint | None,
        title: str,
        reason_code: str,
        reason: str,
        priority: int,
        minutes: int,
        cta_label: str,
        cta_href: str,
        formal_plan: bool = False,
        due_review: bool = False,
        plan_id: int | None = None,
        plan_item_id: int | None = None,
        state: dict | None = None,
    ) -> dict:
        return {
            "action_type": action_type,
            "target_kind": target_kind,
            "target_id": target_id,
            "learning_goal_id": goal_id,
            "course_id": course.id if course else None,
            "course_title": course.title if course else None,
            "knowledge_point_id": point.id if point else None,
            "knowledge_point_title": point.title if point else None,
            "title": title,
            "reason_code": reason_code,
            "reason": reason,
            "priority": priority,
            "estimated_minutes": max(0, minutes),
            "from_formal_plan": formal_plan,
            "is_due_review": due_review,
            "plan_id": plan_id,
            "plan_item_id": plan_item_id,
            "cta_label": cta_label,
            "cta_href": cta_href,
            "_signature_state": state or {},
        }

    def accept(self, payload: NextActionAcceptRequest) -> NextActionAcceptResponse:
        replay = self.db.scalar(
            select(NextActionAcceptance).where(
                NextActionAcceptance.request_id == payload.request_id
            )
        )
        if replay:
            if replay.action_signature != payload.action_signature:
                raise AppError(
                    "next_action_request_conflict",
                    "相同 request_id 已用于另一项建议",
                    status.HTTP_409_CONFLICT,
                )
            return self._accepted_response(replay, idempotent_replay=True)

        action = self.get(payload.available_minutes)
        if action.action_signature != payload.action_signature:
            raise AppError(
                "next_action_stale",
                "建议所依据的学习状态已经变化，请刷新后重试",
                status.HTTP_409_CONFLICT,
            )
        try:
            outcome = self._apply(action)
            acceptance = NextActionAcceptance(
                request_id=payload.request_id,
                action_signature=action.action_signature,
                action_type=action.action_type,
                original_target_kind=action.target_kind,
                original_target_id=action.target_id,
                outcome={"action": action.model_dump(mode="json"), **outcome},
                accepted_at=self.clock.now(),
            )
            self.db.add(acceptance)
            self.db.commit()
            return self._accepted_response(acceptance)
        except IntegrityError as exc:
            self.db.rollback()
            replay = self.db.scalar(
                select(NextActionAcceptance).where(
                    NextActionAcceptance.request_id == payload.request_id
                )
            )
            if replay and replay.action_signature == payload.action_signature:
                return self._accepted_response(replay, idempotent_replay=True)
            raise AppError(
                "next_action_accept_conflict",
                "建议接受发生并发冲突，请重放原请求",
                status.HTTP_409_CONFLICT,
            ) from exc
        except AppError:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            raise AppError(
                "next_action_accept_failed",
                "建议暂时无法执行，本次变更已回滚",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                {"reason": type(exc).__name__},
            ) from exc

    def _apply(self, action: NextLearningActionRead) -> dict:
        if action.action_type == "resume_session":
            session = self.db.get(LearningSession, action.target_id)
            if (
                session is None
                or session.status not in {"active", "paused"}
                or session.invalidated_at is not None
            ):
                raise AppError(
                    "next_action_target_stale",
                    "学习会话已结束，请刷新建议",
                    status.HTTP_409_CONFLICT,
                )
            return self._outcome(
                "learning_session",
                session.id,
                lesson_url_for_session(self.db, session),
                session.daily_task_id,
                session.id,
            )
        if action.action_type == "complete_assessment":
            diagnostic = self.db.get(DiagnosticSession, action.target_id)
            if diagnostic is None or diagnostic.status != "pending":
                raise AppError(
                    "next_action_target_stale",
                    "诊断状态已经变化，请刷新建议",
                    status.HTTP_409_CONFLICT,
                )
            return self._outcome(
                "diagnostic_session", diagnostic.id, action.cta_href, None, None
            )
        if action.action_type == "replan_required":
            return self._outcome(
                action.target_kind, action.target_id, action.cta_href, None, None
            )
        if action.action_type == "review_proposal":
            return self._outcome(
                action.target_kind, action.target_id, action.cta_href, None, None
            )

        task = None
        if action.target_kind == "daily_task":
            task = self.db.get(DailyTask, action.target_id)
        elif action.target_kind == "review_schedule":
            task = self._task_for_review(action.target_id)
        elif action.target_kind == "knowledge_point":
            task = self._task_for_gap(action.target_id, action.action_type)
        if (
            task is None
            or task.status not in {"pending", "in_progress"}
            or task.blocked_at is not None
        ):
            raise AppError(
                "next_action_target_stale",
                "推荐任务已经不可执行，请刷新建议",
                status.HTTP_409_CONFLICT,
            )
        session = self.db.scalar(
            select(LearningSession)
            .where(
                LearningSession.daily_task_id == task.id,
                LearningSession.status.in_(("active", "paused")),
                LearningSession.invalidated_at.is_(None),
            )
            .order_by(LearningSession.started_at.desc(), LearningSession.id.desc())
        )
        if session is None:
            lesson_version = resolve_session_lesson_version(
                self.db,
                course_id=task.course_id,
                knowledge_point_id=task.knowledge_point_id,
                lesson_version_id=None,
            )
            session = LearningSession(
                learning_goal_id=task.learning_goal_id,
                course_id=task.course_id,
                knowledge_point_id=task.knowledge_point_id,
                daily_task_id=task.id,
                lesson_version_id=lesson_version.id if lesson_version else None,
                started_at=self.clock.now(),
                status="active",
                notes="",
            )
            self.db.add(session)
            self.db.flush()
        task.status = "in_progress"
        return self._outcome(
            "learning_session",
            session.id,
            lesson_url_for_session(self.db, session),
            task.id,
            session.id,
        )

    def _task_for_review(self, review_id: int | None) -> DailyTask:
        review = self.db.get(ReviewSchedule, review_id)
        if review is None or review.status not in {"pending", "scheduled"}:
            raise AppError(
                "next_action_target_stale", "复习项已经变化", status.HTTP_409_CONFLICT
            )
        point = self.db.get(KnowledgePoint, review.knowledge_point_id)
        course = self.db.get(Course, point.course_id) if point else None
        if (
            point is None
            or point.lifecycle_status != "active"
            or course is None
            or course.status != "active"
        ):
            raise AppError(
                "next_action_target_unavailable",
                "复习对应的课程已不可用",
                status.HTTP_409_CONFLICT,
            )
        task = self.db.scalar(
            select(DailyTask)
            .where(
                DailyTask.knowledge_point_id == point.id,
                DailyTask.task_type == "review",
                DailyTask.status.in_(("pending", "in_progress")),
                DailyTask.blocked_at.is_(None),
            )
            .order_by(DailyTask.scheduled_date, DailyTask.id)
        )
        if task:
            task.scheduled_date = self.clock.today()
            return task
        task = DailyTask(
            learning_goal_id=course.learning_goal_id,
            course_id=course.id,
            knowledge_point_id=point.id,
            title=f"复习：{point.title}",
            task_type="review",
            estimated_minutes=20,
            scheduled_date=self.clock.today(),
            status="pending",
        )
        self.db.add(task)
        self.db.flush()
        return task

    def _task_for_gap(self, point_id: int | None, action_type: str) -> DailyTask:
        point = self.db.get(KnowledgePoint, point_id)
        course = self.db.get(Course, point.course_id) if point else None
        if (
            point is None
            or point.lifecycle_status != "active"
            or course is None
            or course.status != "active"
        ):
            raise AppError(
                "next_action_target_unavailable",
                "技能缺口对应的课程已不可用",
                status.HTTP_409_CONFLICT,
            )
        task = self.db.scalar(
            select(DailyTask)
            .where(
                DailyTask.knowledge_point_id == point.id,
                DailyTask.status.in_(("pending", "in_progress")),
                DailyTask.scheduled_date <= self.clock.today(),
                DailyTask.blocked_at.is_(None),
            )
            .order_by(DailyTask.scheduled_date, DailyTask.id)
        )
        if task:
            return task
        task = DailyTask(
            learning_goal_id=course.learning_goal_id,
            course_id=course.id,
            knowledge_point_id=point.id,
            title=f"{'练习' if action_type == 'practice' else '学习'}：{point.title}",
            task_type=action_type,
            estimated_minutes=min(20, point.estimated_minutes),
            scheduled_date=self.clock.today(),
            status="pending",
        )
        self.db.add(task)
        self.db.flush()
        return task

    @staticmethod
    def _outcome(kind, object_id, url, task_id, session_id) -> dict:
        return {
            "outcome_kind": kind,
            "outcome_id": object_id,
            "next_url": url,
            "daily_task_id": task_id,
            "learning_session_id": session_id,
        }

    @staticmethod
    def _accepted_response(
        acceptance: NextActionAcceptance, *, idempotent_replay: bool = False
    ) -> NextActionAcceptResponse:
        outcome = acceptance.outcome
        return NextActionAcceptResponse(
            action=NextLearningActionRead.model_validate(outcome["action"]),
            outcome_kind=outcome["outcome_kind"],
            outcome_id=outcome.get("outcome_id"),
            next_url=outcome["next_url"],
            daily_task_id=outcome.get("daily_task_id"),
            learning_session_id=outcome.get("learning_session_id"),
            idempotent_replay=idempotent_replay,
        )
