from uuid import NAMESPACE_URL, uuid5

from app.learning.agents.planning import PlanningAgent
from app.learning.events.module import LearningEventRecorder
from app.learning.events.schemas import LearningEventEnvelope
from app.learning.planning import PlanAdjustmentModule
from app.models.learning_session import LearningSession
from app.models.lesson import Lesson, LessonVersion
from app.services.adaptive_learning.lifecycle import try_refresh_adaptive_learning


class AdaptiveLearningLoop:
    """Post-assessment seam connecting existing Event, Mastery, Proposal and Plan Modules."""

    actor_key = "local-owner"

    def __init__(self, db, settings, clock) -> None:
        self.db = db
        self.settings = settings
        self.clock = clock
        self.events = LearningEventRecorder(db, clock)
        self.planning = PlanAdjustmentModule(db, settings, PlanningAgent(), clock)

    @staticmethod
    def _event_id(event_type: str, identity: str | int) -> str:
        return str(uuid5(NAMESPACE_URL, f"personallearning:{event_type}:{identity}"))

    def _record(
        self,
        *,
        event_type: str,
        identity: str | int,
        aggregate_type: str,
        aggregate_id: str | int,
        payload: dict,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> str:
        event_id = self._event_id(event_type, identity)
        self.events.record(
            LearningEventEnvelope(
                event_id=event_id,
                event_type=event_type,
                actor_key=self.actor_key,
                aggregate_type=aggregate_type,
                aggregate_id=str(aggregate_id),
                correlation_id=correlation_id,
                causation_id=causation_id,
                payload=payload,
                occurred_at=self.clock.now(),
            )
        )
        return event_id

    def _lesson_completed(
        self, session: LearningSession | None, *, causation_id: str | None
    ) -> str | None:
        if (
            session is None
            or session.status != "completed"
            or session.lesson_version_id is None
        ):
            return None
        version = self.db.get(LessonVersion, session.lesson_version_id)
        lesson = self.db.get(Lesson, version.lesson_id) if version else None
        if version is None or lesson is None:
            return None
        return self._record(
            event_type="LessonCompleted",
            identity=session.id,
            aggregate_type="lesson",
            aggregate_id=lesson.id,
            correlation_id=f"learning-session:{session.id}",
            causation_id=causation_id,
            payload={
                "learning_session_id": session.id,
                "course_id": session.course_id,
                "lesson_id": lesson.id,
                "lesson_version_id": version.id,
                "knowledge_point_ids": (
                    [session.knowledge_point_id] if session.knowledge_point_id else []
                ),
            },
        )

    def _mastery_changed(
        self, refresh: dict | None, *, causation_id: str
    ) -> tuple[str | None, str | None]:
        result = (refresh or {}).get("result") or {}
        if not result.get("mastery_changed") or not result.get("snapshot_id"):
            return None, None
        event_id = self._record(
            event_type="MasteryChanged",
            identity=result["snapshot_id"],
            aggregate_type="knowledge_point",
            aggregate_id=result["knowledge_point_id"],
            correlation_id=causation_id,
            causation_id=causation_id,
            payload={
                "knowledge_point_id": result["knowledge_point_id"],
                "old_level": result["old_level"],
                "new_level": result["new_level"],
                "confidence": result["confidence_score"],
                "evidence_ids": result["evidence_ids"],
                "mastery_snapshot_id": result["snapshot_id"],
            },
        )
        proposal = self.planning.consume_mastery_changed(event_id)
        return event_id, proposal.proposal_id if proposal else None

    def after_quiz_finished(self, attempt, activity) -> dict:
        session = (
            self.db.get(LearningSession, attempt.learning_session_id)
            if attempt.learning_session_id
            else None
        )
        lesson_id = None
        if session and session.lesson_version_id:
            version = self.db.get(LessonVersion, session.lesson_version_id)
            lesson_id = version.lesson_id if version else None
        quiz_event_id = self._record(
            event_type="QuizFinished",
            identity=attempt.id,
            aggregate_type="quiz_attempt",
            aggregate_id=attempt.id,
            correlation_id=attempt.request_id,
            payload={
                "quiz_attempt_id": attempt.id,
                "course_id": activity.course_id,
                "lesson_id": lesson_id,
                "knowledge_point_ids": (
                    [activity.knowledge_point_id] if activity.knowledge_point_id else []
                ),
                "score": float(attempt.score_percentage or 0),
            },
        )
        lesson_event_id = self._lesson_completed(session, causation_id=quiz_event_id)
        refresh = try_refresh_adaptive_learning(
            self.db,
            self.settings,
            activity.knowledge_point_id,
            trigger_type=(
                "review_completed"
                if activity.source_scope.get("kind") == "wrong_answer_review"
                else "quiz_completed"
            ),
            trigger_source_id=attempt.id,
            clock=self.clock,
        )
        mastery_event_id, proposal_id = self._mastery_changed(
            refresh, causation_id=quiz_event_id
        )
        return {
            "quiz_event_id": quiz_event_id,
            "lesson_event_id": lesson_event_id,
            "mastery_event_id": mastery_event_id,
            "proposal_id": proposal_id,
        }

    def after_lesson_completed(self, session: LearningSession) -> dict:
        lesson_event_id = self._lesson_completed(session, causation_id=None)
        refresh = try_refresh_adaptive_learning(
            self.db,
            self.settings,
            session.knowledge_point_id,
            trigger_type="learning_session_completed",
            trigger_source_id=session.id,
            clock=self.clock,
        )
        mastery_event_id = None
        proposal_id = None
        if lesson_event_id is not None:
            mastery_event_id, proposal_id = self._mastery_changed(
                refresh, causation_id=lesson_event_id
            )
        return {
            "lesson_event_id": lesson_event_id,
            "mastery_event_id": mastery_event_id,
            "proposal_id": proposal_id,
        }
