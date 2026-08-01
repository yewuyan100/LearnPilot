from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from app.services.adaptive_learning.enums import EvidenceType


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def calculate_confidence(evidence: list, category_scores: dict[str, float], now: datetime) -> float:
    if not evidence:
        return 0.0
    count_score = min(len(evidence) / 10, 1) * 40
    diversity_score = min(len(category_scores) / 6, 1) * 25
    newest = max(_aware(item.occurred_at) for item in evidence)
    age_days = max(0.0, (_aware(now) - newest).total_seconds() / 86400)
    freshness_score = max(0.0, 1 - age_days / 90) * 25
    direct_quiz = any(item.evidence_type in {
        EvidenceType.objective_quiz, EvidenceType.short_answer_quiz
    } for item in evidence)
    direct_score = 10 if direct_quiz else 0
    conflict_penalty = 0.0
    values = list(category_scores.values())
    if len(values) >= 2 and max(values) - min(values) > 40:
        conflict_penalty = min(15.0, (max(values) - min(values) - 40) * 0.25)
    value = max(0.0, min(100.0, count_score + diversity_score + freshness_score + direct_score - conflict_penalty))
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
