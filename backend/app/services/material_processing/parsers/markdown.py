from pathlib import Path
import re

from app.services.material_processing.types import (
    MaterialProcessingError,
    ParsedDocument,
    ParsedSection,
)


HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
INLINE_LINK = re.compile(r"!?\[([^\]]+)]\(([^)]+)\)")
INLINE_CODE = re.compile(r"`([^`\n]+)`")


def _plain_inline_markdown(text: str) -> str:
    text = INLINE_LINK.sub(lambda match: f"{match.group(1)} ({match.group(2)})", text)
    text = INLINE_CODE.sub(lambda match: match.group(1), text)
    text = text.replace("**", "").replace("__", "").replace("~~", "")
    return text


class MarkdownParser:
    parser_type = "markdown"

    def parse(self, path: Path) -> ParsedDocument:
        try:
            text = path.read_bytes().decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise MaterialProcessingError(
                "Markdown 文件不是有效的 UTF-8 或 UTF-8-SIG 编码。"
            ) from exc
        if not text.strip():
            raise MaterialProcessingError("Markdown 文件没有可处理的正文。")

        sections: list[ParsedSection] = []
        current_title: str | None = None
        current_lines: list[str] = []
        in_code_block = False

        def flush() -> None:
            body = "\n".join(current_lines).strip()
            if body:
                sections.append(
                    ParsedSection(
                        text=body,
                        source_order=len(sections),
                        section_title=current_title,
                    )
                )
            current_lines.clear()

        for line in text.splitlines():
            if line.lstrip().startswith("```") or line.lstrip().startswith("~~~"):
                in_code_block = not in_code_block
                continue
            if not in_code_block:
                heading = HEADING.match(line)
                if heading:
                    flush()
                    current_title = _plain_inline_markdown(heading.group(2)).strip()
                    continue
                current_lines.append(_plain_inline_markdown(line))
            else:
                current_lines.append(line)
        flush()

        if not sections:
            raise MaterialProcessingError("Markdown 文件清理后没有可处理的正文。")
        return ParsedDocument(
            sections=tuple(sections),
            parser_type=self.parser_type,
            page_count=None,
        )
