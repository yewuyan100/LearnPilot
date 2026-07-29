import re


CONTROL_CHARACTERS = re.compile(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]")
TRAILING_WHITESPACE = re.compile(r"[ \t]+$", re.MULTILINE)
EXCESSIVE_BLANK_LINES = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")
PDF_WORD_BREAK = re.compile(r"(?<=[A-Za-z])-\n(?=[a-z])")


def clean_text(text: str, *, repair_pdf_lines: bool = False) -> str:
    """Return deterministic readable text without changing semantic punctuation."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    normalized = CONTROL_CHARACTERS.sub("", normalized)
    normalized = normalized.replace("\t", "    ")
    normalized = TRAILING_WHITESPACE.sub("", normalized)
    if repair_pdf_lines:
        normalized = PDF_WORD_BREAK.sub("", normalized)
    normalized = EXCESSIVE_BLANK_LINES.sub("\n\n", normalized)
    return normalized.strip()
