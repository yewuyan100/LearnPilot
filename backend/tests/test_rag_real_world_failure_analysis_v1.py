from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "evals/rag_real_world_corpus/v1"
OUT = V1 / "failure_analysis_v1"
RUN = V1 / "results/dense_only_baseline_v1/20260814T052007Z-593cd2ac"
POST_C_PRODUCTION = V1 / "post_c_production_integrity_v1.json"

EXPECTED = {
    "gold": "33a0b69901fa47e3fe45be0277228cd4a5519fe780fe5b9d2c52b1bfe614927a",
    "freeze": "d979079be4eb901a825ab29414dd7b5124d030182e09b55eea1e93749c12a5c2",
    "corpus": "6f67d510cd35197f107400d33033972c0c3c84478174e4991e491f6c8e4ab563",
    "raw": "bf718aed08e226149c9310cbf20bf25c403708217e2908789120178ac5574e28",
    "semantic": "671fe1a484dd6ff8986b34c0ebf0826f274bbb9ed6dda404f18ad0a2bd60a176",
}


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_all_frozen_identities_and_semantic_detached_hash_are_unchanged():
    assert digest(V1 / "gold/v1/gold_cases.json") == EXPECTED["gold"]
    assert digest(V1 / "gold/v1/gold_dataset_v1_freeze_manifest.json") == EXPECTED["freeze"]
    assert digest(V1 / "corpus_manifest.json") == EXPECTED["corpus"]
    assert digest(RUN / "raw_results.json") == EXPECTED["raw"]
    assert digest(OUT / "semantic_claim_reviews.json") == EXPECTED["semantic"]
    detached = (OUT / "semantic_claim_reviews.sha256").read_text(encoding="ascii").split()[0]
    assert detached == EXPECTED["semantic"]


def test_semantic_review_covers_exactly_104_unique_claims_with_complete_metadata():
    data = load("semantic_claim_reviews.json")
    claims = [claim for case in data["case_reviews"] for claim in case["claim_reviews"]]
    assert len(data["case_reviews"]) == 54
    assert len(claims) == 104
    assert len({claim["claim_id"] for claim in claims}) == 104
    assert data["summary"]["coverage_complete"] is True
    required = {
        "case_id", "claim_id", "case_type", "tier", "topic", "difficulty",
        "query_language", "question", "gold_claim", "machine_answer",
        "selected_context_summary", "citations", "verdict", "review_reason",
    }
    assert all(required <= set(claim) for claim in claims)
    assert all(len(claim["review_reason"]) >= 20 for claim in claims)


def test_every_returned_citation_is_semantically_reviewed_and_missing_groups_are_explicit():
    raw = json.loads((RUN / "raw_results.json").read_text(encoding="utf-8"))
    citations = load("citation_semantic_reviews.json")
    actual_count = sum(len(case["citations"]) for case in raw["cases"])
    assert actual_count == 97
    assert len(citations["citation_reviews"]) == actual_count
    assert len({row["citation_review_id"] for row in citations["citation_reviews"]}) == actual_count
    assert all(row["validity_status"] == "CITATION_VALID" for row in citations["citation_reviews"])
    assert citations["summary"]["returned_citations_reviewed"] == actual_count
    assert citations["summary"]["coverage_complete"] is True
    assert all(row["status"] == "CITATION_MISSING" for row in citations["missing_required_evidence_groups"])


def test_case_and_combined_claim_coverage_is_complete_and_unique():
    analysis = load("case_failure_analysis.json")
    cases = analysis["cases"]
    claims = [claim for case in cases for claim in case["claim_reviews"]]
    assert len(cases) == 72
    assert len({case["case_id"] for case in cases}) == 72
    assert len(claims) == 132
    assert len({claim["claim_id"] for claim in claims}) == 132
    assert all(claim["final_status"] in {"PASS", "PARTIAL", "FAIL"} for claim in claims)


def test_exactly_one_primary_root_cause_per_case_and_totals_equal_72():
    analysis = load("case_failure_analysis.json")
    summary = load("root_cause_summary.json")
    cases = analysis["cases"]
    allowed = {
        "RETRIEVAL_MISS", "SELECTION_RANKING_MISS", "SELECTION_THRESHOLD_MISS",
        "SELECTION_DEDUP_MISS", "SELECTION_DIVERSITY_MISS",
        "SELECTION_CONTEXT_BUDGET_MISS", "ANSWERABILITY_FALSE_NEGATIVE",
        "GENERATION_FACT_ERROR", "GENERATION_OMISSION", "GENERATION_OVERCLAIM",
        "GENERATION_EXTRACTION_ERROR", "MULTI_DOC_SYNTHESIS_FAILURE",
        "CITATION_ONLY_FAILURE", "EVAL_MAPPING_DIAGNOSTIC", "NO_FAILURE",
        "OTHER_VERIFIED",
    }
    assert all(isinstance(case["primary_root_cause"], str) for case in cases)
    assert all(case["primary_root_cause"] in allowed for case in cases)
    assert sum(summary["primary_root_cause_counts"].values()) == 72
    assert summary["case_count"] == 72
    assert "OTHER_VERIFIED" not in summary["primary_root_cause_counts"]


def test_all_nonpassing_cases_have_a_verified_failure_root_and_no_failure_cases_really_pass():
    cases = load("case_failure_analysis.json")["cases"]
    for case in cases:
        if case["primary_root_cause"] == "NO_FAILURE":
            assert case["case_verdict"] in {"FULL_PASS", "CORRECT_REFUSAL"}
            assert case["citation_review"]["semantic_citation_status"] == "PASS"
        if case["case_verdict"] in {"PARTIAL_PASS", "FAIL", "INCORRECT_REFUSAL"}:
            assert case["primary_root_cause"] not in {
                "NO_FAILURE", "EVAL_MAPPING_DIAGNOSTIC", "CITATION_ONLY_FAILURE"
            }


def test_citation_only_failures_have_correct_answers_and_failed_citation_coverage():
    cases = load("case_failure_analysis.json")["cases"]
    citation_only = [case for case in cases if case["primary_root_cause"] == "CITATION_ONLY_FAILURE"]
    assert {case["case_id"] for case in citation_only} == {
        "rw-gold-v1-semantic-checkpointer-store",
        "rw-gold-v1-multi-agent-resume",
    }
    assert all(case["case_verdict"] == "FULL_PASS" for case in citation_only)
    assert all(case["citation_review"]["semantic_citation_status"] == "FAIL" for case in citation_only)


def test_addressability_is_linked_to_verified_stage_evidence():
    matrix = load("optimization_addressability_matrix.json")
    assert len(matrix["entries"]) == 72
    for entry in matrix["entries"]:
        root = entry["primary_root_cause"]
        if entry["dimensions"]["hybrid"] == "HIGH":
            assert root == "RETRIEVAL_MISS"
            assert entry["evidence"]["candidate_required_evidence_missing"] is True
            assert entry["evidence"]["lexical_signature"]
        if entry["dimensions"]["reranker"] == "HIGH":
            assert root in {"SELECTION_RANKING_MISS", "SELECTION_DIVERSITY_MISS"}
            assert entry["evidence"]["candidate_required_evidence_ranks"]
            assert entry["evidence"]["selected_required_evidence_sufficient"] is False


def test_ablation_hypotheses_target_only_evidence_backed_roots():
    hypotheses = load("ablation_hypotheses.json")["arms"]
    matrix = load("optimization_addressability_matrix.json")["entries"]
    hybrid_expected = {entry["case_id"] for entry in matrix if entry["addressability_class"] == "HYBRID_ADDRESSABLE"}
    rerank_expected = {entry["case_id"] for entry in matrix if entry["addressability_class"] == "RERANKER_ADDRESSABLE"}
    assert set(hypotheses["hybrid"]["target_case_ids"]) == hybrid_expected
    assert set(hypotheses["dense_rerank"]["target_case_ids"]) == rerank_expected
    assert hypotheses["hybrid_rerank"]["requires_both_case_ids"] == []


def test_production_code_hashes_still_equal_the_frozen_baseline_binding():
    raw = json.loads((RUN / "raw_results.json").read_text(encoding="utf-8"))
    manifest = load("failure_analysis_manifest.json")
    production = json.loads(POST_C_PRODUCTION.read_text(encoding="utf-8"))
    assert manifest["frozen_bindings"]["production_code"]["all_match"] is True
    assert production["strict_equality_required"] is True
    assert production["hash_algorithm"] == "SHA-256"
    assert production["file_count"] == len(production["baseline_sha256"]) == 15
    assert set(production["baseline_sha256"]) == set(raw["production_code_sha256"])
    for relative_path, expected_hash in production["baseline_sha256"].items():
        assert digest(ROOT / relative_path) == expected_hash


def test_manifest_declares_diagnosis_only_and_complete_status():
    manifest = load("failure_analysis_manifest.json")
    declarations = manifest["execution_declarations"]
    assert manifest["coverage"] == {
        "cases": 72, "combined_claims": 132, "returned_citations": 97, "semantic_claims": 104
    }
    assert declarations["external_llm_calls"] == 0
    assert declarations["deepseek_calls"] == 0
    assert declarations["production_rag_ask_calls"] == 0
    assert declarations["embedding_executions"] == 0
    assert declarations["faiss_retrieval_executions"] == 0
    assert declarations["baseline_rerun"] is False
    assert declarations["production_modified"] is False
    assert declarations["optimization_performed"] is False
    assert manifest["status"] == "COMPLETE"
    assert manifest["ready_for_ablation_design"] is True


def test_manifest_artifact_and_analysis_code_hashes_are_current():
    manifest = load("failure_analysis_manifest.json")
    for relative_path, expected_hash in manifest["artifact_sha256"].items():
        assert digest(ROOT / relative_path) == expected_hash
    for relative_path, expected_hash in manifest["analysis_code_identity"].items():
        assert digest(ROOT / relative_path) == expected_hash
