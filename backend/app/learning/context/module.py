import json
from hashlib import sha256

from fastapi import status
from sqlalchemy import select

from app.core.errors import AppError
from app.learning.context.schemas import (
    ContextQuery,
    CourseContext,
    CurrentTaskContext,
    GoalContext,
    KnowledgePointContext,
    LearnerContext,
    LessonContext,
    LessonVersionContext,
    LearningSessionContext,
    MasterySummaryContext,
    MaterialReferenceContext,
    MaterialScopeContext,
    NextLearningActionContext,
    RecentLearningRecord,
    StudyPlanContext,
    WeakPointContext,
)
from app.models.course import Course
from app.models.daily_task import DailyTask
from app.models.knowledge_point import KnowledgePoint
from app.models.knowledge_mastery import KnowledgeMastery
from app.models.learning_goal import LearningGoal
from app.models.learning_session import LearningSession
from app.models.lesson import (
    Lesson,
    LessonSource,
    LessonVersion,
    LessonVersionKnowledgePoint,
)
from app.models.mastery_snapshot import MasterySnapshot
from app.models.material import Material
from app.models.study_plan import StudyPlan, StudyPlanVersion
from app.services.adaptive_learning.weak_points import WeakPointService
from app.services.material_learning import MaterialScopeResolver
from app.services.next_learning_action import NextLearningActionService


class LearnerContextModule:
    """Read-only projection Module for explicit surface context.

    Parent records may be followed through declared foreign keys. No missing or
    conflicting identifier is silently substituted.
    """

    def __init__(self, db, settings=None, clock=None):
        self.db = db
        self.settings = settings
        self.clock = clock

    @staticmethod
    def _json_value(value):
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, list):
            return [LearnerContextModule._json_value(item) for item in value]
        if isinstance(value, dict):
            return {
                key: LearnerContextModule._json_value(item)
                for key, item in value.items()
            }
        return value

    @staticmethod
    def _mismatch(message: str, **details) -> AppError:
        return AppError("context_mismatch", message, status.HTTP_409_CONFLICT, details or None)

    def _get(self, model, row_id: int | None, label: str):
        if row_id is None:
            return None
        row = self.db.get(model, row_id)
        if row is None:
            raise self._mismatch(f"Explicit {label} does not exist.", **{f"{label}_id": row_id})
        return row

    def _mastery_summary(self, point_id: int | None) -> MasterySummaryContext | None:
        if point_id is None:
            return None
        snapshot = self.db.scalar(
            select(MasterySnapshot)
            .where(MasterySnapshot.knowledge_point_id == point_id)
            .order_by(MasterySnapshot.calculated_at.desc(), MasterySnapshot.id.desc())
        )
        if snapshot is None:
            return None
        return MasterySummaryContext(
            knowledge_point_id=point_id,
            mastery_score=(
                float(snapshot.mastery_score) if snapshot.mastery_score is not None else None
            ),
            confidence_score=float(snapshot.confidence_score),
            mastery_level=snapshot.mastery_level,
            evidence_count=snapshot.evidence_count,
            calculated_at=snapshot.calculated_at,
        )

    def _recent_history(
        self, goal_id: int | None, course_id: int | None
    ) -> list[RecentLearningRecord]:
        if goal_id is None:
            return []
        query = select(LearningSession).where(LearningSession.learning_goal_id == goal_id)
        if course_id is not None:
            query = query.where(LearningSession.course_id == course_id)
        sessions = list(
            self.db.scalars(
                query.order_by(
                    LearningSession.started_at.desc(), LearningSession.id.desc()
                ).limit(5)
            )
        )
        point_ids = {item.knowledge_point_id for item in sessions if item.knowledge_point_id}
        points = {
            item.id: item.title
            for item in self.db.scalars(
                select(KnowledgePoint).where(KnowledgePoint.id.in_(point_ids))
            )
        } if point_ids else {}
        return [
            RecentLearningRecord(
                learning_session_id=item.id,
                knowledge_point_id=item.knowledge_point_id,
                knowledge_point_title=points.get(item.knowledge_point_id),
                status=item.status,
                started_at=item.started_at,
                ended_at=item.ended_at,
            )
            for item in sessions
        ]

    def _material_scope(
        self,
        goal_id: int | None,
        course_id: int | None,
        point_id: int | None,
        lesson_version_id: int | None,
    ) -> MaterialScopeContext:
        lesson_material_ids = None
        if lesson_version_id is not None:
            lesson_material_ids = list(
                self.db.scalars(
                    select(LessonSource.material_id).where(
                        LessonSource.lesson_version_id == lesson_version_id
                    )
                )
            )
        resolution = MaterialScopeResolver(self.db).resolve_combined_scope(
            learning_goal_id=goal_id,
            course_id=course_id,
            knowledge_point_id=point_id,
            material_ids=lesson_material_ids,
            searchable_only=True,
        )
        material_ids = resolution.resolved_material_ids or []
        rows = list(
            self.db.scalars(
                select(Material)
                .where(Material.id.in_(material_ids))
                .order_by(Material.updated_at.desc(), Material.id.desc())
            )
        ) if material_ids else []
        return MaterialScopeContext(
            requested_scope=resolution.requested_scope,
            material_ids=material_ids,
            materials=[
                MaterialReferenceContext(
                    material_id=item.id,
                    title=item.title,
                    original_filename=item.original_filename,
                    source_type=item.source_type,
                )
                for item in rows
            ],
            scoped=resolution.scoped,
            empty=resolution.empty,
        )

    def _weak_points(self, course_id: int | None) -> list[WeakPointContext]:
        if course_id is None:
            return []
        rows = self.db.execute(
            select(KnowledgeMastery, KnowledgePoint)
            .join(KnowledgePoint, KnowledgePoint.id == KnowledgeMastery.knowledge_point_id)
            .where(
                KnowledgePoint.course_id == course_id,
                KnowledgePoint.lifecycle_status == "active",
                KnowledgeMastery.mastery_score.is_not(None),
            )
        ).all()
        service = WeakPointService(
            self.db,
            now=self.clock.now() if self.clock is not None else None,
        )
        projected: list[WeakPointContext] = []
        for mastery, point in rows:
            facts = service.facts(mastery)
            weakness = float(facts["weakness_score"] or 0)
            if mastery.mastery_level not in {"beginner", "developing"} and weakness < 40:
                continue
            projected.append(
                WeakPointContext(
                    knowledge_point_id=point.id,
                    title=point.title,
                    mastery_level=mastery.mastery_level,
                    weakness_score=weakness,
                    recent_failure=bool(facts["recent_failure"]),
                    overdue=bool(facts["overdue"]),
                )
            )
        projected.sort(key=lambda item: (-item.weakness_score, item.knowledge_point_id))
        return projected[:3]

    def _current_task(self, session: LearningSession | None) -> CurrentTaskContext | None:
        if session is None or session.daily_task_id is None:
            return None
        task = self.db.get(DailyTask, session.daily_task_id)
        return CurrentTaskContext.model_validate(task, from_attributes=True) if task else None

    def _next_action(
        self,
        goal_id: int | None,
        course_id: int | None,
        point_id: int | None,
    ) -> NextLearningActionContext | None:
        if self.settings is None or self.clock is None:
            return None
        try:
            action = NextLearningActionService(self.db, self.settings, self.clock).get()
        except AppError:
            return None
        if goal_id is not None and action.learning_goal_id != goal_id:
            return None
        if course_id is not None and action.course_id not in {None, course_id}:
            return None
        if point_id is not None and action.knowledge_point_id not in {None, point_id}:
            return None
        return NextLearningActionContext(
            action_type=action.action_type,
            target_kind=action.target_kind,
            target_id=action.target_id,
            title=action.title,
            reason=action.reason,
            estimated_minutes=action.estimated_minutes,
        )

    def load(self, context_query: ContextQuery) -> LearnerContext:
        surface = context_query.surface_context
        session = self._get(LearningSession, surface.learning_session_id, "learning_session")

        effective_goal_id = surface.goal_id
        effective_course_id = surface.course_id
        effective_point_id = surface.knowledge_point_id
        effective_lesson_id = surface.lesson_id
        effective_lesson_version_id = surface.lesson_version_id

        if session is not None:
            if session.lesson_version_id is None and (
                surface.lesson_id is not None or surface.lesson_version_id is not None
            ):
                raise self._mismatch(
                    "A legacy learning session cannot be reinterpreted as a lesson session.",
                    learning_session_id=session.id,
                )
            expected = {
                "goal_id": session.learning_goal_id,
                "course_id": session.course_id,
                "knowledge_point_id": session.knowledge_point_id,
                "lesson_version_id": session.lesson_version_id,
            }
            supplied = {
                "goal_id": surface.goal_id,
                "course_id": surface.course_id,
                "knowledge_point_id": surface.knowledge_point_id,
                "lesson_version_id": surface.lesson_version_id,
            }
            conflicts = {
                key: {"supplied": supplied[key], "actual": actual}
                for key, actual in expected.items()
                if supplied[key] is not None and supplied[key] != actual
            }
            if conflicts:
                raise self._mismatch(
                    "The explicit learning session does not belong to the supplied context.",
                    conflicts=conflicts,
                )
            effective_goal_id = effective_goal_id or session.learning_goal_id
            effective_course_id = effective_course_id or session.course_id
            effective_point_id = effective_point_id or session.knowledge_point_id
            effective_lesson_version_id = (
                effective_lesson_version_id or session.lesson_version_id
            )

        lesson_version = self._get(
            LessonVersion,
            effective_lesson_version_id,
            "lesson_version",
        )
        if lesson_version is not None:
            if (
                effective_lesson_id is not None
                and lesson_version.lesson_id != effective_lesson_id
            ):
                raise self._mismatch(
                    "The explicit lesson version does not belong to the supplied lesson.",
                    lesson_version_id=lesson_version.id,
                    supplied_lesson_id=effective_lesson_id,
                    actual_lesson_id=lesson_version.lesson_id,
                )
            effective_lesson_id = effective_lesson_id or lesson_version.lesson_id

        lesson = self._get(Lesson, effective_lesson_id, "lesson")
        if lesson is not None:
            if effective_course_id is not None and lesson.course_id != effective_course_id:
                raise self._mismatch(
                    "The explicit lesson does not belong to the supplied course.",
                    lesson_id=lesson.id,
                    supplied_course_id=effective_course_id,
                    actual_course_id=lesson.course_id,
                )
            effective_course_id = effective_course_id or lesson.course_id
            if lesson_version is None and lesson.active_version_number is not None:
                lesson_version = self.db.scalar(
                    select(LessonVersion).where(
                        LessonVersion.lesson_id == lesson.id,
                        LessonVersion.version_number == lesson.active_version_number,
                    )
                )
                effective_lesson_version_id = lesson_version.id if lesson_version else None

        if lesson_version is not None:
            if effective_point_id is not None:
                relation = self.db.scalar(
                    select(LessonVersionKnowledgePoint).where(
                        LessonVersionKnowledgePoint.lesson_version_id == lesson_version.id,
                        LessonVersionKnowledgePoint.knowledge_point_id == effective_point_id,
                    )
                )
                if relation is None:
                    raise self._mismatch(
                        "The explicit knowledge point is not part of the supplied lesson version.",
                        lesson_version_id=lesson_version.id,
                        knowledge_point_id=effective_point_id,
                    )
            else:
                primary = self.db.scalar(
                    select(LessonVersionKnowledgePoint)
                    .where(
                        LessonVersionKnowledgePoint.lesson_version_id == lesson_version.id,
                        LessonVersionKnowledgePoint.role == "primary",
                    )
                    .order_by(LessonVersionKnowledgePoint.order_index)
                )
                effective_point_id = primary.knowledge_point_id if primary else None

        point = self._get(KnowledgePoint, effective_point_id, "knowledge_point")
        if point is not None:
            if effective_course_id is not None and point.course_id != effective_course_id:
                raise self._mismatch(
                    "The explicit knowledge point does not belong to the supplied course.",
                    knowledge_point_id=point.id,
                    supplied_course_id=effective_course_id,
                    actual_course_id=point.course_id,
                )
            effective_course_id = effective_course_id or point.course_id

        course = self._get(Course, effective_course_id, "course")
        if course is not None:
            if effective_goal_id is not None and course.learning_goal_id != effective_goal_id:
                raise self._mismatch(
                    "The explicit course does not belong to the supplied learning goal.",
                    course_id=course.id,
                    supplied_goal_id=effective_goal_id,
                    actual_goal_id=course.learning_goal_id,
                )
            effective_goal_id = effective_goal_id or course.learning_goal_id

        goal = self._get(LearningGoal, effective_goal_id, "goal")

        plan = None
        plan_version = None
        if goal is not None and course is not None:
            plan = self.db.scalar(
                select(StudyPlan)
                .where(
                    StudyPlan.learning_goal_id == goal.id,
                    StudyPlan.course_id == course.id,
                    StudyPlan.status == "active",
                )
                .order_by(StudyPlan.updated_at.desc(), StudyPlan.id.desc())
            )
            if plan is not None and plan.active_version_number is not None:
                plan_version = self.db.scalar(
                    select(StudyPlanVersion).where(
                        StudyPlanVersion.study_plan_id == plan.id,
                        StudyPlanVersion.version_number == plan.active_version_number,
                    )
                )

        goal_context = GoalContext.model_validate(goal, from_attributes=True) if goal else None
        course_context = CourseContext.model_validate(course, from_attributes=True) if course else None
        point_context = KnowledgePointContext.model_validate(point, from_attributes=True) if point else None
        session_context = (
            LearningSessionContext.model_validate(session, from_attributes=True) if session else None
        )
        lesson_context = (
            LessonContext.model_validate(lesson, from_attributes=True) if lesson else None
        )
        lesson_version_context = (
            LessonVersionContext.model_validate(lesson_version, from_attributes=True)
            if lesson_version
            else None
        )
        plan_context = None
        if plan is not None:
            plan_context = StudyPlanContext(
                id=plan.id,
                public_id=plan.public_id,
                status=plan.status,
                version=plan.version,
                active_version_number=plan.active_version_number,
                active_version_status=plan_version.status if plan_version else None,
                active_version_stale_at=plan_version.stale_at if plan_version else None,
                updated_at=plan.updated_at,
            )

        mastery_summary = self._mastery_summary(point.id if point else None)
        recent_learning_history = self._recent_history(
            goal.id if goal else None,
            course.id if course else None,
        )
        material_scope = self._material_scope(
            goal.id if goal else None,
            course.id if course else None,
            point.id if point else None,
            lesson_version.id if lesson_version else None,
        )
        weak_points = self._weak_points(course.id if course else None)
        current_task = self._current_task(session)
        next_learning_action = self._next_action(
            goal.id if goal else None,
            course.id if course else None,
            point.id if point else None,
        )

        invalid_reason = None
        if goal is not None and goal.status == "archived":
            invalid_reason = "goal_archived"
        elif course is not None and course.status == "archived":
            invalid_reason = "course_archived"
        elif point is not None and point.lifecycle_status != "active":
            invalid_reason = "knowledge_point_inactive"
        elif lesson is not None and lesson.status == "archived":
            invalid_reason = "lesson_archived"
        elif session is not None and session.invalidated_at is not None:
            invalid_reason = "learning_session_invalidated"

        version_source = {
            "goal": goal_context,
            "course": course_context,
            "knowledge_point": point_context,
            "study_plan": plan_context,
            "learning_session": session_context,
            "lesson": lesson_context,
            "lesson_version": lesson_version_context,
            "mastery_summary": mastery_summary,
            "recent_learning_history": recent_learning_history,
            "material_scope": material_scope,
            "weak_points": weak_points,
            "current_task": current_task,
            "next_learning_action": next_learning_action,
            "invalid_reason": invalid_reason,
        }
        canonical = json.dumps(
            {
                key: self._json_value(value)
                for key, value in version_source.items()
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        context_version = sha256(canonical.encode("utf-8")).hexdigest()
        return LearnerContext(
            actor_key=context_query.actor_key,
            goal=goal_context,
            course=course_context,
            knowledge_point=point_context,
            study_plan=plan_context,
            learning_session=session_context,
            lesson=lesson_context,
            lesson_version=lesson_version_context,
            mastery_summary=mastery_summary,
            recent_learning_history=recent_learning_history,
            material_scope=material_scope,
            weak_points=weak_points,
            current_task=current_task,
            next_learning_action=next_learning_action,
            context_version=context_version,
            valid=invalid_reason is None,
            invalid_reason=invalid_reason,
        )
