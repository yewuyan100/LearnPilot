from pathlib import Path

from app.services.material_processing.parsers.base import MaterialParser
from app.services.material_processing.parsers.markdown import MarkdownParser
from app.services.material_processing.parsers.pdf import PdfParser
from app.services.material_processing.parsers.text import TextParser
from app.services.material_processing.types import MaterialProcessingError


def parser_for(path: Path, source_type: str) -> MaterialParser:
    normalized = source_type.lower().lstrip(".")
    if normalized == "pdf":
        return PdfParser()
    if normalized in {"md", "markdown"}:
        return MarkdownParser()
    if normalized == "txt":
        return TextParser()
    raise MaterialProcessingError(f"暂不支持解析 {source_type} 资料")


__all__ = ["MaterialParser", "MarkdownParser", "PdfParser", "TextParser", "parser_for"]
