from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select

from app.core.clock import clock_from_settings
from app.models import KnowledgeMastery, MasteryEvidence, MasterySnapshot
from app.services.adaptive_learning.confidence import calculate_confidence
from app.services.adaptive_learning.enums import EvidenceType, MasteryLevel


SCORED_TYPES = (
    EvidenceType.objective_quiz, EvidenceType.short_answer_quiz,
    EvidenceType.successful_review, EvidenceType.task_completion,
    EvidenceType.learning_session, EvidenceType.self_assessment,
    EvidenceType.diagnostic_assessment, EvidenceType.diagnostic_adjustment,
)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def quantize(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class KnowledgeMasteryService:
    def __init__(self, db, settings, *, now: datetime | None = None):
        self.db = db
        self.settings = settings
        self.now = now or clock_from_settings(settings).now()

    def level(self, score: float | None) -> str:
        if score is None:
            return MasteryLevel.unassessed
        if score <= self.settings.mastery_beginner_max:
            return MasteryLevel.beginner
        if score <= self.settings.mastery_developing_max:
            return MasteryLevel.developing
        if score <= self.settings.mastery_proficient_max:
            return MasteryLevel.proficient
        return MasteryLevel.strong

    def calculate(self, evidence: list[MasteryEvidence]) -> dict:
        scored = [item for item in evidence if item.evidence_type in SCORED_TYPES]
        by_type: dict[str, list[MasteryEvidence]] = defaultdict(list)
        for item in sorted(scored, key=lambda row: (aware(row.occurred_at), row.id), reverse=True):
            if len(by_type[item.evidence_type]) < self.settings.mastery_max_evidence_per_type:
                by_type[item.evidence_type].append(item)
        category_scores: dict[str, float] = {}
        category_weights: dict[str, float] = {}
        selected_ids: list[int] = []
        half_life = self.settings.mastery_evidence_half_life_days
        for kind, rows in by_type.items():
            time_weights = []
            weighted_scores = []
            for item in rows:
                age_days = max(0.0, (aware(self.now) - aware(item.occurred_at)).total_seconds() / 86400)
                time_weight = 0.5 ** (age_days / half_life)
                time_weights.append(time_weight)
                weighted_scores.append(float(item.normalized_score) * time_weight)
                selected_ids.append(item.id)
            category_scores[kind] = quantize(sum(weighted_scores) / sum(time_weights))
            category_weights[kind] = float(rows[0].weight)
        if not category_scores:
            mastery_score = None
        else:
            weight_sum = sum(category_weights.values())
            mastery_score = quantize(sum(
                category_scores[kind] * category_weights[kind] for kind in category_scores
            ) / weight_sum)
            mastery_score = max(0.0, min(100.0, mastery_score))
        confidence = calculate_confidence(scored, category_scores, self.now)
        return {
            "mastery_score": mastery_score,
            "confidence_score": confidence,
            "mastery_level": self.level(mastery_score),
            "evidence_count": len(evidence),
            "category_scores": category_scores,
            "selected_evidence_ids": sorted(selected_ids),
            "last_evidence_at": max((aware(item.occurred_at) for item in evidence), default=None),
            "last_practiced_at": max((aware(item.occurred_at) for item in scored), default=None),
            "last_reviewed_at": max((aware(item.occurred_at) for item in evidence if item.evidence_type == EvidenceType.successful_review), default=None),
        }

    def recalculate(self, knowledge_point_id: int, *, trigger_type: str, trigger_source_id: str | int | None = None) -> tuple[KnowledgeMastery, bool]:
        evidence = self.db.scalars(select(MasteryEvidence).where(
            MasteryEvidence.knowledge_point_id == knowledge_point_id
        ).order_by(MasteryEvidence.occurred_at.desc(), MasteryEvidence.id.desc())).all()
        result = self.calculate(list(evidence))
        mastery = self.db.scalar(select(KnowledgeMastery).where(
            KnowledgeMastery.knowledge_point_id == knowledge_point_id
        ))
        if mastery is None:
            mastery = KnowledgeMastery(
                knowledge_point_id=knowledge_point_id,
                algorithm_version=self.settings.mastery_algorithm_version,
                calculated_at=self.now,
            )
            self.db.add(mastery)
        mastery.mastery_score = result["mastery_score"]
        mastery.confidence_score = result["confidence_score"]
        mastery.mastery_level = result["mastery_level"]
        mastery.evidence_count = result["evidence_count"]
        mastery.last_evidence_at = result["last_evidence_at"]
        mastery.last_practiced_at = result["last_practiced_at"]
        mastery.last_reviewed_at = result["last_reviewed_at"]
        mastery.algorithm_version = self.settings.mastery_algorithm_version
        mastery.calculated_at = self.now
        self.db.flush()

        summary = {
            "category_scores": result["category_scores"],
            "selected_evidence_ids": result["selected_evidence_ids"],
            "evidence_type_counts": {
                kind: sum(item.evidence_type == kind for item in evidence)
                for kind in sorted({item.evidence_type for item in evidence})
            },
        }
        previous = self.db.scalar(select(MasterySnapshot).where(
            MasterySnapshot.knowledge_point_id == knowledge_point_id
        ).order_by(MasterySnapshot.calculated_at.desc(), MasterySnapshot.id.desc()))
        changed = previous is None or any((
            (float(previous.mastery_score) if previous.mastery_score is not None else None) != result["mastery_score"],
            float(previous.confidence_score) != result["confidence_score"],
            previous.mastery_level != result["mastery_level"],
            previous.evidence_count != result["evidence_count"],
            previous.evidence_summary_json != summary,
        ))
        if changed:
            self.db.add(MasterySnapshot(
                knowledge_point_id=knowledge_point_id,
                mastery_score=result["mastery_score"], confidence_score=result["confidence_score"],
                mastery_level=result["mastery_level"], evidence_count=result["evidence_count"],
                evidence_summary_json=summary, algorithm_version=self.settings.mastery_algorithm_version,
                trigger_type=trigger_type,
                trigger_source_id=str(trigger_source_id) if trigger_source_id is not None else None,
                calculated_at=self.now, created_at=self.now,
            ))
            self.db.flush()
        return mastery, changed
