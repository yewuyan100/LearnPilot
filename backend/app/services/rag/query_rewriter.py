import re

from app.core.config import Settings
from app.services.llm.base import LLMProvider
from app.services.llm.errors import LLMError
from app.services.llm.schemas import QueryRewriteResult
from app.services.rag.prompts import rewrite_messages
from app.services.rag.types import RewriteResult

FOLLOW_UP_PATTERN = re.compile(
    r"(它|这个|这点|前面|上面|上述|刚才|其中|二者|两者|有什么区别|那.+呢|为什么)"
)
ENTITY_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{2,}")


def rewrite_query(
    *,
    question: str,
    history: list[tuple[str, str]],
    settings: Settings,
    provider: LLMProvider | None,
) -> RewriteResult:
    limited: list[tuple[str, str]] = []
    used_chars = 0
    for role, content in reversed(history[-settings.rag_history_messages :]):
        remaining = settings.rag_history_chars - used_chars
        if remaining <= 0:
            break
        text = content[-remaining:]
        limited.append((role, text))
        used_chars += len(text)
    limited.reverse()
    if (
        not settings.rag_query_rewrite_enabled
        or not limited
        or provider is None
        or (len(question) > 60 and not FOLLOW_UP_PATTERN.search(question))
        or not FOLLOW_UP_PATTERN.search(question)
    ):
        return RewriteResult(question, len(limited), False)
    try:
        result = provider.generate_structured(
            messages=rewrite_messages(question, limited),
            schema=QueryRewriteResult,
        )
        candidate = result.value.standalone_query.strip()  # type: ignore[attr-defined]
        allowed_text = question + "\n" + "\n".join(content for _, content in limited)
        allowed_entities = {item.lower() for item in ENTITY_PATTERN.findall(allowed_text)}
        candidate_entities = {item.lower() for item in ENTITY_PATTERN.findall(candidate)}
        if not candidate or not candidate_entities.issubset(allowed_entities):
            return RewriteResult(question, len(limited), False)
        return RewriteResult(candidate, len(limited), candidate != question)
    except LLMError:
        return RewriteResult(question, len(limited), False)

