from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParsedSection:
    text: str
    source_order: int
    page_number: int | None = None
    section_title: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    sections: tuple[ParsedSection, ...]
    parser_type: str
    page_count: int | None = None


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    chunk_index: int
    content: str
    char_count: int
    content_hash: str
    page_number: int | None = None
    section_title: str | None = None


class MaterialProcessingError(RuntimeError):
    """A user-readable material parsing or chunking failure."""
