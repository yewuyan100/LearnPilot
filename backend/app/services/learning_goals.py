from __future__ import annotations

from dataclasses import dataclass

from fastapi import status
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.models import (
    AgentConversation,
    Course,
    DiagnosticSession,
    KnowledgePoint,
    KnowledgePointLifecycleChange,
    LearningGoal,
    LearningProposal,
    LearningSession,
    Lesson,
    MaterialLearningLink,
    NoteLink,
    StudyPlan,
)
from app.models.daily_task import DailyTask


@dataclass(frozen=True)
class LearningGoalDeleteReport:
    deleted: tuple[str, ...]
    preserved: tuple[str, ...]
    association_removed: tuple[str, ...]
    history_policy: str


class LearningGoalLifecycle:
    """Canonical item-deletion seam.

    Learning structure and execution records are item-owned. Materials, notes,
    practice/answer records, RAG answers, and Agent messages are independent
    user assets and survive after their item associations are removed or made
    non-resolvable.
    """

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _ids(rows) -> list[int]:
        return [int(value) for value in rows]

    def delete(self, goal_id: int) -> LearningGoalDeleteReport:
        goal = self.db.get(LearningGoal, goal_id)
        if goal is None:
            raise AppError(
                "learning_goal_not_found",
                "事项不存在",
                status.HTTP_404_NOT_FOUND,
                {"id": goal_id},
            )

        course_ids = self._ids(
            self.db.scalars(select(Course.id).where(Course.learning_goal_id == goal_id))
        )
        point_ids = self._ids(
            self.db.scalars(
                select(KnowledgePoint.id).where(KnowledgePoint.course_id.in_(course_ids))
            )
        ) if course_ids else []
        task_ids = self._ids(
            self.db.scalars(select(DailyTask.id).where(DailyTask.learning_goal_id == goal_id))
        )
        session_ids = self._ids(
            self.db.scalars(
                select(LearningSession.id).where(LearningSession.learning_goal_id == goal_id)
            )
        )
        lesson_ids = self._ids(
            self.db.scalars(select(Lesson.id).where(Lesson.course_id.in_(course_ids)))
        ) if course_ids else []
        diagnostic_ids = self._ids(
            self.db.scalars(
                select(DiagnosticSession.id).where(DiagnosticSession.course_id.in_(course_ids))
            )
        ) if course_ids else []
        plan_ids = self._ids(
            self.db.scalars(select(StudyPlan.id).where(StudyPlan.learning_goal_id == goal_id))
        )

        try:
            # Independent assets keep their content; only direct ownership links go away.
            self.db.execute(
                delete(MaterialLearningLink).where(
                    (MaterialLearningLink.learning_goal_id == goal_id)
                    | MaterialLearningLink.course_id.in_(course_ids)
                    | MaterialLearningLink.knowledge_point_id.in_(point_ids)
                )
            )
            for entity_type, ids in (
                ("learning_goal", [goal_id]),
                ("course", course_ids),
                ("knowledge_point", point_ids),
                ("daily_task", task_ids),
                ("learning_session", session_ids),
            ):
                if ids:
                    self.db.execute(
                        delete(NoteLink).where(
                            NoteLink.entity_type == entity_type,
                            NoteLink.entity_id.in_([str(value) for value in ids]),
                        )
                    )

            # Goal-scoped conversations and messages remain readable history, but
            # can no longer be resumed as a canonical Goal Context.
            self.db.execute(
                update(AgentConversation)
                .where(
                    AgentConversation.context_type == "goal",
                    AgentConversation.context_id == goal_id,
                )
                .values(status="archived")
            )

            # Generic proposal references have no FK. Expire and detach them so
            # no pending decision can target the deleted item or its plans.
            proposal_conditions = [
                (LearningProposal.target_type == "learning_goal")
                & (LearningProposal.target_id == str(goal_id))
            ]
            if plan_ids:
                proposal_conditions.append(
                    (LearningProposal.target_type == "study_plan")
                    & LearningProposal.target_id.in_([str(value) for value in plan_ids])
                )
            for condition in proposal_conditions:
                self.db.execute(
                    update(LearningProposal)
                    .where(condition)
                    .values(
                        status="expired",
                        target_type=None,
                        target_id=None,
                        domain_draft_type=None,
                        domain_draft_id=None,
                    )
                )

            # Delete item-owned versioned planning and assessment records before
            # their restrictive references to route entities.
            if plan_ids:
                self.db.execute(delete(StudyPlan).where(StudyPlan.id.in_(plan_ids)))
            if diagnostic_ids:
                self.db.execute(
                    delete(DiagnosticSession).where(DiagnosticSession.id.in_(diagnostic_ids))
                )
            if session_ids:
                self.db.execute(
                    delete(LearningSession).where(LearningSession.id.in_(session_ids))
                )
            if task_ids:
                self.db.execute(delete(DailyTask).where(DailyTask.id.in_(task_ids)))
            if lesson_ids:
                self.db.execute(delete(Lesson).where(Lesson.id.in_(lesson_ids)))
            if point_ids:
                self.db.execute(
                    delete(KnowledgePointLifecycleChange).where(
                        KnowledgePointLifecycleChange.knowledge_point_id.in_(point_ids)
                        | KnowledgePointLifecycleChange.superseded_by_id.in_(point_ids)
                    )
                )
                self.db.execute(
                    update(KnowledgePoint)
                    .where(KnowledgePoint.id.in_(point_ids))
                    .values(superseded_by_id=None)
                )

            self.db.delete(goal)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(
                "learning_goal_delete_blocked",
                "事项仍有需要保留的受保护历史，暂时无法删除",
                status.HTTP_409_CONFLICT,
            ) from exc

        return LearningGoalDeleteReport(
            deleted=(
                "learning_goal",
                "courses_and_knowledge_points",
                "study_plans_and_versions",
                "daily_tasks_and_learning_sessions",
                "lessons_and_diagnostics",
            ),
            preserved=(
                "materials",
                "notes_and_source_excerpts",
                "learning_activities_and_answers",
                "rag_answers",
                "agent_messages",
            ),
            association_removed=(
                "material_learning_links",
                "note_links_to_deleted_item_structure",
                "pending_item_proposal_targets",
            ),
            history_policy=(
                "Item-owned planning and execution history is deleted with the item; "
                "independent answer and conversation history is preserved, and "
                "goal-scoped Agent conversations are archived."
            ),
        )
