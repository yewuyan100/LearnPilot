from dataclasses import dataclass


@dataclass(frozen=True)
class RagSource:
    source_label: str
    rank: int
    score: float
    chunk_id: int
    material_id: int
    original_filename: str
    chunk_index: int
    content: str
    page_number: int | None
    section_title: str | None


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    sources: list[RagSource]
    candidate_count: int
    index_version: str | None
    duration_ms: int
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class RewriteResult:
    query: str
    used_history_messages: int
    rewritten: bool

