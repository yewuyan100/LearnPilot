from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.models.quiz_answer import QuizAnswer


@dataclass(frozen=True)
class AggregateScore:
    total_points: float
    earned_points: float
    score_percentage: float
    correct_count: int
    incorrect_count: int
    partial_count: int


def _two(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def aggregate_scores(answers: list[QuizAnswer]) -> AggregateScore:
    if any(
        answer.grading_status != "completed" or answer.earned_points is None
        for answer in answers
    ):
        raise ValueError("仍有题目未完成批改")
    total = sum(Decimal(str(answer.max_points)) for answer in answers)
    earned = sum(Decimal(str(answer.earned_points)) for answer in answers)
    correct = sum(
        1
        for answer in answers
        if Decimal(str(answer.earned_points)) == Decimal(str(answer.max_points))
    )
    incorrect = sum(
        1 for answer in answers if Decimal(str(answer.earned_points)) == Decimal("0")
    )
    partial = len(answers) - correct - incorrect
    percentage = Decimal("0") if total == 0 else earned / total * Decimal("100")
    return AggregateScore(
        total_points=_two(total),
        earned_points=_two(earned),
        score_percentage=_two(percentage),
        correct_count=correct,
        incorrect_count=incorrect,
        partial_count=partial,
    )
