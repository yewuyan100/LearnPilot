import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "evals" / "rag_demo_corpus" / "v1"
sys.path.insert(0, str(EVAL))

from baseline_metrics import compute_run, reconstruct_context  # noqa: E402


def test_frozen_baseline_gold_distribution_and_document_references():
    manifest = json.loads((EVAL / "corpus_manifest.json").read_text(encoding="utf-8"))
    gold = json.loads((EVAL / "gold_cases.json").read_text(encoding="utf-8"))
    document_ids = {item["document_id"] for item in manifest["documents"]}

    assert len(gold["cases"]) == 48
    assert {
        case_type: sum(item["type"] == case_type for item in gold["cases"])
        for case_type in {item["type"] for item in gold["cases"]}
    } == {
        "single_doc_fact": 8,
        "semantic_paraphrase": 8,
        "multi_doc": 8,
        "rerank_disambiguation": 8,
        "citation_sensitive": 8,
        "unanswerable": 8,
    }
    assert all(set(item["expected_document_ids"]).issubset(document_ids) for item in gold["cases"])


def test_reconstruct_context_applies_threshold_and_material_diversity():
    results = [
        {
            "score": 0.9 - index / 100,
            "material_id": 1 if index < 4 else 2,
            "chunk_id": index + 1,
            "chunk_index": index,
            "original_filename": "a.md" if index < 4 else "b.md",
            "content": f"distinct evidence {index} " * 10,
        }
        for index in range(6)
    ]
    result = reconstruct_context(
        results,
        candidate_expansion=6,
        top_k=4,
        min_score=0.35,
        max_sources=4,
        max_chunk_chars=2200,
        max_context_chars=12000,
    )
    assert len(result["candidate_sources"]) == 6
    assert len(result["selected_context_sources"]) == 4
    assert {item["material_id"] for item in result["selected_context_sources"]} == {1, 2}


def test_compute_run_classifies_retrieval_miss_before_answer_failure():
    metadata = {
        "filename_to_document_id": {"other.md": "lp-rag-v1-a02"},
        "document_topics": {"lp-rag-v1-a01": "rag_retrieval", "lp-rag-v1-a02": "rag_retrieval"},
        "rag_configuration": {
            "candidate_expansion": 18, "top_k": 6, "min_score": 0.35,
            "max_sources": 6, "max_chunk_chars": 2200, "max_context_chars": 12000,
        },
    }
    raw = [{
        "case": {
            "case_id": "rag-v1-test", "question": "q", "type": "single_doc_fact",
            "difficulty": "easy", "answerable": True,
            "expected_document_ids": ["lp-rag-v1-a01"], "key_facts": ["expected fact"],
            "citation_expectations": {
                "required": True, "minimum_distinct_documents": 1,
                "must_cite_document_ids": ["lp-rag-v1-a01"], "forbid_citations": False,
            },
        },
        "diagnostic_search": {"response_json": {"results": [{
            "rank": 1, "score": 0.9, "material_id": 2, "chunk_id": 2,
            "chunk_index": 0, "original_filename": "other.md", "content": "other fact",
        }]}},
        "ask": {"status_code": 200, "elapsed_ms": 10, "response_json": {
            "assistant_message": {
                "answerable": False, "content": "insufficient", "citations": [],
                "refusal_reason": "below_score_threshold", "latency_ms": 0,
            },
            "retrieval": {"source_count": 1, "duration_ms": 1},
            "model": {"fallback_used": False},
        }},
    }]
    result = compute_run(raw, metadata)
    assert result["cases"][0]["failure_stage"] == "RETRIEVAL_MISS"
