from app.services.material_processing.cleaning import clean_text


def test_cleaning_normalizes_newlines_nul_controls_and_tabs():
    value = "第一行\r\n含\x00空值\r第二行\t对齐\x07"
    assert clean_text(value) == "第一行\n含空值\n第二行    对齐"


def test_cleaning_collapses_blank_lines_and_preserves_paragraphs():
    value = "第一段  \n\n\n\n第二段\n\n第三段"
    assert clean_text(value) == "第一段\n\n第二段\n\n第三段"


def test_cleaning_preserves_chinese_english_punctuation_and_code():
    value = '说明：“Tools 与 Resources” (v2-beta).\n\nif (x >= 1) { return "ok"; }'
    cleaned = clean_text(value)
    assert "“Tools 与 Resources” (v2-beta)." in cleaned
    assert 'if (x >= 1) { return "ok"; }' in cleaned


def test_cleaning_is_stable_and_repairs_only_safe_pdf_word_breaks():
    value = "inter-\nnational\n\n中文-\n段落"
    first = clean_text(value, repair_pdf_lines=True)
    assert first == clean_text(value, repair_pdf_lines=True)
    assert "international" in first
    assert "中文-\n段落" in first
