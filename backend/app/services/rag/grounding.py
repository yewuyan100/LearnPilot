import logging
from dataclasses import dataclass

from app.services.llm.base import LLMProvider, LLMUsage
from app.services.llm.errors import LLMOutputInvalidError
from app.services.llm.schemas import RagGroundedAnswerDraft
from app.services.rag.prompts import answer_messages, repair_messages
from app.services.rag.types import RagSource
from app.services.rag.validation import (
    RenderedGroundedAnswer,
    render_grounded_answer,
    validate_grounded_draft,
)

logger = logging.getLogger("personal_learning.rag.grounding")


@dataclass(frozen=True)
class GroundedAnswerResult:
    answer: RenderedGroundedAnswer
    model_name: str
    usage: LLMUsage
    finish_reason: str | None
    initial_finish_reason: str | None
    repair_attempted: bool
    initial_validation_reason: str | None


class GroundedAnswerInvalidError(Exception):
    code = "grounded_answer_invalid"

    def __init__(self, reason: str, *, initial_reason: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.initial_reason = initial_reason


def _draft_from_result(value) -> RagGroundedAnswerDraft:
    if isinstance(value, RagGroundedAnswerDraft):
        return value
    return RagGroundedAnswerDraft.model_validate(value)


def _completed_result(
    *,
    draft: RagGroundedAnswerDraft,
    sources: list[RagSource],
    model_result,
    initial_finish_reason: str | None,
    repair_attempted: bool,
    initial_validation_reason: str | None,
) -> GroundedAnswerResult:
    return GroundedAnswerResult(
        answer=render_grounded_answer(draft, sources),
        model_name=model_result.model,
        usage=model_result.usage,
        finish_reason=model_result.finish_reason,
        initial_finish_reason=initial_finish_reason,
        repair_attempted=repair_attempted,
        initial_validation_reason=initial_validation_reason,
    )


def generate_grounded_answer(
    *,
    provider: LLMProvider,
    question: str,
    sources: list[RagSource],
) -> GroundedAnswerResult:
    """Generate, validate, repair at most once, and deterministically render an answer."""
    initial_result = None
    invalid_draft: dict | None = None
    validation_reason: str | None = None
    try:
        initial_result = provider.generate_structured(
            messages=answer_messages(question, sources),
            schema=RagGroundedAnswerDraft,
        )
        draft = _draft_from_result(initial_result.value)
        valid, validation_reason = validate_grounded_draft(draft, sources)
        if valid:
            return _completed_result(
                draft=draft,
                sources=sources,
                model_result=initial_result,
                initial_finish_reason=initial_result.finish_reason,
                repair_attempted=False,
                initial_validation_reason=None,
            )
        invalid_draft = draft.model_dump(mode="json")
    except LLMOutputInvalidError as exc:
        validation_reason = exc.reason

    assert validation_reason is not None
    logger.info(
        "rag_grounding_repair_started reason=%s allowed_source_ids=%s",
        validation_reason,
        [source.source_label for source in sources],
    )
    try:
        repaired_result = provider.generate_structured(
            messages=repair_messages(
                question=question,
                sources=sources,
                invalid_draft=invalid_draft,
                validation_reason=validation_reason,
            ),
            schema=RagGroundedAnswerDraft,
        )
    except LLMOutputInvalidError as exc:
        raise GroundedAnswerInvalidError(
            exc.reason,
            initial_reason=validation_reason,
        ) from exc

    repaired_draft = _draft_from_result(repaired_result.value)
    valid, repaired_reason = validate_grounded_draft(repaired_draft, sources)
    if not valid:
        raise GroundedAnswerInvalidError(
            repaired_reason or "grounding_validation_failed",
            initial_reason=validation_reason,
        )
    return _completed_result(
        draft=repaired_draft,
        sources=sources,
        model_result=repaired_result,
        initial_finish_reason=(
            initial_result.finish_reason if initial_result is not None else None
        ),
        repair_attempted=True,
        initial_validation_reason=validation_reason,
    )
