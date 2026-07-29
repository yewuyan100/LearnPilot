from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.services.material_processing.types import (
    MaterialProcessingError,
    ParsedDocument,
    ParsedSection,
)


class PdfParser:
    parser_type = "pdf"

    def parse(self, path: Path) -> ParsedDocument:
        try:
            reader = PdfReader(str(path), strict=False)
            if reader.is_encrypted:
                raise MaterialProcessingError(
                    "当前 PDF 已加密，V2 无法读取受密码保护的文件。"
                )
            sections: list[ParsedSection] = []
            for page_number, page in enumerate(reader.pages, start=1):
                try:
                    text = page.extract_text() or ""
                except Exception as exc:
                    raise MaterialProcessingError(
                        f"PDF 第 {page_number} 页文本提取失败。"
                    ) from exc
                if text.strip():
                    sections.append(
                        ParsedSection(
                            text=text,
                            source_order=len(sections),
                            page_number=page_number,
                        )
                    )
        except MaterialProcessingError:
            raise
        except (PdfReadError, OSError, ValueError) as exc:
            raise MaterialProcessingError("PDF 文件损坏或格式无效，无法读取。") from exc
        except Exception as exc:
            raise MaterialProcessingError("PDF 读取失败，请确认文件格式有效。") from exc

        if not sections:
            raise MaterialProcessingError(
                "当前 PDF 未提取到可用文本，可能是扫描版文件；V2 暂不支持 OCR。"
            )
        return ParsedDocument(
            sections=tuple(sections),
            parser_type=self.parser_type,
            page_count=len(reader.pages),
        )
