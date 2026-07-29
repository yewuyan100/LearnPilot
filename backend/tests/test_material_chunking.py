from app.services.material_processing.chunking import chunk_sections
from app.services.material_processing.types import ParsedSection


def chunks(text: str, **overrides):
    settings = {"chunk_size": 80, "overlap": 15, "min_chunk_size": 12}
    settings.update(overrides)
    return chunk_sections(
        [ParsedSection(text=text, source_order=0, page_number=2, section_title="State")],
        **settings,
    )


def test_small_and_exact_text_create_one_chunk():
    assert len(chunks("短文本内容。")) == 1
    exact = "a" * 80
    assert len(chunks(exact)) == 1
    assert chunks(exact)[0].content == exact


def test_long_text_uses_overlap_and_continuous_indexes():
    text = "第一句介绍状态。第二句介绍节点。第三句介绍边。第四句介绍持久化。" * 5
    result = chunks(text)
    assert len(result) > 1
    assert [item.chunk_index for item in result] == list(range(len(result)))
    assert result[0].content[-8:] in result[1].content


def test_long_paragraph_falls_back_to_character_windows():
    result = chunks("A" * 220)
    assert len(result) >= 3
    assert all(item.content for item in result)
    assert max(item.char_count for item in result[:-1]) <= 80


def test_chinese_and_english_sentence_boundaries_are_stable():
    text = (
        "这是第一句，用来说明 MCP。第二句解释 Client 与 Server！"
        "This sentence explains tools. Another sentence explains resources."
    )
    assert chunks(text) == chunks(text)
    assert all(item.content_hash for item in chunks(text))


def test_metadata_and_hash_are_propagated():
    item = chunks("State 保存工作流上下文，并在节点之间传递数据。")[0]
    assert item.page_number == 2
    assert item.section_title == "State"
    assert item.char_count == len(item.content)
    assert len(item.content_hash) == 64


def test_empty_text_creates_no_chunks():
    assert chunks("   \n\n") == []


def test_last_small_fragment_is_merged():
    result = chunks("x" * 75 + "\n\n" + "y" * 20, chunk_size=80, overlap=5, min_chunk_size=25)
    assert len(result) == 1
    assert result[0].content.endswith("y" * 20)
