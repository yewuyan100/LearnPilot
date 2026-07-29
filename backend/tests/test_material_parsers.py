from pathlib import Path

import pytest

from app.services.material_processing.parsers.markdown import MarkdownParser
from app.services.material_processing.parsers.pdf import PdfParser
from app.services.material_processing.parsers.text import TextParser
from app.services.material_processing.types import MaterialProcessingError
from tests.pdf_utils import write_text_pdf


def test_text_parser_utf8_and_utf8_sig(tmp_path: Path):
    plain = tmp_path / "plain.txt"
    plain.write_text("第一段\n\nSecond paragraph.", encoding="utf-8")
    bom = tmp_path / "bom.txt"
    bom.write_bytes(b"\xef\xbb\xbfMCP resources")

    assert TextParser().parse(plain).sections[0].text.startswith("第一段")
    assert TextParser().parse(bom).sections[0].text == "MCP resources"


@pytest.mark.parametrize(
    "payload, message",
    [
        (b"", "没有可处理的正文"),
        (b"\xff\xfe\x00\x00", "UTF-8"),
    ],
)
def test_text_parser_rejects_empty_and_invalid_encoding(
    tmp_path: Path,
    payload: bytes,
    message: str,
):
    path = tmp_path / "invalid.txt"
    path.write_bytes(payload)
    with pytest.raises(MaterialProcessingError, match=message):
        TextParser().parse(path)


def test_markdown_parser_preserves_headings_lists_and_code(tmp_path: Path):
    path = tmp_path / "guide.md"
    path.write_text(
        "# MCP 定位\n\n- Client\n- Server\n\n"
        "## Tools\n\n```python\nserver.run()\n```\n",
        encoding="utf-8",
    )
    first = MarkdownParser().parse(path)
    second = MarkdownParser().parse(path)

    assert first == second
    assert [section.section_title for section in first.sections] == ["MCP 定位", "Tools"]
    assert "- Client" in first.sections[0].text
    assert "server.run()" in first.sections[1].text
    assert "```" not in first.sections[1].text


def test_pdf_parser_tracks_multiple_pages(tmp_path: Path):
    path = write_text_pdf(
        tmp_path / "pages.pdf",
        ["MCP client and server", "Tools and resources"],
    )
    document = PdfParser().parse(path)

    assert document.page_count == 2
    assert [section.page_number for section in document.sections] == [1, 2]
    assert "Tools" in document.sections[1].text


def test_pdf_parser_rejects_blank_or_scanned_pdf(tmp_path: Path):
    path = write_text_pdf(tmp_path / "blank.pdf", ["", ""])
    with pytest.raises(MaterialProcessingError, match="扫描版"):
        PdfParser().parse(path)


def test_pdf_parser_rejects_damaged_pdf(tmp_path: Path):
    path = tmp_path / "damaged.pdf"
    path.write_bytes(b"%PDF damaged")
    with pytest.raises(MaterialProcessingError, match="损坏|读取失败"):
        PdfParser().parse(path)


def test_pdf_parser_rejects_encrypted_pdf(tmp_path: Path):
    path = write_text_pdf(tmp_path / "encrypted.pdf", ["Protected"], encrypted=True)
    with pytest.raises(MaterialProcessingError, match="加密"):
        PdfParser().parse(path)
