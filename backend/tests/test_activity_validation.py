import pytest
from pydantic import ValidationError

from app.models.activity_question import ActivityQuestion
from app.schemas.learning_activity import (
    ActivityGenerateRequest,
    GeneratedActivity,
    GeneratedQuestion,
)
from app.services.grading.objective import grade_objective
from app.services.learning_activities.validator import validate_generated_activity
from app.services.llm.openai_compatible import _decode_json_content


def base_question(**updates):
    value = {
        "question_type": "single_choice",
        "stem": "哪一个是正确描述？",
        "options": [
            {"id": "A", "text": "描述 A"},
            {"id": "B", "text": "描述 B"},
            {"id": "C", "text": "描述 C"},
        ],
        "correct_answer": ["A"],
        "reference_answer": None,
        "grading_rubric": None,
        "explanation": "来源支持描述 A。",
        "difficulty": "easy",
        "points": 2,
        "cited_source_ids": ["S1"],
    }
    value.update(updates)
    return value


def test_structured_output_accepts_a_single_json_fence():
    assert _decode_json_content('```json\n{"value": 1}\n```') == {"value": 1}


@pytest.mark.parametrize(
    "updates",
    [
        {"correct_answer": ["A", "B"]},
        {"options": [{"id": "A", "text": "a"}, {"id": "B", "text": "b"}]},
        {"correct_answer": ["Z"]},
    ],
)
def test_invalid_single_choice_combinations(updates):
    if updates == {"correct_answer": ["Z"]}:
        question = GeneratedQuestion.model_validate(base_question(**updates))
        request = ActivityGenerateRequest.model_validate(
            {
                "title": "练习",
                "material_ids": [1],
                "question_types": ["single_choice"],
                "question_count": 1,
                "request_id": "request-123",
            }
        )
        report = validate_generated_activity(
            GeneratedActivity(title="练习", questions=[question]),
            request,
            {"S1"},
        )
        assert not report.valid
    else:
        with pytest.raises(ValidationError):
            GeneratedQuestion.model_validate(base_question(**updates))


def test_short_answer_requires_balanced_rubric():
    with pytest.raises(ValidationError):
        GeneratedQuestion.model_validate(
            {
                **base_question(),
                "question_type": "short_answer",
                "options": None,
                "correct_answer": None,
                "reference_answer": "参考",
                "grading_rubric": [
                    {
                        "criterion": "概念",
                        "points": 1,
                        "required_concepts": ["概念"],
                    }
                ],
            }
        )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "title": "题数不足",
            "material_ids": [1],
            "question_types": ["single_choice", "short_answer"],
            "question_count": 1,
            "request_id": "request-too-few",
        },
        {
            "title": "重复资料",
            "material_ids": [1, 1],
            "question_types": ["single_choice"],
            "question_count": 1,
            "request_id": "request-duplicate-material",
        },
    ],
)
def test_generation_request_requires_bounded_material_scope(payload):
    with pytest.raises(ValidationError):
        ActivityGenerateRequest.model_validate(payload)


def test_generation_request_accepts_a_course_as_material_scope():
    request = ActivityGenerateRequest.model_validate(
        {
            "title": "课程范围",
            "course_id": 1,
            "question_types": ["single_choice"],
            "question_count": 1,
            "request_id": "request-course-scope",
        }
    )
    assert request.course_id == 1
    assert request.material_ids is None


@pytest.mark.parametrize(
    "updates",
    [
        {
            "question_type": "multiple_choice",
            "correct_answer": ["A", "A"],
        },
        {
            "question_type": "true_false",
            "options": None,
            "correct_answer": ["true"],
        },
        {
            "question_type": "short_answer",
            "options": None,
            "correct_answer": None,
            "reference_answer": "参考",
            "grading_rubric": [
                {
                    "criterion": "概念",
                    "points": 1,
                    "required_concepts": ["概念"],
                },
                {
                    "criterion": "概念",
                    "points": 1,
                    "required_concepts": ["另一个概念"],
                },
            ],
        },
    ],
)
def test_other_invalid_question_combinations(updates):
    with pytest.raises(ValidationError):
        GeneratedQuestion.model_validate(base_question(**updates))


def objective_question(question_type, correct):
    return ActivityQuestion(
        id=1,
        activity_id=1,
        question_index=1,
        question_type=question_type,
        stem="题目",
        options_json=(
            [{"id": "A", "text": "A"}, {"id": "B", "text": "B"}, {"id": "C", "text": "C"}]
            if question_type != "true_false"
            else None
        ),
        correct_answer_json=correct,
        explanation="解析",
        difficulty="easy",
        points=2,
        content_hash="hash",
    )


def test_objective_grading_is_deterministic_and_strict():
    assert grade_objective(objective_question("single_choice", ["A"]), [" a "]).is_correct
    assert grade_objective(
        objective_question("multiple_choice", ["A", "C"]), ["C", "A"]
    ).is_correct
    assert not grade_objective(
        objective_question("multiple_choice", ["A", "C"]), ["A"]
    ).is_correct
    assert grade_objective(objective_question("true_false", [True]), [True]).is_correct
    assert grade_objective(objective_question("true_false", [True]), None).unanswered
