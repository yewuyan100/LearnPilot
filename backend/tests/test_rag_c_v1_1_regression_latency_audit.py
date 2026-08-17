import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "evals/rag_real_world_corpus/v1"
RUN = V1 / "results/c_v1_1_regression_latency_audit/20260814T142012Z-015c3ca0"
REPORT = ROOT / "RAG_C_V1_1_REGRESSION_LATENCY_AUDIT.md"


def load(name: str):
    return json.loads((RUN / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_frozen_identity_gate_is_exact():
    data = load("integrity_preflight.json")
    assert data["status"] == "PASS"
    assert data["ablation_design_sha256"] == "442bedce1c43b27b3557b0055708342edd278e98bcac0c12a68c1390fe88f655"
    assert data["phase2_run_id"] == "20260814T095542Z-1317c6a7"
    assert data["phase3_run_id"] == "20260814T123142Z-8852712b"
    assert data["phase4_run_id"] == "20260814T131417Z-04dfc031"
    assert all(item["match"] for item in data["frozen_hashes"].values())
    assert all(not item["errors"] for item in data["phase_manifests"])


def test_exact_two_regressions_have_identical_pre_rerank_pools():
    cases = load("regression_case_audit.json")["cases"]
    assert {item["case_id"] for item in cases} == {
        "rw-gold-v1-semantic-context-order",
        "rw-gold-v1-disambig-fastapi-async-deps",
    }
    for case in cases:
        assert len(case["candidate_rows_dense_order"]) == 18
        assert case["pre_rerank_pool"] == {
            "a_dense_top18_count": 18,
            "c_dense_top18_count": 18,
            "identities_identical": True,
            "ranks_scores_identical": True,
            "all_candidates_admitted_in_both": True,
        }


def test_regression_cause_and_actionability_are_evidence_bound():
    cases = load("regression_case_audit.json")["cases"]
    for case in cases:
        assert case["independent_dominant_cause"] == "CITATION_SEMANTIC_SUPPORT"
        assert case["phase4_causal_trace_cause"] == "CITATION_SEMANTIC_SUPPORT"
        assert case["cause_alignment"] is True
        assert case["context_comparison"] == "EQUALLY_OR_MORE_SUFFICIENT_C_CONTEXT_BUT_WORSE_GENERATION"
        assert case["actionability"] == "GENERATION_ADDRESSABLE"
        assert case["confidence"] == "HIGH_CONFIDENCE"
        assert case["would_serving_only_optimization_leave_regression_unchanged"] == "YES"


def test_execution_is_singleton_fully_batched_and_inference_only():
    data = load("implementation_architecture.json")
    assert data["model_load_scope"] == "per process"
    assert data["model_instance_count_in_phase2_runner"] == 1
    assert data["tokenization"] == "pair-by-pair encode inside one 18-pair call"
    assert data["forward_pass"] == "single dynamically padded batch"
    assert data["pair_count"] == 18
    assert data["all_pairs_passed_simultaneously"] is True
    assert data["accidentally_sequential_forward"] is False
    assert all(data["source_contract_checks"].values())


def test_microprofile_uses_only_frozen_local_inputs_and_matches_scores():
    data = load("reranker_microprofile.json")
    assert data["model_runtime"]["local_files_only"] is True
    assert data["model_runtime"]["automatic_downloads"] == 0
    assert data["model_runtime"]["device"] == "cpu"
    assert data["model_runtime"]["dtype"] == "torch.float32"
    assert data["local_reranker_model_initializations"] == 1
    assert data["local_reranker_inference_calls"] == 5
    assert data["local_reranker_pairs_scored"] == 90
    assert all(row["ranking_order_matches_frozen_phase2"] for row in data["measurements"])
    assert all(row["all_scores_bitwise_equal_to_frozen_phase2"] for row in data["measurements"])
    assert max(row["max_absolute_score_difference"] for row in data["measurements"]) == 0.0


def test_forward_is_measured_primary_bottleneck():
    data = load("reranker_microprofile.json")
    assert data["primary_latency_bottleneck"] == "forward_ms"
    assert data["secondary_latency_bottleneck"] == "tokenization_ms"
    assert data["forward_fraction_of_warm_p50"] > 0.99
    assert data["warm_summary_ms"]["total_reranker_call_ms"]["p50"] > 7000
    assert data["warm_summary_ms"]["tokenization_ms"]["p50"] < 20


def test_token_lengths_match_all_frozen_phase2_pairs():
    data = load("token_length_profile.json")["token_lengths"]
    assert data["query_count"] == 72
    assert data["pair_count"] == 1296
    assert data["pairs_reaching_1024_cap"] == 0
    assert data["truncation_count"] == 0
    assert data["frozen_phase2_input_token_telemetry_match"] is True
    assert data["pair_token_length"]["max"] == 379
    assert data["most_chunks_substantially_below_cap"] is True


def test_depth_analysis_does_not_select_an_alternative_depth():
    data = load("candidate_depth_analysis.json")
    assert data["case_count"] == 72
    assert data["historical_depth_conclusion"] == "18_REMAINS_NECESSARY_TO_REPRODUCE_OBSERVED_C_V1_1_BENEFIT"
    assert data["fixed_cases_with_selected_required_evidence_beyond_top12"] == [
        "rw-gold-v1-long-bge-training"
    ]
    fixed = {row["case_id"]: row for row in data["fixed_case_required_evidence_ranks"]}
    assert 15 in fixed["rw-gold-v1-long-bge-training"]["selected_required_evidence_dense_ranks"]
    assert "no alternative depth rescoring" in data["analysis_scope"]


def test_decision_is_target_cpu_impractical_without_selecting_parameters():
    data = load("optimization_decision.json")
    assert data["recommended_c_v1_2_optimization_class"] == "D. CURRENT_RERANKER_NOT_PRACTICAL_ON_TARGET_CPU"
    assert data["no_parameters_selected"] is True
    assert data["no_implementation_performed"] is True
    assert len(data["serving_only_optimization_candidates"]) >= 8
    assert len(data["semantic_or_runtime_change_candidates"]) == 7


def test_production_files_are_byte_identical():
    data = load("production_hash_verification.json")
    assert data["checked_file_count"] == 15
    assert data["all_match_phase2"] is True
    assert data["all_byte_identical_during_audit"] is True
    assert all(row["matches_phase2"] and row["byte_identical_during_audit"] for row in data["rows"])


def test_zero_external_retrieval_generation_and_production_changes():
    data = load("reranker_microprofile.json")
    for key in (
        "external_requests",
        "deepseek_calls",
        "new_retrieval_runs",
        "new_generation_runs",
        "new_semantic_experiment_outputs",
    ):
        assert data[key] == 0


def test_report_has_18_sections_and_exact_status_ending():
    report = REPORT.read_text(encoding="utf-8")
    assert len(re.findall(r"(?m)^## \d+\. ", report)) == 18
    assert report.endswith(
        "RAG_C_V1_1_REGRESSION_LATENCY_AUDIT = PASS\n"
        "READY_FOR_C_V1_2_OPTIMIZATION = YES\n"
    )
