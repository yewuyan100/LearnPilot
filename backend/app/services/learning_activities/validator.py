import re
from dataclasses import dataclass
from hashlib import sha256

from app.schemas.learning_activity import (
    ActivityGenerateRequest,
    GeneratedActivity,
    GeneratedQuestion,
)


@dataclass(frozen=True)
class ValidationReport:
    errors: list[str]
    warnings: list[str]

    @property
    def valid(self) -> bool:
        return not self.errors


def normalize_stem(stem: str) -> str:
    return re.sub(r"[\W_]+", "", stem, flags=re.UNICODE).lower()


def content_hash(question: GeneratedQuestion) -> str:
    return sha256(
        f"{question.question_type.value}:{normalize_stem(question.stem)}".encode("utf-8")
    ).hexdigest()


def validate_generated_activity(
    activity: GeneratedActivity,
    request: ActivityGenerateRequest,
    allowed_sources: set[str],
) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    if len(activity.questions) != request.question_count:
        errors.append("题目数量与请求不一致")
    requested_types = set(request.question_types)
    if not set(question.question_type for question in activity.questions).issubset(
        requested_types
    ):
        errors.append("生成结果包含未请求的题型")
    if len(activity.questions) >= len(requested_types):
        missing_types = requested_types - {
            question.question_type for question in activity.questions
        }
        if missing_types:
            errors.append("生成结果未覆盖全部请求题型")
    normalized: set[str] = set()
    hashes: set[str] = set()
    for index, question in enumerate(activity.questions, start=1):
        prefix = f"第 {index} 题"
        stem = question.stem.strip()
        normalized_stem = normalize_stem(stem)
        digest = content_hash(question)
        if not stem:
            errors.append(f"{prefix}题干为空")
        if digest in hashes or normalized_stem in normalized:
            errors.append(f"{prefix}与同批其他题目重复")
        hashes.add(digest)
        normalized.add(normalized_stem)
        source_ids = list(dict.fromkeys(question.cited_source_ids))
        if not source_ids or any(item not in allowed_sources for item in source_ids):
            errors.append(f"{prefix}引用了不存在的来源")
        if question.question_type.value in {"single_choice", "multiple_choice"}:
            options = question.options or []
            ids = [item.id for item in options]
            texts = [re.sub(r"\s+", " ", item.text.strip()).lower() for item in options]
            if len(ids) != len(set(ids)):
                errors.append(f"{prefix}选项 ID 重复")
            if len(texts) != len(set(texts)):
                errors.append(f"{prefix}选项文本重复")
            answers = [item for item in question.correct_answer or [] if isinstance(item, str)]
            if any(item not in ids for item in answers):
                errors.append(f"{prefix}答案不在选项中")
            if question.question_type.value == "multiple_choice" and len(answers) >= len(ids):
                errors.append(f"{prefix}多选题不能所有选项都正确")
            lengths = [len(item.text.strip()) for item in options]
            if lengths and min(lengths) > 0 and max(lengths) > min(lengths) * 4:
                warnings.append(f"{prefix}选项长度差异明显")
            if answers and re.search(
                rf"(答案|正确选项)\s*(是|为|:|：)?\s*{'|'.join(map(re.escape, answers))}\b",
                stem,
                re.IGNORECASE,
            ):
                errors.append(f"{prefix}题干直接暴露答案")
        if question.question_type.value == "short_answer":
            concepts = {
                concept.strip().lower()
                for item in question.grading_rubric or []
                for concept in item.required_concepts
                if concept.strip()
            }
            if not concepts:
                errors.append(f"{prefix}评分标准缺少必要概念")
    return ValidationReport(errors, warnings)
