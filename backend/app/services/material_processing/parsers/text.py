from pathlib import Path

from app.services.material_processing.types import (
    MaterialProcessingError,
    ParsedDocument,
    ParsedSection,
)


class TextParser:
    parser_type = "text"

    def parse(self, path: Path) -> ParsedDocument:
        try:
            text = path.read_bytes().decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise MaterialProcessingError(
                "TXT 文件不是有效的 UTF-8 或 UTF-8-SIG 编码，请转换编码后重试。"
            ) from exc
        if not text.strip():
            raise MaterialProcessingError("TXT 文件没有可处理的正文。")
        return ParsedDocument(
            sections=(ParsedSection(text=text, source_order=0),),
            parser_type=self.parser_type,
            page_count=None,
        )
