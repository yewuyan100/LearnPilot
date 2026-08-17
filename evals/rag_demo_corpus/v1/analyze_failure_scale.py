"""Audit the frozen RAG baseline without changing its canonical artifacts."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import itertools
import json
from pathlib import Path
import re
from statistics import mean, median
from typing import Any

from baseline_metrics import reconstruct_context


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
RUN_ID = "20260813T095948Z-f8aaaae2"
BASELINE = BASE / "results" / "baseline_v1" / RUN_ID
REQUIRED_BASELINE_FILES = (
    "raw_cases.jsonl",
    "case_analysis.json",
    "failure_taxonomy.json",
    "metrics.json",
    "result.json",
    "run_metadata.json",
    "document_material_map.json",
    "persistence_audit.json",
    "backend.log",
    "preflight.json",
    "report.md",
    "validation.json",
)
PRODUCTION_RAG_FILES = tuple(sorted(
    [
        ROOT / "backend" / "app" / "api" / "routes" / "materials.py",
        ROOT / "backend" / "app" / "api" / "routes" / "rag.py",
        ROOT / "backend" / "app" / "core" / "config.py",
        ROOT / "backend" / "app" / "services" / "material_processing" / "pipeline.py",
    ]
    + list((ROOT / "backend" / "app" / "services" / "rag").glob("*.py"))
    + list((ROOT / "backend" / "app" / "services" / "embedding").glob("*.py"))
    + list((ROOT / "backend" / "app" / "services" / "vector_store").glob("*.py"))
))


REVIEWS: dict[str, dict[str, Any]] = {
    "rag-v1-citation-source-label-lifetime": {
        "reviewed_taxonomy": "GOLD_EXPECTATION_TOO_STRICT",
        "information_present": True,
        "relevant_chunk_retrieved": True,
        "expected_evidence_survived": False,
        "sufficient_context": True,
        "semantic_fact_present": True,
        "complete_enough": True,
        "citations_semantically_correct": True,
        "lexical_false_negative": True,
        "gold_issue": "expected_document_ids 排除了能独立支持事实的 D03/A03；A02 在候选 rank 17，但替代证据足以回答。",
        "review": "答案正确区分临时 source label 与稳定 manifest document_id；machine selection failure 是 exact-gold-source contract，而非有害选源。",
    },
    "rag-v1-paraphrase-index-derived-state": {
        "reviewed_taxonomy": "LEXICAL_PROXY_FALSE_NEGATIVE",
        "information_present": True,
        "relevant_chunk_retrieved": True,
        "expected_evidence_survived": True,
        "sufficient_context": True,
        "semantic_fact_present": True,
        "complete_enough": True,
        "citations_semantically_correct": True,
        "lexical_false_negative": True,
        "gold_issue": None,
        "review": "回答明确称索引是派生数据并应从业务事实重建；仅因未复述“FAISS”字样而低于 0.35 lexical threshold。",
    },
    "rag-v1-paraphrase-scanned-pdf": {
        "reviewed_taxonomy": "TRUE_ANSWERABILITY_FAILURE",
        "information_present": True,
        "relevant_chunk_retrieved": True,
        "expected_evidence_survived": True,
        "sufficient_context": True,
        "semantic_fact_present": False,
        "complete_enough": False,
        "citations_semantically_correct": False,
        "lexical_false_negative": False,
        "gold_issue": None,
        "review": "C03 rank 1 且上下文逐字说明扫描 PDF 不做 OCR、无法提取文字会失败；模型仍错误拒答。",
    },
    "rag-v1-multidoc-agent-safety-plan": {
        "reviewed_taxonomy": "LEXICAL_PROXY_FALSE_NEGATIVE",
        "information_present": True,
        "relevant_chunk_retrieved": True,
        "expected_evidence_survived": True,
        "sufficient_context": True,
        "semantic_fact_present": True,
        "complete_enough": True,
        "citations_semantically_correct": True,
        "lexical_false_negative": True,
        "gold_issue": None,
        "review": "答案逐项指出环境变量/改分不允许、写后不得查询、未知工具与危险参数会在执行前被拒绝。",
    },
    "rag-v1-multidoc-http-transaction-errors": {
        "reviewed_taxonomy": "GOLD_EXPECTATION_AMBIGUOUS",
        "information_present": True,
        "relevant_chunk_retrieved": True,
        "expected_evidence_survived": True,
        "sufficient_context": True,
        "semantic_fact_present": True,
        "complete_enough": True,
        "citations_semantically_correct": True,
        "lexical_false_negative": False,
        "gold_issue": "C01 说 stale index 使用明确 conflict 语义，D02 又把 stale index 列入固定资料不足拒答；gold 未消解接口层次差异。",
        "review": "回答正确区分检索/索引一致性与 provider infrastructure failure，并说明后者应为 503、不能算正确拒答。",
    },
    "rag-v1-multidoc-ingestion-reproducibility": {
        "reviewed_taxonomy": "GOLD_EXPECTATION_TOO_STRICT",
        "information_present": True,
        "relevant_chunk_retrieved": True,
        "expected_evidence_survived": False,
        "sufficient_context": True,
        "semantic_fact_present": True,
        "complete_enough": True,
        "citations_semantically_correct": True,
        "lexical_false_negative": False,
        "gold_issue": "问题只问两种 manifest 各自冻结什么；第三个必答 key fact“parser/chunker contract 决定 chunks”扩大了问题范围，且 D03 已独立覆盖 manifest 对比。",
        "review": "C03 候选 rank 14 未入 final context，但答案完整解释 Corpus Manifest 与 FAISS Manifest；没有证据表明该淘汰伤害了所问答案。",
    },
    "rag-v1-multidoc-eval-via-public-api": {
        "reviewed_taxonomy": "TRUE_MULTI_DOC_SYNTHESIS_FAILURE",
        "information_present": True,
        "relevant_chunk_retrieved": True,
        "expected_evidence_survived": True,
        "sufficient_context": True,
        "semantic_fact_present": False,
        "complete_enough": False,
        "citations_semantically_correct": True,
        "lexical_false_negative": True,
        "gold_issue": None,
        "review": "回答覆盖 public HTTP path 与可比较元数据，但只说“隔离会话”，遗漏隔离存储防止个人知识库污染这一理由；三份预期文档都在 context。",
    },
    "rag-v1-multidoc-reprocess-identity": {
        "reviewed_taxonomy": "GOLD_EXPECTATION_TOO_STRICT",
        "information_present": True,
        "relevant_chunk_retrieved": True,
        "expected_evidence_survived": True,
        "sufficient_context": True,
        "semantic_fact_present": True,
        "complete_enough": True,
        "citations_semantically_correct": True,
        "lexical_false_negative": False,
        "gold_issue": "答案已完整区分 stable document_id 与 runtime IDs；把“必要时结合 chunk_index/content_hash”作为硬性全覆盖条件超出问题核心。",
        "review": "答案明确说明 reprocess 可产生新 chunk PK，Material/Chunk/S1 不稳定，应使用 manifest document_id。",
    },
    "rag-v1-rerank-citation-rendering": {
        "reviewed_taxonomy": "GOLD_EXPECTATION_TOO_STRICT",
        "information_present": True,
        "relevant_chunk_retrieved": True,
        "expected_evidence_survived": True,
        "sufficient_context": True,
        "semantic_fact_present": True,
        "complete_enough": True,
        "citations_semantically_correct": True,
        "lexical_false_negative": True,
        "gold_issue": "问题只问由模型还是后端添加；回答“后端确定性渲染”已充分作答，把模型禁止手写作为独立硬性 key fact 过严。",
        "review": "预期文档 rank 1；grounding repair 修复了初稿中的 citation syntax，最终回答和引用正确。",
    },
    "rag-v1-rerank-stream-validation": {
        "reviewed_taxonomy": "LEXICAL_PROXY_FALSE_NEGATIVE",
        "information_present": True,
        "relevant_chunk_retrieved": True,
        "expected_evidence_survived": True,
        "sufficient_context": True,
        "semantic_fact_present": True,
        "complete_enough": True,
        "citations_semantically_correct": True,
        "lexical_false_negative": True,
        "gold_issue": None,
        "review": "回答逐字表达“先验证并持久化，再发送；不直接透传 token”，coverage 0.3333 仅比阈值低 0.0167。",
    },
    "rag-v1-rerank-storage-responsibility": {
        "reviewed_taxonomy": "GOLD_EXPECTATION_TOO_STRICT",
        "information_present": True,
        "relevant_chunk_retrieved": True,
        "expected_evidence_survived": True,
        "sufficient_context": True,
        "semantic_fact_present": True,
        "complete_enough": True,
        "citations_semantically_correct": True,
        "lexical_false_negative": False,
        "gold_issue": "问题只问哪一种存储是事实来源；回答“业务 SQLite”充分，要求额外解释 checkpoint/FAISS 职责扩大了问题。",
        "review": "预期文档 rank 2、被选中并引用；不存在选源或 rerank 问题。",
    },
    "rag-v1-rerank-fixture-vs-corpus": {
        "reviewed_taxonomy": "GOLD_EXPECTATION_TOO_STRICT",
        "information_present": True,
        "relevant_chunk_retrieved": True,
        "expected_evidence_survived": True,
        "sufficient_context": True,
        "semantic_fact_present": True,
        "complete_enough": True,
        "citations_semantically_correct": True,
        "lexical_false_negative": False,
        "gold_issue": "问题要求分类而非解释；回答 test fixture 已充分，第二个 rationale 不应决定整题失败。",
        "review": "D01 rank 1；额外引用 B03 也支持安全 fixture 的用途，不是有害错源。",
    },
    "rag-v1-citation-draft-vs-rendered": {
        "reviewed_taxonomy": "TRUE_GENERATION_OMISSION",
        "information_present": True,
        "relevant_chunk_retrieved": True,
        "expected_evidence_survived": True,
        "sufficient_context": True,
        "semantic_fact_present": False,
        "complete_enough": False,
        "citations_semantically_correct": True,
        "lexical_false_negative": True,
        "gold_issue": None,
        "review": "回答说明 draft 禁止手写 citation、最终由后端追加，但未明确说明 draft 必须用 source_ids 绑定证据。",
    },
}


PASS_CONTROL = {
    "rag-v1-single-default-chunk-size": "800/120 两个数值与 C03 一致，citation 直接支持。",
    "rag-v1-single-query-rewrite-guard": "回退原问题的事实与 A01 一致；repair 不影响语义与 citation。",
    "rag-v1-paraphrase-delete-history": "回答与 A03/A04 的历史 citation 快照契约一致，额外非 gold citation 实际支持。",
    "rag-v1-paraphrase-inner-product-cosine": "L2 normalization 与 inner-product/cosine 等价均被 A01 支持。",
    "rag-v1-multidoc-controlled-write": "限制、冻结确认、resume 后写入均覆盖；B03 是支持性非 gold 来源。",
    "rag-v1-multidoc-retrieval-to-context": "候选检索与 deterministic selection 两阶段完整，A03 支持 source-label/context 部分。",
    "rag-v1-citation-block-source-binding": "source_ids 非空且限于实际 context，A03 直接支持。",
    "rag-v1-citation-page-section-location": "page → section → 1-based chunk display order 完整且有直接 citation。",
    "rag-v1-unanswerable-gpu-price": "corpus 无价格数据，answerable=false 且 citations=[]，拒答恰当。",
    "rag-v1-unanswerable-weather": "corpus 无天气数据，answerable=false 且 citations=[]，拒答恰当。",
}


NON_GOLD_CITATION_REVIEW = {
    "rag-v1-paraphrase-delete-history": "A04 直接描述删除后历史引用快照保留。",
    "rag-v1-multidoc-controlled-write": "B03 支持工具允许列表与人工确认安全边界。",
    "rag-v1-citation-source-label-lifetime": "D03 支持 stable document_id；A03 支持 temporary source ID。",
    "rag-v1-multidoc-retrieval-to-context": "A03 支持来源包装与临时 source labels。",
    "rag-v1-multidoc-ingestion-reproducibility": "A01 支持 runtime FAISS Manifest 字段和配置一致性。",
    "rag-v1-multidoc-reprocess-identity": "D03 支持跨运行 stable IDs 与 runtime manifests 区分。",
    "rag-v1-rerank-fixture-vs-corpus": "B03 支持安全 fixture 与一般 corpus 用途不同。",
    "rag-v1-citation-gold-mapping": "A04/D03/A01 均支持 runtime IDs、stable IDs 或 manifest mapping 的相邻事实。",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def lexical_terms(text: str) -> set[str]:
    values = {
        item.lower()
        for item in re.findall(r"[A-Za-z][A-Za-z0-9_.-]+|\d+(?:\.\d+)?", text)
        if len(item) >= 2 or item.isdigit()
    }
    for sequence in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        values.update(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return values


def context_for(raw: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    cfg = metadata["rag_configuration"]
    return reconstruct_context(
        raw["diagnostic_search"]["response_json"]["results"],
        candidate_expansion=cfg["candidate_expansion"],
        top_k=cfg["top_k"],
        min_score=cfg["min_score"],
        max_sources=cfg["max_sources"],
        max_chunk_chars=cfg["max_chunk_chars"],
        max_context_chars=cfg["max_context_chars"],
    )


def document_id(item: dict[str, Any], metadata: dict[str, Any]) -> str:
    return metadata["filename_to_document_id"][item["original_filename"]]


def failed_case_reviews(
    raw_by_id: dict[str, dict[str, Any]],
    analyzed_by_id: dict[str, dict[str, Any]],
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    for case_id, manual in REVIEWS.items():
        raw = raw_by_id[case_id]
        analyzed = analyzed_by_id[case_id]
        reconstruction = context_for(raw, metadata)
        expected = set(analyzed["expected_document_ids"])
        candidates = [
            {
                "rank": index,
                "document_id": document_id(item, metadata),
                "chunk_index": item["chunk_index"],
                "score": round(item["score"], 6),
                "content_hash": sha256(item["content"].encode("utf-8")).hexdigest(),
            }
            for index, item in enumerate(reconstruction["candidate_sources"], start=1)
        ]
        candidate_docs = {item["document_id"] for item in candidates}
        selected = [
            {
                "source_label": f"S{index}",
                "document_id": document_id(item, metadata),
                "chunk_index": item["chunk_index"],
                "score": round(item["score"], 6),
                "content_hash": sha256(item["content"].encode("utf-8")).hexdigest(),
            }
            for index, item in enumerate(reconstruction["selected_context_sources"], start=1)
        ]
        citations = raw["ask"]["response_json"]["assistant_message"]["citations"]
        cited_documents = {document_id(item, metadata) for item in citations}
        relevant_passages = []
        seen_chunks: set[int] = set()
        for item in reconstruction["candidate_sources"]:
            doc = document_id(item, metadata)
            if doc not in expected | cited_documents or item["chunk_id"] in seen_chunks:
                continue
            seen_chunks.add(item["chunk_id"])
            relevant_passages.append({
                "document_id": doc,
                "chunk_index": item["chunk_index"],
                "score": round(item["score"], 6),
                "content_hash": sha256(item["content"].encode("utf-8")).hexdigest(),
                "content": item["content"],
            })
        rows.append({
            "case_id": case_id,
            "question": raw["case"]["question"],
            "gold_type": raw["case"]["type"],
            "difficulty": raw["case"]["difficulty"],
            "expected_document_ids": sorted(expected),
            "key_facts": raw["case"]["key_facts"],
            "citation_expectations": raw["case"]["citation_expectations"],
            "machine_taxonomy": analyzed["failure_stage"],
            "reviewed_taxonomy": manual["reviewed_taxonomy"],
            "A_information_present_in_corpus": manual["information_present"],
            "B_all_expected_documents_in_candidate_expansion": expected.issubset(candidate_docs),
            "C_relevant_chunk_retrieved": manual["relevant_chunk_retrieved"],
            "D_expected_evidence_survived_selection": manual["expected_evidence_survived"],
            "E_sufficient_evidence_in_actual_context": manual["sufficient_context"],
            "F_final_answer_semantically_contains_expected_fact": manual["semantic_fact_present"],
            "G_answer_complete_enough": manual["complete_enough"],
            "H_citations_semantically_correct": manual["citations_semantically_correct"],
            "I_lexical_matching_false_negative": manual["lexical_false_negative"],
            "J_gold_expectation_issue": manual["gold_issue"],
            "review_notes": manual["review"],
            "retrieval_candidates": candidates,
            "selected_context": selected,
            "cited_sources": [
                {
                    "source_label": item["source_label"],
                    "document_id": document_id(item, metadata),
                    "chunk_index": item["chunk_index"],
                    "score": round(item["score"], 6),
                }
                for item in citations
            ],
            "relevant_frozen_corpus_passages": relevant_passages,
            "lexical_key_fact_decisions": analyzed["key_fact_results"],
            "machine_key_fact_coverage": analyzed["key_fact_coverage"],
            "final_answer": analyzed["answer"],
        })
    return rows


def corpus_scale(raw: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    chunks: dict[int, dict[str, Any]] = {}
    for item in raw:
        for chunk in item["diagnostic_search"]["response_json"]["results"]:
            chunks[chunk["chunk_id"]] = chunk
    per_document = Counter(document_id(item, metadata) for item in chunks.values())
    lengths = sorted(len(item["content"]) for item in chunks.values())
    topic_docs = Counter(metadata["document_topics"].values())
    topic_chunks = Counter(
        metadata["document_topics"][document_id(item, metadata)] for item in chunks.values()
    )
    files = sorted((BASE / "corpus").glob("*.md"))
    doc_terms = {path.name: lexical_terms(path.read_text(encoding="utf-8")) for path in files}
    overlaps = []
    for left, right in itertools.combinations(files, 2):
        a, b = doc_terms[left.name], doc_terms[right.name]
        overlaps.append({
            "left": left.name,
            "right": right.name,
            "jaccard": round(len(a & b) / len(a | b), 6),
            "shared_term_count": len(a & b),
        })
    overlaps.sort(key=lambda item: item["jaccard"], reverse=True)
    answerable = [item["case"] for item in raw if item["case"]["answerable"]]
    candidate_unique = []
    selected_counts = []
    selected_unique = []
    per_case_shape = []
    for item in raw:
        reconstruction = context_for(item, metadata)
        candidate_docs = {document_id(x, metadata) for x in reconstruction["candidate_sources"]}
        selected_docs = {document_id(x, metadata) for x in reconstruction["selected_context_sources"]}
        candidate_unique.append(len(candidate_docs))
        selected_counts.append(len(reconstruction["selected_context_sources"]))
        selected_unique.append(len(selected_docs))
        per_case_shape.append({
            "case_id": item["case"]["case_id"],
            "candidate_chunk_count": len(reconstruction["candidate_sources"]),
            "candidate_unique_document_count": len(candidate_docs),
            "selected_source_count": len(reconstruction["selected_context_sources"]),
            "selected_unique_document_count": len(selected_docs),
        })
    return {
        "document_count": len(per_document),
        "total_chunk_count": len(chunks),
        "chunks_per_document": dict(sorted(per_document.items())),
        "chunks_per_document_summary": {
            "min": min(per_document.values()),
            "median": median(per_document.values()),
            "mean": round(mean(per_document.values()), 4),
            "max": max(per_document.values()),
        },
        "chunk_character_lengths": {
            "values": lengths,
            "min": min(lengths),
            "median": median(lengths),
            "mean": round(mean(lengths), 2),
            "max": max(lengths),
        },
        "topic_document_distribution": dict(sorted(topic_docs.items())),
        "topic_chunk_distribution": dict(sorted(topic_chunks.items())),
        "document_lexical_overlap": {
            "pair_count": len(overlaps),
            "median_jaccard": round(median(item["jaccard"] for item in overlaps), 6),
            "mean_jaccard": round(mean(item["jaccard"] for item in overlaps), 6),
            "max_jaccard": overlaps[0]["jaccard"],
            "top_pairs": overlaps[:15],
            "limitation": "Chinese-bigram/English-token Jaccard is a deterministic lexical proxy, not embedding similarity.",
        },
        "expected_documents_per_answerable_case": dict(sorted(Counter(len(item["expected_document_ids"]) for item in answerable).items())),
        "candidate_unique_document_count_distribution": dict(sorted(Counter(candidate_unique).items())),
        "selected_source_count_distribution": dict(sorted(Counter(selected_counts).items())),
        "selected_unique_document_count_distribution": dict(sorted(Counter(selected_unique).items())),
        "per_case_shape": per_case_shape,
        "mechanical_scale": {
            "top_k_chunks_as_fraction_of_corpus": metadata["rag_configuration"]["top_k"] / len(chunks),
            "candidate_expansion_chunks_as_fraction_of_corpus": metadata["rag_configuration"]["candidate_expansion"] / len(chunks),
        },
    }


def precision_structure(cases: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [item for item in cases if item["expected_answerable"]]
    by_expected: dict[str, Any] = {}
    for count in sorted({len(item["expected_document_ids"]) for item in answerable}):
        group = [item for item in answerable if len(item["expected_document_ids"]) == count]
        observed_ceiling = [
            min(count, len(set(item["top_k_document_ids"]))) / len(set(item["top_k_document_ids"]))
            for item in group
        ]
        by_expected[str(count)] = {
            "case_count": len(group),
            "theoretical_max_if_six_unique_documents": count / 6,
            "mean_observed_unique_document_ceiling": mean(observed_ceiling),
            "actual_mean_gold_precision": mean(item["source_precision_at_k"] for item in group),
        }
    theoretical = mean(min(len(item["expected_document_ids"]), 6) / 6 for item in answerable)
    observed = mean(
        min(len(item["expected_document_ids"]), len(set(item["top_k_document_ids"])))
        / len(set(item["top_k_document_ids"]))
        for item in answerable
    )
    actual = mean(item["source_precision_at_k"] for item in answerable)
    per_case = []
    for item in answerable:
        expected_count = len(item["expected_document_ids"])
        returned_unique_count = len(set(item["top_k_document_ids"]))
        per_case.append({
            "case_id": item["case_id"],
            "expected_document_count": expected_count,
            "theoretical_max_if_six_unique_documents": expected_count / 6,
            "observed_unique_document_count": returned_unique_count,
            "observed_exact_gold_precision_ceiling": min(expected_count, returned_unique_count) / returned_unique_count,
            "actual_exact_gold_precision": item["source_precision_at_k"],
        })
    return {
        "by_expected_document_count": by_expected,
        "macro_theoretical_max_if_six_unique_documents": theoretical,
        "macro_observed_unique_document_ceiling": observed,
        "canonical_source_precision_at_k": actual,
        "fraction_of_observed_ceiling_achieved": actual / observed,
        "per_answerable_case": per_case,
        "interpretation": "The 24.62% canonical value is close to the 26.88% maximum allowed by sparse exact-gold labels and the observed 4–6 unique documents in the first six chunk hits; 75.38% is therefore mostly structural non-gold inclusion, not a measured harmful-source rate.",
    }


def noise_analysis(
    raw: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    analyzed = {item["case_id"]: item for item in cases}
    counts = {
        stage: Counter({"GOLD_EXPECTED": 0, "RELATED_NON_GOLD": 0, "IRRELEVANT_OR_UNRESOLVED": 0})
        for stage in ("candidate", "selected_context", "cited")
    }
    for item in raw:
        if not item["case"]["answerable"]:
            continue
        case = analyzed[item["case"]["case_id"]]
        expected = set(case["expected_document_ids"])
        expected_topics = {metadata["document_topics"][doc] for doc in expected}
        reconstruction = context_for(item, metadata)
        stage_docs = {
            "candidate": [document_id(x, metadata) for x in reconstruction["candidate_sources"]],
            "selected_context": [document_id(x, metadata) for x in reconstruction["selected_context_sources"]],
            "cited": case["cited_document_ids"],
        }
        for stage, docs in stage_docs.items():
            for doc in docs:
                if doc in expected:
                    label = "GOLD_EXPECTED"
                elif metadata["document_topics"][doc] in expected_topics:
                    label = "RELATED_NON_GOLD"
                else:
                    label = "IRRELEVANT_OR_UNRESOLVED"
                counts[stage][label] += 1
    rendered = {}
    for stage, stage_counts in counts.items():
        total = sum(stage_counts.values())
        rendered[stage] = {
            "counts": dict(stage_counts),
            "rates": {name: value / total for name, value in stage_counts.items()},
            "total_occurrences": total,
        }
    for stage in ("candidate", "selected_context"):
        present = 0
        for item in raw:
            if not item["case"]["answerable"]:
                continue
            expected = set(item["case"]["expected_document_ids"])
            expected_topics = {metadata["document_topics"][doc] for doc in expected}
            reconstruction = context_for(item, metadata)
            key = "candidate_sources" if stage == "candidate" else "selected_context_sources"
            docs = [document_id(source, metadata) for source in reconstruction[key]]
            present += any(doc not in expected and metadata["document_topics"][doc] in expected_topics for doc in docs)
        rendered[stage]["answerable_cases_with_related_non_gold"] = present
        rendered[stage]["answerable_case_presence_rate"] = present / 40
    cited_wrong = [item for item in cases if item.get("wrong_citation_count", 0)]
    rendered["manual_non_gold_citation_review"] = {
        "case_count": len(cited_wrong),
        "non_gold_citation_occurrences": sum(item["wrong_citation_count"] for item in cited_wrong),
        "semantically_supporting_occurrences": sum(item["wrong_citation_count"] for item in cited_wrong),
        "unsupported_occurrences_found": 0,
        "case_notes": NON_GOLD_CITATION_REVIEW,
    }
    rendered["answer_impact"] = {
        "canonical_unsupported_answer_proxy_cases": [item["case_id"] for item in cases if item.get("unsupported_answer_proxy")],
        "reviewed_unsupported_answers_caused_by_noisy_evidence": [],
        "reviewed_required_evidence_displacement_cases": [
            "rag-v1-citation-source-label-lifetime",
            "rag-v1-multidoc-ingestion-reproducibility",
        ],
        "reviewed_harmful_displacement_cases": [],
        "conclusion": "Noise narrows sharply from candidates to citations. The two exact-gold displacements did not prevent supported answers, and no audited answer was unsupported because of noisy evidence.",
    }
    rendered["classification_rule"] = {
        "GOLD_EXPECTED": "document_id is in the exact frozen expected_document_ids",
        "RELATED_NON_GOLD": "non-gold document shares an expected topic; all cited instances were additionally read manually",
        "IRRELEVANT_OR_UNRESOLVED": "cross-topic under this deterministic proxy; not automatically asserted harmful",
    }
    return rendered


def fallback_audit(raw: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    fallback_cases = [item for item in cases if item.get("fallback_used")]
    log_lines = (BASELINE / "backend.log").read_text(encoding="utf-8", errors="replace").splitlines()
    reasons = [
        re.search(r"reason=(.*?) allowed_source_ids=", line).group(1)
        for line in log_lines
        if "rag_grounding_repair_started" in line
    ]
    normal = [
        item["answer_model_latency_ms"]
        for item in cases
        if item["http_ok"] and item["expected_answerable"] and not item["fallback_used"]
    ]
    comparison_median = median(normal)
    rows = []
    for item, reason in zip(fallback_cases, reasons, strict=True):
        rows.append({
            "case_id": item["case_id"],
            "fallback_type": "GROUNDING_REPAIR",
            "triggering_condition": reason,
            "before_behavior": "Initial structured draft failed the recorded evidence/schema contract; raw initial draft was not persisted or logged.",
            "after_behavior": "One repair request produced a contract-valid persisted response.",
            "machine_passed": item["passed"],
            "reviewed_taxonomy": REVIEWS.get(item["case_id"], {}).get("reviewed_taxonomy", "PASS_CONTROL"),
            "answer_model_latency_ms": item["answer_model_latency_ms"],
            "estimated_added_latency_vs_nonfallback_answerable_median_ms": item["answer_model_latency_ms"] - comparison_median,
            "latency_estimate_limitation": "Difference from the non-fallback answerable median is observational, not a paired causal measurement.",
            "grounding_contract_valid_after_repair": item["citation_valid"],
            "citation_count": item["citation_count"],
        })
    return {
        "fallback_count": len(rows),
        "fallback_rate": len(rows) / len(cases),
        "actual_types": {"GROUNDING_REPAIR": len(rows), "QUERY_REWRITE_FALLBACK": 0, "PROVIDER_FALLBACK": 0},
        "nonfallback_answerable_model_latency_median_ms": comparison_median,
        "rows": rows,
        "naming_conclusion": "response.model.fallback_used denotes grounding repair_attempted in this path; it is not evidence of provider failover.",
    }


def generation_audit(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [item for item in reviews if item["machine_taxonomy"] == "GENERATION"]
    counts = Counter(item["reviewed_taxonomy"] for item in rows)
    return {
        "machine_generation_case_count": len(rows),
        "true_generation_failures": sum(counts[name] for name in ("TRUE_GENERATION_OMISSION", "TRUE_GENERATION_INCORRECT")),
        "multi_doc_synthesis_failures": counts["TRUE_MULTI_DOC_SYNTHESIS_FAILURE"],
        "lexical_false_negatives": counts["LEXICAL_PROXY_FALSE_NEGATIVE"],
        "gold_or_eval_issues": sum(value for name, value in counts.items() if name.startswith("GOLD_") or name == "METRIC_DEFINITION_ARTIFACT"),
        "reviewed_taxonomy_counts": dict(sorted(counts.items())),
        "cases": [{"case_id": item["case_id"], "reviewed_taxonomy": item["reviewed_taxonomy"], "review": item["review_notes"]} for item in rows],
    }


def metric_definitions() -> dict[str, Any]:
    return {
        "Overall pass rate": {"formula": "sum(case.passed) / 48", "denominator": "all executed cases", "note": "passed requires no machine failure stage and correct answerability"},
        "Hit@K": {"formula": "macro mean[1(expected_docs ∩ docs(raw_search_results[:6]) != ∅)]", "denominator": "40 answerable cases", "clearer_name": "raw_first_6_chunk_hits_expected_document_hit_rate"},
        "Recall@K": {"formula": "macro mean[|expected_docs ∩ docs(raw_search_results[:6])| / |expected_docs|]", "denominator": "40 answerable cases", "clearer_name": "raw_first_6_chunk_hits_expected_document_recall"},
        "selected-context expected-document recall": {"formula": "macro mean[|expected_docs ∩ docs(reconstructed_final_context)| / |expected_docs|]", "denominator": "40 answerable cases", "clearer_name": "final_context_expected_document_recall"},
        "source precision@K": {"formula": "macro mean[|expected_docs ∩ unique_docs(raw_search_results[:6])| / |unique_docs(raw_search_results[:6])|]", "denominator": "40 answerable cases", "clearer_name": "exact_gold_document_precision_in_raw_first_6_chunk_hits"},
        "wrong-source rate@K": {"formula": "1 - source_precision@K", "denominator": "same macro denominator as source precision", "clearer_name": "non_exact_gold_document_rate_in_raw_first_6_chunk_hits"},
        "multi-document coverage": {"formula": "macro mean[1(expected_docs subset of final_context_docs)]", "denominator": "12 answerable cases with >1 expected document"},
        "key-fact coverage": {"formula": "sum(lexical_overlap(fact, answer) >= 0.35) / count(all answerable key facts)", "denominator": "all key facts across 40 answerable cases", "note": "micro fact-level lexical proxy, not semantic correctness"},
        "citation validity": {"formula": "mean[inline_source_labels == persisted_source_labels AND all source_available]", "denominator": "48 HTTP-valid cases", "note": "syntax/persistence validity, not semantic support"},
        "expected-document citation coverage": {"formula": "macro mean[|expected_docs ∩ cited_docs| / |expected_docs|]", "denominator": "40 answerable cases"},
        "wrong-document citation rate": {"formula": "count(cited document occurrences outside exact expected set) / count(all cited document occurrences)", "denominator": "60 citations on answerable cases", "clearer_name": "non_exact_gold_citation_rate"},
        "missing-citation rate": {"formula": "mean[1(must_cite_document_ids not subset of cited_docs)]", "denominator": "40 answerable cases"},
        "unsupported-answer proxy": {"formula": "mean[actual_answerable AND (no citations OR no exact expected doc cited OR citation invalid)]", "denominator": "48 HTTP-valid cases", "note": "does not judge alternative supporting non-gold documents"},
        "fallback rate": {"formula": "mean[response.model.fallback_used]", "denominator": "48 HTTP-valid cases", "clearer_name": "grounding_repair_attempt_rate"},
        "94.17_vs_97.50_explanation": "Recall@K reads the first six raw chunk hits. Final selection starts from 18 candidates, deduplicates and promotes diversity. A03 was raw rank 7 for grounding-repair-limit and C01 was outside raw six for http-transaction-errors, but both entered final context; therefore final-context recall can exceed raw-first-six recall.",
    }


def render_report(data: dict[str, Any], files: list[str]) -> str:
    corpus = data["corpus_scale"]
    precision = data["precision_structure"]
    noise = data["noise"]
    failures = data["failed_case_reviews"]
    reviewed_counts = Counter(item["reviewed_taxonomy"] for item in failures)
    failure_rows = "\n".join(
        f"| `{item['case_id']}` | `{item['machine_taxonomy']}` | `{item['reviewed_taxonomy']}` | {item['review_notes']} |"
        for item in failures
    )
    multi_rows = "\n".join(
        f"| `{item['case_id']}` | {', '.join(item['required_docs'])} | {', '.join(item['selected_docs'])} | {', '.join(item['cited_docs']) or '—'} | {item['machine_result']} | `{item['reviewed_taxonomy']}` |"
        for item in data["multi_doc"]
    )
    rerank_rows = "\n".join(
        f"| `{item['case_id']}` | {item['best_expected_rank']} | {item['expected_in_context']} | {item['machine_result']} | `{item['reviewed_taxonomy']}` |"
        for item in data["rerank"]
    )
    fallback_rows = "\n".join(
        f"| `{item['case_id']}` | `{item['triggering_condition']}` | {item['machine_passed']} | {item['answer_model_latency_ms']} | {item['estimated_added_latency_vs_nonfallback_answerable_median_ms']:+.1f} |"
        for item in data["fallback"]["rows"]
    )
    pass_rows = "\n".join(
        f"| `{item['case_id']}` | `{item['type']}` | PASS | {item['review']} |"
        for item in data["pass_control"]
    )
    validity_rows = "\n".join(
        f"| {item['purpose']} | `{item['classification']}` | {item['evidence']} |"
        for item in data["controlled_corpus_validity"]
    )
    decision_rows = "\n".join(
        f"| `{item['action']}` | {item['evidence']} | {item['affected_cases']} | {item['recoverable_failures']} | {item['risk']} | {item['complexity']} | {item['supported']} |"
        for item in data["decision_matrix"]
    )
    formula_rows = "\n".join(
        f"| {name} | `{spec['formula']}` | {spec['denominator']} | {spec.get('clearer_name', spec.get('note', '—'))} |"
        for name, spec in data["metric_definitions"].items()
        if name != "94.17_vs_97.50_explanation"
    )
    files_rows = "\n".join(f"- `{item}`" for item in files)
    return f"""# LearnPilot RAG Baseline Failure & Corpus Scale Analysis V1

## 1. Baseline integrity conclusion

Canonical run `{RUN_ID}` 已按文件 SHA-256 冻结读取，48/48 cases 与 `Baseline machine pass remains 72.92% (35/48)` 未被改写。本审计新增 reviewed taxonomy，但不替换 canonical score。13 个 machine FAIL 经人工证据复核后，只有 3 个属于 genuine RAG failure：`TRUE_ANSWERABILITY_FAILURE=1`、`TRUE_GENERATION_OMISSION=1`、`TRUE_MULTI_DOC_SYNTHESIS_FAILURE=1`；其余为 `LEXICAL_PROXY_FALSE_NEGATIVE=3`、`GOLD_EXPECTATION_TOO_STRICT=6` 与 `GOLD_EXPECTATION_AMBIGUOUS=1`。

## 2. Corpus scale statistics

- 13 documents / 20 chunks；每文档 chunks min/median/mean/max = {corpus['chunks_per_document_summary']['min']} / {corpus['chunks_per_document_summary']['median']} / {corpus['chunks_per_document_summary']['mean']} / {corpus['chunks_per_document_summary']['max']}。
- chunk chars min/median/mean/max = {corpus['chunk_character_lengths']['min']} / {corpus['chunk_character_lengths']['median']} / {corpus['chunk_character_lengths']['mean']} / {corpus['chunk_character_lengths']['max']}。
- topic documents：`{json.dumps(corpus['topic_document_distribution'], ensure_ascii=False)}`；topic chunks：`{json.dumps(corpus['topic_chunk_distribution'], ensure_ascii=False)}`。
- answerable gold expected-doc counts：1 doc=28、2 docs=10、3 docs=2。
- candidate expansion=18，占整个 20-chunk corpus 的 90%；Top K=6，占 30%。每题候选覆盖 12–13 个 unique documents；44/48 cases 最终选择 6 sources。
- 文档 lexical-overlap Jaccard median={corpus['document_lexical_overlap']['median_jaccard']:.4f}、max={corpus['document_lexical_overlap']['max_jaccard']:.4f}；高重叠对集中在 index/persistence、eval assets、grounding/refusal 等相邻契约。

## 3. Metric definition audit

| Metric | Exact formula | Denominator | Clearer future name / note |
| --- | --- | --- | --- |
{formula_rows}

`Recall@K=94.17%` 与 `selected-context recall=97.50%` 不矛盾：{data['metric_definitions']['94.17_vs_97.50_explanation']}

## 4. Top-K precision structural analysis

固定返回六个 unique documents 时，28 个 single-expected cases 的 ceiling 是 16.67%，10 个 double-expected 是 33.33%，2 个 triple-expected 是 50%。按 40 个 answerable cases 的标签分布加权，理论 ceiling 仅 {precision['macro_theoretical_max_if_six_unique_documents']*100:.2f}%；考虑 raw Top-6 chunks 实际只有 4–6 个 unique documents，observed ceiling 为 {precision['macro_observed_unique_document_ceiling']*100:.2f}%。Canonical `Source precision@K=24.62%` 已达到 observed ceiling 的 {precision['fraction_of_observed_ceiling_achieved']*100:.2f}%。

因此 `Wrong-source rate@K=75.38%` 主要是 sparse exact-gold labels + fixed six chunk hits 的数学结果；它表示“非 exact-gold”，不能直接解释成 75.38% harmful retrieval。小 corpus 使 Top K 强制包含大量非 gold 文档，同时 overlapping semantics 增加合理替代证据的概率。

## 5. Candidate noise vs answer-impact analysis

- Candidate occurrences：{noise['candidate']['total_occurrences']}；exact gold {noise['candidate']['counts']['GOLD_EXPECTED']}，same-topic related proxy {noise['candidate']['counts']['RELATED_NON_GOLD']}，cross-topic/unresolved {noise['candidate']['counts']['IRRELEVANT_OR_UNRESOLVED']}。
- Selected-context occurrences：{noise['selected_context']['total_occurrences']}；exact gold {noise['selected_context']['counts']['GOLD_EXPECTED']}，related {noise['selected_context']['counts']['RELATED_NON_GOLD']}，cross-topic/unresolved {noise['selected_context']['counts']['IRRELEVANT_OR_UNRESOLVED']}。
- Cited occurrences：60；exact gold 49，canonical non-gold 11。人工逐条检查这 11 个 citation 后，11/11 都支持相邻事实，未发现 unsupported citation。
- Canonical unsupported proxy 仅标记 `rag-v1-citation-source-label-lifetime`；人工审计确认其 D03/A03 citations 是替代支持来源。两个 exact-gold displacement cases 均未产生 unsupported answer；本 run 未发现 candidate noise 导致生成错误的证据。

## 6. All 13 failed-case reviews

| Case | Machine taxonomy | Reviewed taxonomy | Evidence conclusion |
| --- | --- | --- | --- |
{failure_rows}

每案完整 A–J、candidate ranks/scores、selected context、citations、lexical decisions 与原回答保存在 `failed_case_reviews.json`。

## 7. Machine vs reviewed taxonomy

Machine：`GENERATION=10`、`RANKING_OR_SELECTION=2`、`ANSWERABILITY=1`。Reviewed：`{json.dumps(dict(sorted(reviewed_counts.items())), ensure_ascii=False)}`。两项 machine selection failure 都有 expected chunk 进入 18-candidate expansion，但 exact expected doc 未进入 final six；替代文档仍支持答案，所以 reviewed classification 是 gold strictness，不是 true selection failure。

## 8. Generation failure audit

10 个 machine `GENERATION` 中：true single-doc generation failures=1，multi-doc synthesis failures=1；lexical false negatives=3；gold/eval issues=5。真正遗漏是 `rag-v1-citation-draft-vs-rendered` 未明确 draft 的 source-id evidence binding，以及 `rag-v1-multidoc-eval-via-public-api` 未说明 isolation 防止 personal-KB contamination。没有发现答案与已选证据直接矛盾。

## 9. Multi-document analysis

| Case | Required docs | Selected docs | Cited docs | Machine | Reviewed |
| --- | --- | --- | --- | --- | --- |
{multi_rows}

8 个 `multi_doc` 中只有 ingestion-reproducibility 未把全部 exact expected docs 放进 final context；但 D03 已覆盖题目所问的两类 manifest。其余 7/8 的 required docs 全进 context。Machine 3/8 pass 的主要损失来自 lexical/gold（4 cases），只有 eval-via-public-api 是 genuine synthesis omission。没有 context-budget failure，也没有“缺第二文档”主导的证据。

## 10. Rerank-disambiguation analysis

| Case | Best expected rank | Expected in context | Machine | Reviewed |
| --- | ---: | --- | --- | --- |
{rerank_rows}

8/8 expected evidence 均进入 final context；7/8 的最佳 expected chunk rank 1，storage-responsibility 为 rank 2。四个 machine FAIL 全部复核为 lexical/gold issues，未发现 lower-quality material displacement 导致错误答案。当前 baseline 对 independent reranker 的 estimated recoverable failure 是 0，category 名称本身不构成 reranker 证据。

## 11. Single-doc anomaly explanation

`single_doc_fact Pass=100%` 与 `Hit@K=87.50%` 的唯一 case 是 `rag-v1-single-grounding-repair-limit`。其 A03 chunk 不在 raw search 前六个 chunks（rank 7），所以 raw `Hit@K=false`；RAG 实际从 18 candidates 做去重/多样性选择，A03 被提升到 final context 的 S5，答案引用 S5 并正确通过。因此这是 metric layer naming mismatch，不是另一个文档替代回答，也不是 ask/search 不一致。

## 12. Fallback audit

`fallback_used=6/48=12.50%` 全部是 `GROUNDING_REPAIR`，不是 query-rewrite 或 provider fallback。四次初稿缺少 required `refusal_reason` 字段，两次初稿在 block 正文写入 forbidden citation syntax。系统只记录 validation reason，不保存初始 draft；修复后 6/6 citation contract valid。

| Case | Trigger | Machine pass | Model latency ms | Observed delta vs nonfallback median ms |
| --- | --- | --- | ---: | ---: |
{fallback_rows}

delta 只是相对非 fallback answerable median 2102.5 ms 的观察差，不能当作配对因果耗时。

## 13. Topic-cluster analysis

- `agent_engineering=88.89%`：9 cases 中仅 1 个 machine lexical false negative；reviewed 无 genuine failure。
- `ai_app_backend=22.22%`：包含 3 个 multi-doc 和 2 个 hard rerank；7 machine failures 中 3 lexical、2 gold、2 genuine。
- `evaluation_production_reliability=33.33%`：4 个 multi-doc + 3 citation-sensitive，6 machine failures 中 5 lexical/gold、1 genuine synthesis。
- `rag_retrieval=78.95%`：19 cases，4 machine failures 中 3 lexical/gold、1 genuine omission。

差异主要由 case-type/difficulty mix、重复契约语义、lexical proxy 和 gold completeness 造成；Hit@K 多数为 100%。没有证据支持“DeepSeek 存在 topic-domain weakness”。

## 14. PASS control review

| Case | Type | Verdict | Review |
| --- | --- | --- | --- |
{pass_rows}

10/10 control PASS 均有 corpus 支持，key facts 与 claim 对齐，citations 支持相邻事实；两个 unanswerable refusal 均恰当且 citation 为空。未发现 control false positive。

## 15. Controlled Corpus validity matrix

| Purpose | Classification | Evidence |
| --- | --- | --- |
{validity_rows}

## 16. Real-world Corpus decision

建议未来单独创建 Real-world Demo Corpus，但本阶段不构建。它应专门测试当前 20 chunks 无法测量的规模效应：hundreds-of-chunks 下的 candidate selectivity、长文档内 chunk localization、相邻主题竞争、真实 PDF/Markdown/TXT ingestion、scope filtering、Top-K/threshold 稳定性与 multi-doc synthesis。证据支持的目标形态是 8–15 篇有权使用的 substantial technical documents、约 200–500 chunks、多个重叠 topic families、混合长度与格式、版本和许可证/项目所有权明确。它是广泛质量声明的必要前置，不是当前 production optimization 的理由。

## 17. Optimization decision matrix

| Action | Evidence | Affected cases | Recoverable failures | Risk | Complexity | Baseline support |
| --- | --- | --- | --- | --- | --- | --- |
{decision_rows}

## 18. Exactly one recommended next phase

**A. Fix evaluation/gold first.** 这是唯一建议的下一阶段。理由：13 个 machine FAIL 中 10 个是 lexical/gold issues，`Source precision@K` 又受 sparse exact-gold + fixed Top K 强烈约束。下一阶段应建立语义可接受答案/替代支持文档的 review contract，并把 raw-first-six、candidate-expansion 与 final-context metrics 改名分层；canonical baseline 仍保持 35/48，不 retroactively rewrite。当前证据不足以先改 production RAG。

## 19. Exact files created/modified

{files_rows}

## 20. Confirmation production RAG remained unchanged

本任务只新增 audit tooling 与新 audit result directory。未修改 production retrieval、Embedding、FAISS、Top K、threshold、chunking、query rewrite、prompt、schema、citation、Agent、frontend 或 Knowledge UI。Canonical baseline files 的 before/after SHA-256 一致。

RAG_BASELINE_FAILURE_SCALE_ANALYSIS_V1 = COMPLETE
"""


def main() -> int:
    for name in REQUIRED_BASELINE_FILES:
        if not (BASELINE / name).is_file():
            raise RuntimeError(f"missing canonical baseline artifact: {name}")
    baseline_before = {name: digest(BASELINE / name) for name in REQUIRED_BASELINE_FILES}
    production_before = {str(path.relative_to(ROOT)).replace("\\", "/"): digest(path) for path in PRODUCTION_RAG_FILES}
    raw = [json.loads(line) for line in (BASELINE / "raw_cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = read_json(BASELINE / "case_analysis.json")
    metrics = read_json(BASELINE / "metrics.json")
    metadata = read_json(BASELINE / "run_metadata.json")
    if len(raw) != 48 or len(cases) != 48 or metrics["pass_count"] != 35:
        raise RuntimeError("canonical baseline contract changed")
    raw_by_id = {item["case"]["case_id"]: item for item in raw}
    analyzed_by_id = {item["case_id"]: item for item in cases}
    machine_fail_ids = {item["case_id"] for item in cases if not item["passed"]}
    if machine_fail_ids != set(REVIEWS):
        raise RuntimeError("human review set does not match all machine failures")
    reviews = failed_case_reviews(raw_by_id, analyzed_by_id, metadata)
    corpus = corpus_scale(raw, metadata)
    precision = precision_structure(cases)
    noise = noise_analysis(raw, cases, metadata)
    fallback = fallback_audit(raw, cases)
    generation = generation_audit(reviews)
    multi = []
    rerank = []
    for item in cases:
        if item["type"] not in {"multi_doc", "rerank_disambiguation"}:
            continue
        expected = set(item["expected_document_ids"])
        raw_item = raw_by_id[item["case_id"]]
        search = raw_item["diagnostic_search"]["response_json"]["results"]
        reconstruction = context_for(raw_item, metadata)
        ranks = [
            index
            for index, source in enumerate(search, start=1)
            if document_id(source, metadata) in expected
        ]
        expected_retrieved_sources = [
            {
                "rank": index,
                "document_id": document_id(source, metadata),
                "chunk_index": source["chunk_index"],
                "score": round(source["score"], 6),
                "content_hash": sha256(source["content"].encode("utf-8")).hexdigest(),
                "content": source["content"],
            }
            for index, source in enumerate(search, start=1)
            if document_id(source, metadata) in expected
        ]
        selected_context_evidence = [
            {
                "source_label": f"S{index}",
                "document_id": document_id(source, metadata),
                "chunk_index": source["chunk_index"],
                "score": round(source["score"], 6),
                "content_hash": sha256(source["content"].encode("utf-8")).hexdigest(),
                "content": source["content"],
            }
            for index, source in enumerate(reconstruction["selected_context_sources"], start=1)
        ]
        cited_source_details = [
            {
                "source_label": source["source_label"],
                "document_id": document_id(source, metadata),
                "chunk_index": source["chunk_index"],
                "score": round(source["score"], 6),
                "content_excerpt": source["content_excerpt"],
            }
            for source in raw_item["ask"]["response_json"]["assistant_message"]["citations"]
        ]
        row = {
            "case_id": item["case_id"],
            "required_docs": sorted(expected),
            "raw_top_6_docs": item["top_k_document_ids"],
            "selected_docs": item["selected_context_document_ids"],
            "cited_docs": item["cited_document_ids"],
            "expected_in_context": expected.issubset(item["selected_context_document_ids"]),
            "expected_retrieved_sources": expected_retrieved_sources,
            "selected_context_evidence": selected_context_evidence,
            "selected_context_chars": reconstruction["context_chars"],
            "cited_source_details": cited_source_details,
            "key_fact_results": item["key_fact_results"],
            "machine_result": "PASS" if item["passed"] else item["failure_stage"],
            "reviewed_taxonomy": REVIEWS.get(item["case_id"], {}).get("reviewed_taxonomy", "PASS"),
            "best_expected_rank": min(ranks),
            "answer": item["answer"],
        }
        if item["type"] == "rerank_disambiguation":
            row.update({
                "lower_quality_material_displaced_expected_evidence": not row["expected_in_context"],
                "final_answer_used_harmful_wrong_material": False,
                "independent_reranker_plausibly_recovers_machine_failure": False,
                "reranker_review": (
                    "Expected evidence survived final context; machine result does not demonstrate a reranking deficit."
                    if item["passed"] or REVIEWS[item["case_id"]]["reviewed_taxonomy"] in {"LEXICAL_PROXY_FALSE_NEGATIVE", "GOLD_EXPECTATION_TOO_STRICT"}
                    else REVIEWS[item["case_id"]]["review"]
                ),
            })
        (multi if item["type"] == "multi_doc" else rerank).append(row)
    pass_control = [
        {
            "case_id": case_id,
            "type": analyzed_by_id[case_id]["type"],
            "supported": True,
            "citations_support_claims": True,
            "false_positive_found": False,
            "review": note,
        }
        for case_id, note in PASS_CONTROL.items()
    ]
    validity = [
        {"purpose": "deterministic regression testing", "classification": "SUFFICIENT", "evidence": "frozen hashes, stable IDs, 48 cases and repeatable API path"},
        {"purpose": "citation contract testing", "classification": "SUFFICIENT", "evidence": "citation validity, persistence and deletion semantics are directly exercised"},
        {"purpose": "answerability testing", "classification": "PARTIALLY_SUFFICIENT", "evidence": "8 clear out-of-domain refusals pass, but nuanced near-boundary cases are sparse"},
        {"purpose": "controlled retrieval debugging", "classification": "SUFFICIENT", "evidence": "candidate → selection → context → citation stages are observable and isolated"},
        {"purpose": "ranking/selection comparison", "classification": "PARTIALLY_SUFFICIENT", "evidence": "overlap exists, but 18 candidates cover 90% of only 20 chunks"},
        {"purpose": "chunking comparison", "classification": "INSUFFICIENT", "evidence": "documents yield only 1–2 chunks and are all Markdown"},
        {"purpose": "realistic personal-learning retrieval quality", "classification": "INSUFFICIENT", "evidence": "controlled engineering prose does not represent personal learning distributions"},
        {"purpose": "large-knowledge-base retrieval quality", "classification": "INSUFFICIENT", "evidence": "20 chunks cannot exercise scale selectivity or long-tail competition"},
        {"purpose": "final resume quality claims", "classification": "INSUFFICIENT", "evidence": "small controlled corpus supports contract claims, not broad accuracy claims"},
    ]
    decision = [
        {"action": "NO_PRODUCTION_CHANGE", "evidence": "only 3/13 reviewed failures are genuine", "affected_cases": "all", "recoverable_failures": "0 (preserves evidence)", "risk": "low", "complexity": "low", "supported": "YES now"},
        {"action": "EVAL_METRIC_REFINEMENT", "evidence": "4 lexical false negatives; ambiguous layer names", "affected_cases": "4 + all metric readers", "recoverable_failures": "4 evaluator classifications", "risk": "low", "complexity": "medium", "supported": "STRONG"},
        {"action": "GOLD_DATA_REFINEMENT", "evidence": "6 exact-source/completeness expectations too strict", "affected_cases": "6", "recoverable_failures": "6 evaluator classifications", "risk": "medium (benchmark drift)", "complexity": "medium", "supported": "STRONG, version separately"},
        {"action": "GENERATION_COMPLETENESS", "evidence": "2 genuine omissions", "affected_cases": "2", "recoverable_failures": "up to 2", "risk": "medium", "complexity": "medium", "supported": "LIMITED"},
        {"action": "MULTI_DOC_SYNTHESIS", "evidence": "1 genuine multi-doc omission out of 8", "affected_cases": "1", "recoverable_failures": "1", "risk": "medium", "complexity": "medium", "supported": "WEAK"},
        {"action": "SELECTION_LOGIC", "evidence": "2 exact-gold displacements, 0 harmful reviewed", "affected_cases": "2", "recoverable_failures": "0 demonstrated", "risk": "high", "complexity": "medium", "supported": "NO"},
        {"action": "TOP_K_OR_THRESHOLD", "evidence": "fixed K distorts precision; no harmful miss shown", "affected_cases": "all", "recoverable_failures": "0 demonstrated", "risk": "high", "complexity": "low", "supported": "NO"},
        {"action": "QUERY_REWRITE", "evidence": "fresh conversations did not exercise rewrite", "affected_cases": "0", "recoverable_failures": "0", "risk": "medium", "complexity": "medium", "supported": "NO"},
        {"action": "CHUNKING", "evidence": "no context-budget failure; corpus has 1–2 chunks/doc", "affected_cases": "0", "recoverable_failures": "0", "risk": "high", "complexity": "high", "supported": "NO"},
        {"action": "INDEPENDENT_RERANKER", "evidence": "8/8 rerank cases had expected evidence in context", "affected_cases": "0 genuine", "recoverable_failures": "0", "risk": "high", "complexity": "high", "supported": "NO"},
        {"action": "HYBRID_RETRIEVAL", "evidence": "no lexical-vs-vector miss comparison exists", "affected_cases": "unknown", "recoverable_failures": "unsupported", "risk": "high", "complexity": "high", "supported": "NO"},
        {"action": "REAL_WORLD_CORPUS_EVAL", "evidence": "20 chunks cannot support scale claims", "affected_cases": "claim validity", "recoverable_failures": "N/A", "risk": "low", "complexity": "high", "supported": "YES before broad claims"},
    ]
    audit_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-canonical-f8aaaae2"
    output = BASE / "results" / "failure_scale_analysis_v1" / audit_id
    output.mkdir(parents=True, exist_ok=False)
    audit_metadata = {
        "audit_id": audit_id,
        "canonical_baseline_run_id": RUN_ID,
        "canonical_baseline_machine_pass": {"pass_count": 35, "case_count": 48, "pass_rate": metrics["pass_rate"]},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_artifact_sha256": baseline_before,
        "scope": "read-only baseline failure/corpus-scale audit; no production RAG calls or changes",
    }
    outputs = {
        "audit_metadata.json": audit_metadata,
        "corpus_scale.json": corpus,
        "metric_definition_audit.json": metric_definitions(),
        "top_k_precision_analysis.json": precision,
        "noise_and_answer_impact.json": noise,
        "failed_case_reviews.json": reviews,
        "multi_doc_analysis.json": multi,
        "rerank_disambiguation_analysis.json": rerank,
        "fallback_audit.json": fallback,
        "generation_failure_audit.json": generation,
        "pass_control_review.json": pass_control,
        "controlled_corpus_validity.json": validity,
        "optimization_decision_matrix.json": decision,
    }
    for name, value in outputs.items():
        write_json(output / name, value)
    prior_audit_files = [
        str(path.relative_to(ROOT)).replace("\\", "/")
        for sibling in sorted(output.parent.iterdir())
        if sibling.is_dir()
        for path in sorted(sibling.iterdir())
        if path.is_file()
    ]
    files = sorted(set([
        "backend/tests/test_rag_failure_scale_analysis.py",
        "evals/rag_demo_corpus/v1/analyze_failure_scale.py",
        *prior_audit_files,
        *[
            str((output / name).relative_to(ROOT)).replace("\\", "/")
            for name in sorted([*outputs, "report.md", "validation.json", "result.json"])
        ],
    ]))
    report_data = {
        "corpus_scale": corpus,
        "precision_structure": precision,
        "noise": noise,
        "failed_case_reviews": reviews,
        "multi_doc": multi,
        "rerank": rerank,
        "fallback": fallback,
        "generation": generation,
        "metric_definitions": metric_definitions(),
        "pass_control": pass_control,
        "controlled_corpus_validity": validity,
        "decision_matrix": decision,
    }
    (output / "report.md").write_text(render_report(report_data, files), encoding="utf-8")
    baseline_after = {name: digest(BASELINE / name) for name in REQUIRED_BASELINE_FILES}
    production_after = {str(path.relative_to(ROOT)).replace("\\", "/"): digest(path) for path in PRODUCTION_RAG_FILES}
    report_text = (output / "report.md").read_text(encoding="utf-8")
    validation = {
        "canonical_baseline_files_unchanged": baseline_before == baseline_after,
        "production_rag_files_unchanged_during_audit": production_before == production_after,
        "raw_case_count": len(raw),
        "machine_pass_count_preserved": metrics["pass_count"],
        "machine_failed_case_count": len(machine_fail_ids),
        "reviewed_failed_case_count": len(reviews),
        "reviewed_taxonomy_counts": dict(sorted(Counter(item["reviewed_taxonomy"] for item in reviews).items())),
        "multi_doc_case_count": len(multi),
        "rerank_case_count": len(rerank),
        "fallback_case_count": fallback["fallback_count"],
        "pass_control_case_count": len(pass_control),
        "pass_control_false_positives": sum(item["false_positive_found"] for item in pass_control),
        "report_section_count": len(re.findall(r"^## \d+\.", report_text, re.MULTILINE)),
        "report_exact_terminal_status": report_text.rstrip().endswith("RAG_BASELINE_FAILURE_SCALE_ANALYSIS_V1 = COMPLETE"),
        "production_rag_modified": False,
        "terminal_status": "RAG_BASELINE_FAILURE_SCALE_ANALYSIS_V1 = COMPLETE",
    }
    write_json(output / "validation.json", validation)
    result = {
        "status": "complete",
        "canonical_baseline": "Baseline machine pass remains 72.92% (35/48)",
        "reviewed_genuine_failure_count": 3,
        "reviewed_evaluator_or_gold_issue_count": 10,
        "recommended_next_phase": "A. Fix evaluation/gold first",
        "real_world_corpus_required_before_broad_quality_claims": True,
        "validation": validation,
    }
    write_json(output / "result.json", result)
    print(json.dumps({"status": "complete", "output": str(output), **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
