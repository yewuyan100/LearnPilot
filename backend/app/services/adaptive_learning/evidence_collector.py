import json
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import select

from app.models import (
    ActivityQuestion, DailyTask, LearningActivity, LearningSession,
    MasteryEvidence, QuizAnswer, QuizAttempt, WrongAnswer,
)
from app.services.adaptive_learning.enums import EvidenceType


def _aware(value: datetime | None, fallback: datetime) -> datetime:
    if value is None:
        return fallback
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class LearningEvidenceCollector:
    def __init__(self, db, settings, *, now: datetime | None = None):
        self.db = db
        self.settings = settings
        self.now = now or settings.adaptive_fixed_now or datetime.now(timezone.utc)

    def _weight(self, evidence_type: str) -> float:
        return {
            EvidenceType.objective_quiz: self.settings.mastery_objective_weight,
            EvidenceType.short_answer_quiz: self.settings.mastery_short_answer_weight,
            EvidenceType.wrong_answer: self.settings.mastery_review_weight,
            EvidenceType.successful_review: self.settings.mastery_review_weight,
            EvidenceType.task_completion: self.settings.mastery_task_weight,
            EvidenceType.learning_session: self.settings.mastery_session_weight,
            EvidenceType.self_assessment: self.settings.mastery_self_assessment_weight,
        }[EvidenceType(evidence_type)]

    def add(
        self, *, knowledge_point_id: int, evidence_type: str, source_type: str,
        source_id: str | int, occurred_at: datetime, raw_value: float | None,
        normalized_score: float, metadata: dict,
    ) -> tuple[MasteryEvidence, bool]:
        source_id = str(source_id)
        existing = self.db.scalar(select(MasteryEvidence).where(
            MasteryEvidence.source_type == source_type,
            MasteryEvidence.source_id == source_id,
            MasteryEvidence.evidence_type == evidence_type,
        ))
        if existing:
            return existing, False
        normalized_score = max(0.0, min(100.0, round(float(normalized_score), 2)))
        payload = {
            "knowledge_point_id": knowledge_point_id, "evidence_type": evidence_type,
            "source_type": source_type, "source_id": source_id,
            "occurred_at": _aware(occurred_at, self.now).isoformat(),
            "normalized_score": normalized_score, "metadata": metadata,
        }
        evidence = MasteryEvidence(
            knowledge_point_id=knowledge_point_id,
            evidence_type=evidence_type,
            source_type=source_type,
            source_id=source_id,
            occurred_at=_aware(occurred_at, self.now),
            raw_value=raw_value,
            normalized_score=normalized_score,
            weight=self._weight(evidence_type),
            metadata_json=metadata,
            content_hash=sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            created_at=self.now,
        )
        self.db.add(evidence)
        self.db.flush()
        return evidence, True

    def collect(self, knowledge_point_id: int) -> int:
        created = 0
        quiz_rows = self.db.execute(
            select(QuizAnswer, QuizAttempt, ActivityQuestion)
            .join(QuizAttempt, QuizAttempt.id == QuizAnswer.attempt_id)
            .join(ActivityQuestion, ActivityQuestion.id == QuizAnswer.question_id)
            .join(LearningActivity, LearningActivity.id == QuizAttempt.activity_id)
            .where(
                LearningActivity.knowledge_point_id == knowledge_point_id,
                QuizAttempt.status == "completed",
                QuizAnswer.grading_status == "completed",
                QuizAnswer.earned_points.is_not(None),
                QuizAnswer.max_points > 0,
            )
        ).all()
        for answer, attempt, question in quiz_rows:
            kind = (
                EvidenceType.short_answer_quiz
                if question.question_type == "short_answer"
                else EvidenceType.objective_quiz
            )
            _, is_new = self.add(
                knowledge_point_id=knowledge_point_id, evidence_type=kind,
                source_type="quiz_answer", source_id=answer.id,
                occurred_at=attempt.graded_at or attempt.submitted_at or attempt.created_at,
                raw_value=float(answer.earned_points),
                normalized_score=float(answer.earned_points) / float(answer.max_points) * 100,
                metadata={"question_type": question.question_type, "attempt_id": attempt.id},
            )
            created += int(is_new)

        wrongs = self.db.scalars(select(WrongAnswer).where(
            WrongAnswer.knowledge_point_id == knowledge_point_id,
            WrongAnswer.status.in_(("active", "resolved")),
        )).all()
        for wrong in wrongs:
            kind = EvidenceType.successful_review if wrong.status == "resolved" else EvidenceType.wrong_answer
            occurred = wrong.resolved_at or wrong.last_reviewed_at or wrong.created_at
            _, is_new = self.add(
                knowledge_point_id=knowledge_point_id, evidence_type=kind,
                source_type="wrong_answer", source_id=wrong.id,
                occurred_at=occurred, raw_value=1 if wrong.status == "resolved" else 0,
                normalized_score=100 if wrong.status == "resolved" else 0,
                metadata={"status": wrong.status, "review_count": wrong.review_count, "error_type": wrong.error_type},
            )
            created += int(is_new)

        tasks = self.db.scalars(select(DailyTask).where(
            DailyTask.knowledge_point_id == knowledge_point_id, DailyTask.status == "completed"
        )).all()
        for task in tasks:
            _, is_new = self.add(
                knowledge_point_id=knowledge_point_id, evidence_type=EvidenceType.task_completion,
                source_type="daily_task", source_id=task.id, occurred_at=task.updated_at,
                raw_value=1, normalized_score=70,
                metadata={"task_type": task.task_type, "estimated_minutes": task.estimated_minutes},
            )
            created += int(is_new)

        sessions = self.db.scalars(select(LearningSession).where(
            LearningSession.knowledge_point_id == knowledge_point_id,
            LearningSession.status == "completed", LearningSession.ended_at.is_not(None),
        )).all()
        for session in sessions:
            started = _aware(session.started_at, self.now)
            ended = _aware(session.ended_at, self.now)
            minutes = max(0.0, (ended - started).total_seconds() / 60)
            if minutes <= 0:
                continue
            _, is_new = self.add(
                knowledge_point_id=knowledge_point_id, evidence_type=EvidenceType.learning_session,
                source_type="learning_session", source_id=session.id, occurred_at=ended,
                raw_value=minutes, normalized_score=min(100, minutes / 30 * 100),
                metadata={"duration_minutes": round(minutes, 2)},
            )
            created += int(is_new)
        return created

    def record_self_assessment(self, knowledge_point_id: int, rating: int, request_id: str) -> tuple[MasteryEvidence, bool]:
        mapped = {1: 20, 2: 40, 3: 60, 4: 80, 5: 100}[rating]
        return self.add(
            knowledge_point_id=knowledge_point_id, evidence_type=EvidenceType.self_assessment,
            source_type="self_assessment", source_id=request_id, occurred_at=self.now,
            raw_value=rating, normalized_score=mapped, metadata={"rating": rating},
        )
