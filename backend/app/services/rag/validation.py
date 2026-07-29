import re

from app.services.llm.schemas import RagModelAnswer
from app.services.rag.types import RagSource

CITATION_PATTERN = re.compile(r"\[(S\d+)\]")
PROMPT_INJECTION_PATTERN = re.compile(
    r"(泄露|显示|输出|告诉我).{0,12}(系统提示|system prompt|内部提示)"
    r"|忽略.{0,12}(指令|规则|提示)"
    r"|reveal.{0,12}system prompt",
    re.IGNORECASE,
)


def is_prompt_injection_request(question: str) -> bool:
    return bool(PROMPT_INJECTION_PATTERN.search(question))


def validate_answer(answer: RagModelAnswer, sources: list[RagSource]) -> tuple[bool, str | None]:
    allowed = {source.source_label for source in sources}
    inline = set(CITATION_PATTERN.findall(answer.answer_markdown))
    declared = set(answer.cited_source_ids)
    if answer.answerable:
        if not answer.answer_markdown.strip() or not inline:
            return False, "answer_missing_citations"
        if inline != declared:
            return False, "citation_declaration_mismatch"
        if not inline.issubset(allowed):
            return False, "citation_source_invalid"
        if answer.refusal_reason:
            return False, "answer_has_refusal_reason"
    else:
        if inline or declared:
            return False, "refusal_has_citations"
    return True, None
