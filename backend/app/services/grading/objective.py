from dataclasses import dataclass

from app.core.errors import AppError
from app.models.activity_question import ActivityQuestion
from fastapi import status


@dataclass(frozen=True)
class ObjectiveGrade:
    earned_points: float
    is_correct: bool
    feedback: str
    unanswered: bool


def normalize_objective_answer(
    question: ActivityQuestion, answer: list[str | bool] | None
) -> list[str | bool] | None:
    if answer is None or answer == []:
        return None
    option_ids = {
        str(item["id"]).strip().upper() for item in (question.options_json or [])
    }
    if question.question_type == "single_choice":
        if len(answer) != 1 or not isinstance(answer[0], str):
            raise AppError(
                "attempt_answer_invalid",
                "单选题只能提交一个选项",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        value = answer[0].strip().upper()
        if value not in option_ids:
            raise AppError(
                "attempt_answer_invalid",
                "单选题答案不是有效选项",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return [value]
    if question.question_type == "multiple_choice":
        if (
            not answer
            or any(not isinstance(item, str) for item in answer)
        ):
            raise AppError(
                "attempt_answer_invalid",
                "多选题答案必须是选项列表",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        values = [item.strip().upper() for item in answer]
        if len(values) != len(set(values)) or any(item not in option_ids for item in values):
            raise AppError(
                "attempt_answer_invalid",
                "多选题包含重复或无效选项",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return sorted(values)
    if question.question_type == "true_false":
        if len(answer) != 1 or type(answer[0]) is not bool:
            raise AppError(
                "attempt_answer_invalid",
                "判断题答案必须是 true 或 false",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return [answer[0]]
    raise AppError(
        "attempt_answer_invalid",
        "简答题不能提交客观选项",
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


def grade_objective(
    question: ActivityQuestion, answer: list[str | bool] | None
) -> ObjectiveGrade:
    normalized = normalize_objective_answer(question, answer)
    if normalized is None:
        return ObjectiveGrade(0.0, False, "未作答", True)
    expected = question.correct_answer_json or []
    if question.question_type == "multiple_choice":
        correct = set(normalized) == {
            str(item).strip().upper() for item in expected
        }
    elif question.question_type == "single_choice":
        correct = normalized == [str(expected[0]).strip().upper()]
    else:
        correct = normalized == expected
    return ObjectiveGrade(
        round(question.points, 2) if correct else 0.0,
        correct,
        "回答正确" if correct else "回答错误，请结合解析和来源复习",
        False,
    )
