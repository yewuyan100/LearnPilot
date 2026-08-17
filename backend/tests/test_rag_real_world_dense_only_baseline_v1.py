from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "evals/rag_real_world_corpus/v1/dense_only_baseline_v1"
sys.path.insert(0, str(HARNESS))

from dense_baseline_metrics import (  # noqa: E402
    build_artifacts,
    citation_evaluation,
    compute,
    evaluate_claim,
    group_coverage,
)


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_frozen_real_world_bindings_match_exact_v1_identities():
    base = ROOT / "evals/rag_real_world_corpus/v1"
    assert digest(base / "corpus_manifest.json") == "6f67d510cd35197f107400d33033972c0c3c84478174e4991e491f6c8e4ab563"
    assert digest(base / "gold/v1/gold_cases.json") == "33a0b69901fa47e3fe45be0277228cd4a5519fe780fe5b9d2c52b1bfe614927a"
    assert digest(base / "gold/v1/gold_dataset_v1_freeze_manifest.json") == "d979079be4eb901a825ab29414dd7b5124d030182e09b55eea1e93749c12a5c2"


def test_evidence_groups_use_or_within_and_and_across_required_groups():
    groups = [
        {
            "evidence_group_id": "g1",
            "required": True,
            "any_of_document_ids": ["doc-a", "doc-a-alternate"],
            "any_of_evidence_ids": ["ev-a", "ev-a-alternate"],
        },
        {
            "evidence_group_id": "g2",
            "required": True,
            "any_of_document_ids": ["doc-b"],
            "any_of_evidence_ids": ["ev-b"],
        },
    ]
    complete = group_coverage(
        groups,
        [
            {"document_id": "doc-a-alternate", "evidence_ids": ["ev-a-alternate"]},
            {"document_id": "doc-b", "evidence_ids": ["ev-b"]},
        ],
    )
    incomplete = group_coverage(
        groups, [{"document_id": "doc-a", "evidence_ids": ["ev-a"]}]
    )
    assert complete["document_pass"] is True
    assert complete["anchor_pass"] is True
    assert incomplete["document_pass"] is False
    assert incomplete["anchor_pass"] is False


def test_semantic_review_is_never_replaced_with_a_lexical_proxy():
    claim = {
        "claim_id": "semantic-1",
        "canonical_claim": "The answer must explain the mechanism.",
        "required": True,
        "evaluation_mode": "SEMANTIC_REVIEW",
    }
    result = evaluate_claim(claim, "The answer must explain the mechanism.", True, 1)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["machine_pass"] is None


def test_exact_and_answerability_claim_modes_are_deterministic():
    exact = {
        "claim_id": "exact-1",
        "canonical_claim": "Dimension and length",
        "required": True,
        "evaluation_mode": "NUMERIC_EXACT",
        "deterministic_match": {"all_terms": ["1024", "8192"]},
    }
    answerability = {
        "claim_id": "unanswerable-1",
        "canonical_claim": "Corpus does not answer",
        "required": True,
        "evaluation_mode": "ANSWERABILITY_ONLY",
    }
    assert evaluate_claim(exact, "dimension 1024 and length 8192", True, 1)["machine_pass"] is True
    assert evaluate_claim(exact, "dimension 1024", True, 1)["machine_pass"] is False
    assert evaluate_claim(answerability, "refusal", False, 0)["machine_pass"] is True
    assert evaluate_claim(answerability, "unsupported answer", True, 1)["machine_pass"] is False


def test_forbidden_citations_and_required_citation_coverage_are_checked():
    unanswerable = {
        "evidence_groups": [],
        "citation_contract": {
            "citation_required": False,
            "forbid_citations": True,
            "minimum_distinct_required_documents": 0,
        },
    }
    answerable = {
        "evidence_groups": [
            {
                "evidence_group_id": "g1",
                "required": True,
                "any_of_document_ids": ["doc-a"],
                "any_of_evidence_ids": ["ev-a"],
            }
        ],
        "citation_contract": {
            "citation_required": True,
            "forbid_citations": False,
            "minimum_distinct_required_documents": 1,
        },
    }
    citation = {
        "source_label": "S1",
        "chunk_id": 1,
        "material_id": 1,
        "document_id": "doc-a",
        "evidence_ids": ["ev-a"],
        "source_available": True,
    }
    assert citation_evaluation(unanswerable, [citation])["machine_contract_pass"] is False
    assert citation_evaluation(answerable, [citation])["machine_contract_pass"] is True


def test_metrics_artifacts_recompute_from_frozen_raw_without_semantic_proxy(tmp_path):
    case = {
        "case_id": "case-1",
        "tier": "CORE",
        "case_type": "single_doc_fact",
        "primary_topic": "rag_retrieval",
        "difficulty": "easy",
        "query_language": "en",
        "answerable": True,
        "question": "What is the value?",
        "evidence_groups": [
            {
                "evidence_group_id": "g1",
                "required": True,
                "any_of_document_ids": ["doc-a"],
                "any_of_evidence_ids": ["ev-a"],
            }
        ],
        "claims": [
            {
                "claim_id": "claim-1",
                "canonical_claim": "Value is 1024",
                "required": True,
                "evaluation_mode": "NUMERIC_EXACT",
                "deterministic_match": {"all_terms": ["1024"]},
            },
            {
                "claim_id": "claim-2",
                "canonical_claim": "Meaning is correct",
                "required": True,
                "evaluation_mode": "SEMANTIC_REVIEW",
            },
        ],
        "citation_contract": {
            "citation_required": True,
            "forbid_citations": False,
            "minimum_distinct_required_documents": 1,
        },
        "acceptable_supporting_evidence": [],
        "plausible_distractor_documents": [],
    }
    source = {
        "source_label": "S1",
        "chunk_id": 1,
        "material_id": 1,
        "document_id": "doc-a",
        "evidence_ids": ["ev-a"],
        "source_available": True,
    }
    raw = {
        "run_id": "synthetic-run",
        "cases": [
            {
                "sequence": 1,
                "case_run_id": "synthetic-case-run",
                "execution_status": "COMPLETED",
                "gold_case": case,
                "diagnostic": {"candidates": [source]},
                "retrieval": {"selected_sources": [source]},
                "response": {
                    "assistant_message": {"content": "1024", "answerable": True},
                    "model": {"fallback_used": False},
                },
                "citations": [source],
                "latency": {"ask_http_ms": 10, "generation_observed_ms": 5},
                "generation": {"aggregate_usage": {"input_tokens": 10, "output_tokens": 2}},
                "retry_and_error_summary": {},
            }
        ],
    }
    raw_path = tmp_path / "raw_results.json"
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    expected = compute(raw)
    build_artifacts(raw_path, tmp_path)
    persisted = json.loads((tmp_path / "retrieval_metrics.json").read_text(encoding="utf-8"))
    assert persisted == expected["retrieval_metrics"]
    assert expected["claim_metrics"]["semantic_machine_pass_rate"] is None


def test_completed_latest_run_has_72_unique_frozen_records_when_present():
    pointer = ROOT / "evals/rag_real_world_corpus/v1/results/dense_only_baseline_v1/latest_run.json"
    if not pointer.is_file():
        pytest.skip("baseline has not executed yet")
    latest = json.loads(pointer.read_text(encoding="utf-8"))
    raw_path = ROOT / latest["run_dir"] / "raw_results.json"
    detached = (raw_path.parent / "raw_results.sha256").read_text(encoding="utf-8").split()[0]
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    assert digest(raw_path) == detached
    assert len(raw["cases"]) == 72
    assert len({item["case_run_id"] for item in raw["cases"]}) == 72
    assert len({item["case_id"] for item in raw["cases"]}) == 72
    assert all(item["execution_status"] == "COMPLETED" for item in raw["cases"])
    validation = json.loads((raw_path.parent / "validation.json").read_text(encoding="utf-8"))
    assert validation["production_code_unchanged"] is True
    assert validation["production_runtime_state_unchanged"] is True
    assert validation["protected_corpus_gold_freeze_unchanged"] is True
