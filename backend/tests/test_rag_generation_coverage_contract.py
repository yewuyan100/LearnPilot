import inspect
import json

from app.services.llm.schemas import RagGroundedAnswerDraft
from app.services.rag import prompts
from app.services.rag.prompts import (
    answer_messages,
    repair_messages,
    rewrite_messages,
)
from app.services.rag.types import RagSource
from app.services.rag.validation import render_grounded_answer, validate_grounded_draft


def _source(label: str, chunk_id: int, content: str) -> RagSource:
    return RagSource(
        source_label=label,
        rank=int(label[1:]),
        score=0.9,
        chunk_id=chunk_id,
        material_id=1,
        original_filename="fixture.md",
        chunk_index=chunk_id - 1,
        content=content,
        page_number=None,
        section_title="Fixture",
    )


def _draft(blocks: list[dict]) -> RagGroundedAnswerDraft:
    return RagGroundedAnswerDraft.model_validate(
        {"answerable": True, "blocks": blocks, "refusal_reason": None}
    )


def test_answer_contract_requires_every_supported_question_branch():
    messages = answer_messages(
        "分别说明方案 A 的条件、方案 B 的机制。",
        [_source("S1", 1, "方案 A 的条件。"), _source("S2", 2, "方案 B 的机制。")],
    )
    system = messages[0]["content"]
    assert "资料已支持的必要分支，并逐一回答" in system
    assert "不要因为已经处理一个相关分支就省略其他必要分支" in system
    assert messages[-1]["content"] == "问题：分别说明方案 A 的条件、方案 B 的机制。"


def test_answer_contract_does_not_force_irrelevant_context_summary():
    messages = answer_messages(
        "比较方案 A 与方案 B。",
        [
            _source("S1", 1, "方案 A。"),
            _source("S2", 2, "方案 B。"),
            _source("S3", 3, "与问题无关的方案 C。"),
        ],
    )
    assert "不要机械总结每个资料片段" in messages[0]["content"]
    assert "只覆盖问题需要且资料支持的内容" in messages[0]["content"]


def test_answer_contract_requires_claim_specific_semantic_support():
    system = answer_messages("说明两个结论。", [_source("S1", 1, "证据")])[0][
        "content"
    ]
    assert "引用 ID 有效不等于语义支持充分" in system
    assert "每个主要事实或技术结论必须绑定实际支持该结论" in system
    assert "拆分 evidence block 或列出所有互补的 source_ids" in system


def test_multiple_claim_specific_citations_validate_and_render():
    sources = [_source("S1", 1, "第一项证据"), _source("S2", 2, "第二项证据")]
    draft = _draft(
        [
            {"content_markdown": "第一项结论。", "source_ids": ["S1"]},
            {"content_markdown": "第二项结论。", "source_ids": ["S2"]},
        ]
    )
    assert validate_grounded_draft(draft, sources) == (True, None)
    rendered = render_grounded_answer(draft, sources)
    assert rendered.answer_markdown == "第一项结论。[S1]\n\n第二项结论。[S2]"
    assert rendered.cited_source_ids == ["S1", "S2"]


def test_rewrite_contract_preserves_distinct_question_branches():
    messages = rewrite_messages(
        "它在条件 A 和机制 B 下分别怎样？", [("user", "讨论对象是方案 X")]
    )
    assert "不得为了更短而删除原问题的必要分支" in messages[0]["content"]
    assert "条件、机制、比较项或备选项" in messages[0]["content"]
    assert "当前问题：它在条件 A 和机制 B 下分别怎样？" in messages[1]["content"]


def test_repair_contract_preserves_supported_required_branch():
    invalid = {
        "answerable": True,
        "blocks": [{"content_markdown": "只回答了第一项。", "source_ids": ["S1"]}],
        "refusal_reason": None,
    }
    messages = repair_messages(
        question="分别回答第一项和第二项。",
        sources=[_source("S1", 1, "第一项"), _source("S2", 2, "第二项")],
        invalid_draft=invalid,
        validation_reason="fixture_failure",
    )
    payload = json.loads(messages[-1]["content"])
    assert "不得通过删除用户问题要求且资料支持的必要分支" in messages[0]["content"]
    assert "不得删除原问题要求且资料支持的必要分支" in payload["instruction"]
    assert payload["invalid_draft"] == invalid


def test_failed_case_fixture_contract_covers_all_three_supported_branches():
    question = "endpoint 本身的 def/async def 选择与 dependency 的混用规则，应该分别依赖哪两份 FastAPI 文档？"
    sources = [
        _source("S1", 364, "dependency 文档说明两种 dependency 可与两种 endpoint 混用。"),
        _source("S2", 362, "不回答当前问题的类型别名说明。"),
        _source("S3", 353, "不回答当前问题的工具函数说明。"),
        _source("S4", 343, "不回答当前问题的并发库说明。"),
        _source("S5", 366, "不回答当前问题的依赖注入概述。"),
        _source("S6", 351, "标准 def dependency 在外部 threadpool 中运行。"),
        _source("S7", 314, "async 文档给出 endpoint 的 def/async def 选择规则。"),
    ]
    messages = answer_messages(question, sources)
    assert messages[-1]["content"] == f"问题：{question}"
    assert [source.chunk_id for source in sources] == [364, 362, 353, 343, 366, 351, 314]
    assert all(
        f'<source id="{label}"' in messages[1]["content"]
        for label in ("S1", "S2", "S3", "S4", "S5", "S6", "S7")
    )

    compliant = _draft(
        [
            {"content_markdown": "endpoint 选择规则来自 async 文档。", "source_ids": ["S7"]},
            {"content_markdown": "外部 threadpool 行为也来自该文档。", "source_ids": ["S6"]},
            {"content_markdown": "dependency 混用规则来自 dependency 文档。", "source_ids": ["S1"]},
        ]
    )
    assert validate_grounded_draft(compliant, sources) == (True, None)
    assert render_grounded_answer(compliant, sources).cited_source_ids == ["S7", "S6", "S1"]

    production_contract = "\n".join(
        [
            prompts.ANSWER_SYSTEM_PROMPT,
            prompts.REWRITE_SYSTEM_PROMPT,
            prompts.REPAIR_SYSTEM_PROMPT,
        ]
    ).lower()
    for forbidden in ("fastapi", "async", "threadpool", "dependency", "endpoint"):
        assert forbidden not in production_contract
    assert "rw-gold-v1" not in inspect.getsource(prompts)
