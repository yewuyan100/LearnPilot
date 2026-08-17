import hashlib
import json
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "evals/rag_real_world_corpus/v1"
RUN = V1 / "results/c_v1_2_onnx_runtime_equivalence/20260814T145246Z-298674d5"
REPORT = ROOT / "RAG_C_V1_2_ONNX_RUNTIME_EQUIVALENCE.md"


def load(name: str):
    return json.loads((RUN / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def test_frozen_bindings_and_authoritative_manifests_are_exact():
    data = load("integrity_preflight.json")
    assert data["status"] == "PASS"
    assert data["ablation_design_sha256"] == "442bedce1c43b27b3557b0055708342edd278e98bcac0c12a68c1390fe88f655"
    assert data["phase2_run_id"] == "20260814T095542Z-1317c6a7"
    assert data["phase3_run_id"] == "20260814T123142Z-8852712b"
    assert data["phase4_run_id"] == "20260814T131417Z-04dfc031"
    assert data["c_v1_1_audit_run_id"] == "20260814T142012Z-015c3ca0"
    assert all(not item["errors"] for item in data["verified_manifests"].values())
    assert all(item["match"] for item in data["fixed_hashes"].values())


def test_onnx_runtime_and_export_contract_is_fp32_cpu_only():
    runtime = load("runtime_manifest.json")
    export = load("model_export_manifest.json")
    assert runtime["target_runtime"] == "ONNX Runtime CPUExecutionProvider FP32"
    assert runtime["onnx_session"]["providers"] == ["CPUExecutionProvider"]
    assert runtime["onnx_session"]["graph_optimization_level"] == "ORT_ENABLE_ALL"
    assert runtime["onnx_session"]["execution_mode"] == "ORT_SEQUENTIAL"
    assert runtime["onnx_session"]["intra_op_num_threads"] == 8
    assert runtime["onnx_session"]["inter_op_num_threads"] == 1
    assert runtime["semantic_contract_changes"] == 0
    assert export["export"]["opsets_observed"] == {"ai.onnx": 17}
    assert export["export"]["initializer_data_type_counts"] == {"1": 393}


def test_model_tokenizer_and_onnx_artifact_identity_are_bound():
    preflight = load("integrity_preflight.json")
    export = load("model_export_manifest.json")
    source = export["source"]
    assert source["model_id"] == "BAAI/bge-reranker-v2-m3"
    assert source["revision"] == "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
    assert source["model_safetensors_sha256"] == "d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286"
    assert export["source_snapshot_unchanged_after_export"] is True
    snapshot_names = {row["name"] for row in preflight["snapshot_files"]}
    assert {"tokenizer.json", "tokenizer_config.json", "sentencepiece.bpe.model"} <= snapshot_names
    onnx = next(row for row in export["artifact_files"] if row["path"].endswith(".onnx"))
    onnx_path = ROOT / onnx["path"]
    assert onnx["sha256"] == "4710a4911421f95a9d56a401d98a5256eb252a867e7bd2c1c6bf691386542c55"
    assert sha256(onnx_path) == onnx["sha256"]
    assert all((ROOT / row["path"]).stat().st_size == row["size_bytes"] for row in export["artifact_files"])


def test_exact_input_equivalence_covers_72_by_18_without_truncation():
    data = load("input_equivalence.json")
    assert data["query_count"] == 72
    assert data["pair_count"] == 1296
    assert data["candidate_depth"] == 18
    assert data["all_candidate_orders_match_frozen_dense_order"] is True
    assert data["all_frozen_pair_token_counts_match"] is True
    assert data["truncation_count"] == 0
    assert data["input_names"] == ["input_ids", "attention_mask"]
    assert data["output_names"] == ["logits"]
    assert all(row["pair_count"] == 18 for row in data["rows"])
    assert sum(len(row["pairs"]) for row in data["rows"]) == 1296


def test_score_rows_and_runtime_output_shapes_are_complete():
    scores = load("per_pair_score_comparison.json")
    latency = load("latency_measurements.json")
    assert scores["score_difference_statistics"]["pair_count"] == 1296
    assert len(scores["rows"]) == 1296
    assert all(math.isfinite(row["pytorch_score"]) and math.isfinite(row["onnx_score"]) for row in scores["rows"])
    assert all(row["absolute_difference"] >= 0 for row in scores["rows"])
    assert latency["first_inference"]["output_shape"] == [18, 1]
    assert all(row["output_shape"] == [18, 1] for row in latency["onnx_profile_measurements"])


def test_pytorch_onnx_ranking_and_near_tie_determinism_are_exact():
    semantic = load("semantic_equivalence.json")
    scores = load("per_pair_score_comparison.json")
    queries = load("per_query_ranking_comparison.json")["rows"]
    assert semantic["semantic_equivalence"] == "PASS"
    assert semantic["reranker_order_exact_count"] == 72
    assert not semantic["ordering_mismatches"]
    assert all(row["rank_equal"] for row in scores["rows"])
    assert all(row["pytorch_order"] == row["onnx_order"] for row in queries)
    deterministic = semantic["near_tie_determinism"]
    assert deterministic["repeat_count"] == 3
    assert deterministic["scores_bitwise_deterministic"] is True
    assert deterministic["orders_deterministic"] is True


def test_frozen_governance_top6_context_and_required_evidence_are_exact():
    semantic = load("semantic_equivalence.json")
    governance = load("governance_context_comparison.json")
    queries = load("per_query_ranking_comparison.json")["rows"]
    assert semantic["governed_top6_exact_count"] == 72
    assert semantic["context_digest_exact_count"] == 72
    assert semantic["required_evidence_presence_exact_count"] == 72
    assert governance["governance_mismatches"] == []
    assert governance["context_mismatches"] == []
    assert governance["required_evidence_regressions"] == []
    assert all(row["pytorch_top6"] == row["onnx_top6"] for row in queries)
    assert all(row["pytorch_context_digest"] == row["onnx_context_digest"] for row in queries)


def test_near_tie_audit_is_descriptive_and_complete():
    data = load("near_tie_analysis.json")
    assert data["adjacent_pair_count"] == 72 * 17
    assert data["minimum_adjacent_score_margin"]["margin"] == 0.0
    assert data["margin_distribution"]["p1"] <= data["margin_distribution"]["p5"] <= data["margin_distribution"]["p50"]
    assert data["descriptive_near_tie_counts"]["margin_lte_1e-06"] == 8
    assert "no production threshold" in data["threshold_caveat"]


def test_latency_evidence_supports_exact_class_b_decision():
    latency = load("latency_measurements.json")
    decision = load("final_decision_evidence.json")
    assert latency["paired_representative_total_p50_speedup"] < 1.0
    assert latency["onnx_warm_summary_ms"]["total_reranker_call_ms"]["p50"] > 10_000
    assert decision["classification"] == "B. ONNX_FP32_EQUIVALENT_BUT_SPEEDUP_INSUFFICIENT"
    assert decision["interactive_learnpilot_latency_plausible"] is False
    assert decision["production_promotion_performed"] is False


def test_candidate_depth_retrieval_and_production_semantics_did_not_change():
    runtime = load("runtime_manifest.json")
    environment = load("environment_identity.json")
    assert runtime["candidate_depth"] == 18
    assert runtime["top_k"] == 6
    assert runtime["semantic_contract_changes"] == 0
    assert environment["production_dependency_files_modified"] is False
    assert load("external_call_audit.json")["retrieval_runs"] == 0


def test_production_files_remain_byte_identical():
    data = load("production_hash_verification.json")
    assert data["checked_file_count"] == 15
    assert data["all_match_frozen_reference"] is True
    assert data["all_byte_identical_during_experiment"] is True
    assert all(row["matches_frozen_reference"] and row["byte_identical_during_experiment"] for row in data["rows"])


def test_zero_generation_evaluator_model_hub_and_phase_rerun_calls():
    data = load("external_call_audit.json")
    for key in (
        "deepseek_calls",
        "openai_calls",
        "other_external_evaluator_calls",
        "model_hub_calls",
        "model_downloads",
        "generation_calls",
        "retrieval_runs",
        "phase3_or_phase4_reruns",
        "production_modifications",
    ):
        assert data[key] == 0
    assert data["dependency_registry_commands"] == 2
    assert data["dependency_install_scope"] == ".tmp/c_v1_2_onnx_runtime/site-packages only"


def test_report_has_17_sections_and_exact_status_ending():
    report = REPORT.read_text(encoding="utf-8")
    assert len(re.findall(r"(?m)^## \d+\. ", report)) == 17
    assert report.endswith(
        "RAG_C_V1_2_ONNX_RUNTIME_AUDIT = PASS\n"
        "READY_FOR_C_PRODUCTION_DECISION = YES\n"
    )
