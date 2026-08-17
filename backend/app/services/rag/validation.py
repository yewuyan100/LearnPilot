import re
from dataclasses import dataclass

from app.services.llm.schemas import RagGroundedAnswerDraft
from app.services.rag.types import RagSource

CITATION_PATTERN = re.compile(r"\[(S\d+)\]")
FORBIDDEN_DRAFT_CITATION_PATTERN = re.compile(
    r"\[\s*S\s*\d+\s*\]", re.IGNORECASE
)
PROMPT_INJECTION_PATTERN = re.compile(
    r"(泄露|显示|输出|告诉我).{0,12}(系统提示|system prompt|内部提示)"
    r"|忽略.{0,12}(指令|规则|提示)"
    r"|reveal.{0,12}system prompt",
    re.IGNORECASE,
)


def is_prompt_injection_request(question: str) -> bool:
    return bool(PROMPT_INJECTION_PATTERN.search(question))


@dataclass(frozen=True)
class RenderedGroundedAnswer:
    answerable: bool
    answer_markdown: str
    cited_source_ids: list[str]
    refusal_reason: str | None


class GroundingValidationError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def validate_grounded_draft(
    draft: RagGroundedAnswerDraft,
    sources: list[RagSource],
    *,
    max_source_count: int = 20,
    max_answer_chars: int = 12000,
) -> tuple[bool, str | None]:
    allowed = {source.source_label for source in sources}
    refusal_reason = (draft.refusal_reason or "").strip()
    if not draft.answerable:
        if draft.blocks:
            return False, "refusal_has_blocks"
        if not refusal_reason:
            return False, "refusal_reason_missing"
        return True, None

    if refusal_reason:
        return False, "answer_has_refusal_reason"
    if not draft.blocks:
        return False, "answer_blocks_missing"

    unique_source_ids: list[str] = []
    rendered_chars = 0
    for index, block in enumerate(draft.blocks, start=1):
        content = block.content_markdown.strip()
        if not content:
            return False, f"evidence_content_empty:block={index}"
        if FORBIDDEN_DRAFT_CITATION_PATTERN.search(content):
            return False, f"citation_syntax_forbidden:block={index}"
        if not block.source_ids:
            return False, f"evidence_sources_missing:block={index}"
        block_ids = list(dict.fromkeys(block.source_ids))
        unknown = [source_id for source_id in block_ids if source_id not in allowed]
        if unknown:
            return False, (
                f"evidence_source_invalid:block={index}:ids={','.join(unknown)}"
            )
        for source_id in block_ids:
            if source_id not in unique_source_ids:
                unique_source_ids.append(source_id)
        rendered_chars += len(content) + sum(len(source_id) + 2 for source_id in block_ids)

    if len(unique_source_ids) > max_source_count:
        return False, "evidence_source_limit_exceeded"
    rendered_chars += max(0, len(draft.blocks) - 1) * 2
    if rendered_chars > max_answer_chars:
        return False, "rendered_answer_too_long"
    return True, None


def render_grounded_answer(
    draft: RagGroundedAnswerDraft,
    sources: list[RagSource],
) -> RenderedGroundedAnswer:
    valid, reason = validate_grounded_draft(draft, sources)
    if not valid:
        raise GroundingValidationError(reason or "grounding_validation_failed")
    if not draft.answerable:
        return RenderedGroundedAnswer(
            answerable=False,
            answer_markdown="",
            cited_source_ids=[],
            refusal_reason=(draft.refusal_reason or "").strip(),
        )

    rendered_blocks: list[str] = []
    cited_source_ids: list[str] = []
    for block in draft.blocks:
        block_ids = list(dict.fromkeys(block.source_ids))
        citations = "".join(f"[{source_id}]" for source_id in block_ids)
        rendered_blocks.append(f"{block.content_markdown.strip()}{citations}")
        for source_id in block_ids:
            if source_id not in cited_source_ids:
                cited_source_ids.append(source_id)
    return RenderedGroundedAnswer(
        answerable=True,
        answer_markdown="\n\n".join(rendered_blocks),
        cited_source_ids=cited_source_ids,
        refusal_reason=None,
    )
