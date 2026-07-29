from hashlib import sha256
import re

from app.services.material_processing.types import ChunkDraft, ParsedSection


BOUNDARY_PATTERNS = (
    re.compile(r"\n\n"),
    re.compile(r"\n"),
    re.compile(r"[。！？!?；;](?:\s|$)"),
    re.compile(r"[.](?:\s|$)"),
    re.compile(r"[,，、:：](?:\s|$)"),
)


def _choose_end(text: str, start: int, hard_end: int, minimum: int) -> int:
    if hard_end >= len(text):
        return len(text)
    search_start = min(start + minimum, hard_end)
    window = text[search_start:hard_end]
    for pattern in BOUNDARY_PATTERNS:
        matches = list(pattern.finditer(window))
        if matches:
            return search_start + matches[-1].end()
    return hard_end


def _section_ranges(
    text: str,
    chunk_size: int,
    overlap: int,
    min_chunk_size: int,
) -> list[tuple[int, int]]:
    if not text:
        return []
    if len(text) <= chunk_size:
        return [(0, len(text))]

    ranges: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        hard_end = min(start + chunk_size, len(text))
        end = _choose_end(text, start, hard_end, min_chunk_size)
        if end <= start:
            end = hard_end
        ranges.append((start, end))
        if end >= len(text):
            break
        next_start = max(end - overlap, start + 1)
        while next_start < end and text[next_start].isspace():
            next_start += 1
        start = next_start

    if len(ranges) > 1:
        last_start, last_end = ranges[-1]
        last_content = text[last_start:last_end].strip()
        previous_start, previous_end = ranges[-2]
        new_tail_length = last_end - previous_end
        if len(last_content) < min_chunk_size or new_tail_length < min_chunk_size:
            ranges[-2] = (previous_start, last_end)
            ranges.pop()
    return ranges


def chunk_sections(
    sections: list[ParsedSection],
    *,
    chunk_size: int,
    overlap: int,
    min_chunk_size: int,
) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for section in sorted(sections, key=lambda item: item.source_order):
        text = section.text.strip()
        for start, end in _section_ranges(text, chunk_size, overlap, min_chunk_size):
            content = text[start:end].strip()
            if not content:
                continue
            drafts.append(
                ChunkDraft(
                    chunk_index=len(drafts),
                    content=content,
                    char_count=len(content),
                    content_hash=sha256(content.encode("utf-8")).hexdigest(),
                    page_number=section.page_number,
                    section_title=section.section_title,
                )
            )
    return drafts
