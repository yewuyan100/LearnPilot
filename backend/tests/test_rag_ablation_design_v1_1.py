from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
V1_ROOT = ROOT / "evals/rag_real_world_corpus/v1"
DESIGN_V1 = V1_ROOT / "ablation_design_v1"
DESIGN_V1_1 = V1_ROOT / "ablation_design_v1_1"
FAILURE = V1_ROOT / "failure_analysis_v1"
POST_C_PRODUCTION = V1_ROOT / "post_c_production_integrity_v1.json"
GOLD_HELPERS = V1_ROOT / "gold/v1"
if str(GOLD_HELPERS) not in sys.path:
    sys.path.insert(0, str(GOLD_HELPERS))

from gold_common import json_schema_errors  # noqa: E402


EXPECTED = {
    "v1_design": "4c3b2e294b63dcc0ae57be1d30d713b3cf1ffed5b0f3a989499f1298902703c6",
    "v1_1_design": "442bedce1c43b27b3557b0055708342edd278e98bcac0c12a68c1390fe88f655",
    "v1_1_schema": "929fe7aeff73554c921f6a55eb9de35d7ab4996a240e3f357f02875d9eba6820",
    "audit": "8e31f700d4d1a4d18ef102b38b13681eedfa02d7ea24fd641fd566c886f66f8b",
    "gold": "33a0b69901fa47e3fe45be0277228cd4a5519fe780fe5b9d2c52b1bfe614927a",
    "freeze": "d979079be4eb901a825ab29414dd7b5124d030182e09b55eea1e93749c12a5c2",
    "corpus": "6f67d510cd35197f107400d33033972c0c3c84478174e4991e491f6c8e4ab563",
    "baseline_raw": "bf718aed08e226149c9310cbf20bf25c403708217e2908789120178ac5574e28",
    "failure_manifest": "e869fd73e2570413595c1af194b6ec6876e8b822fbd4eac279541a03cac27fb8",
    "hypotheses": "27184ff8ddbf628f78767ede545e202ee66cb9ff17f56728961a8ce2d801f610",
}


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def design_v1():
    return load(DESIGN_V1 / "ablation_design_manifest.json")


def design_v1_1():
    return load(DESIGN_V1_1 / "ablation_design_manifest.json")


def assert_before(stages: list[str], earlier: str, later: str) -> None:
    assert stages.index(earlier) < stages.index(later)


def test_v1_1_manifest_is_schema_valid_complete_and_detached_hash_bound():
    manifest_path = DESIGN_V1_1 / "ablation_design_manifest.json"
    schema_path = DESIGN_V1_1 / "ablation_design_manifest.schema.json"
    manifest = load(manifest_path)
    schema = load(schema_path)
    assert json_schema_errors(manifest, schema) == []
    assert manifest["design_version"] == "V1.1"
    assert manifest["status"] == "COMPLETE"
    assert manifest["ready_for_hybrid_rerank_implementation"] is True
    assert digest(schema_path) == EXPECTED["v1_1_schema"]
    assert digest(manifest_path) == EXPECTED["v1_1_design"]
    detached = (DESIGN_V1_1 / "ablation_design_manifest.sha256").read_text(
        encoding="ascii"
    ).split()
    assert detached == [EXPECTED["v1_1_design"], "ablation_design_manifest.json"]
    assert "created_at" not in manifest


def test_historical_v1_remains_hash_valid_and_v1_1_binds_audited_predecessor():
    historical_path = DESIGN_V1 / "ablation_design_manifest.json"
    assert digest(historical_path) == EXPECTED["v1_design"]
    assert (DESIGN_V1 / "ablation_design_manifest.sha256").read_text(
        encoding="ascii"
    ).split() == [EXPECTED["v1_design"], "ablation_design_manifest.json"]
    manifest = design_v1_1()
    assert manifest["supersession"] == {
        "scope": "eligibility placement / candidate-admission ordering only",
        "predecessor": {
            "path": "evals/rag_real_world_corpus/v1/ablation_design_v1/ablation_design_manifest.json",
            "sha256": EXPECTED["v1_design"],
        },
        "audit_authority": {
            "path": "RAG_ELIGIBILITY_PLACEMENT_AUDIT_V1.md",
            "sha256": EXPECTED["audit"],
        },
        "unrelated_v1_fields_changed": False,
    }
    assert digest(ROOT / "RAG_ELIGIBILITY_PLACEMENT_AUDIT_V1.md") == EXPECTED["audit"]


def test_gold_corpus_baseline_and_failure_analysis_identities_are_frozen():
    baseline = (
        V1_ROOT
        / "results/dense_only_baseline_v1/20260814T052007Z-593cd2ac/raw_results.json"
    )
    assert digest(V1_ROOT / "gold/v1/gold_cases.json") == EXPECTED["gold"]
    assert digest(V1_ROOT / "gold/v1/gold_dataset_v1_freeze_manifest.json") == EXPECTED["freeze"]
    assert digest(V1_ROOT / "corpus_manifest.json") == EXPECTED["corpus"]
    assert digest(baseline) == EXPECTED["baseline_raw"]
    assert digest(FAILURE / "failure_analysis_manifest.json") == EXPECTED["failure_manifest"]
    assert digest(FAILURE / "ablation_hypotheses.json") == EXPECTED["hypotheses"]
    frozen = design_v1_1()["frozen_inputs"]
    assert frozen["gold"]["case_count"] == 72
    assert frozen["gold"]["claim_count"] == 132
    assert frozen["corpus_manifest"]["document_count"] == 11
    assert frozen["corpus_manifest"]["runtime_chunk_count"] == 442


def test_exactly_four_arms_exist_and_a_is_the_no_rerun_frozen_control():
    manifest = design_v1_1()
    assert list(manifest["arms"]) == [
        "dense_only",
        "hybrid",
        "dense_rerank",
        "hybrid_rerank",
    ]
    control = manifest["frozen_inputs"]["dense_control"]
    assert control["run_id"] == "20260814T052007Z-593cd2ac"
    assert control["raw_results_sha256"] == EXPECTED["baseline_raw"]
    assert control["reuse_without_rerun"] is True
    assert control["rerun_only_if_execution_is_proven_invalid"] is True
    assert manifest["scope_declarations"]["baseline_rerun"] is False
    assert "rerank" not in " ".join(manifest["arms"]["dense_only"]["stage_order"])


def test_a_and_c_apply_dense_admission_after_raw_top18_and_before_reranking():
    arms = design_v1_1()["arms"]
    raw = "raw_dense_top_18"
    admit = "dense_branch_admission_score_gte_0_35"
    governance = "overlap_dedup"
    for arm_name in ("dense_only", "dense_rerank"):
        stages = arms[arm_name]["stage_order"]
        assert_before(stages, raw, admit)
        assert_before(stages, admit, governance)
    c_stages = arms["dense_rerank"]["stage_order"]
    rerank = "rerank_all_dense_admitted_candidates_max_18"
    assert_before(c_stages, admit, rerank)
    assert_before(c_stages, rerank, governance)


def test_b_and_d_admit_each_branch_before_union_rrf_and_fused_top18():
    arms = design_v1_1()["arms"]
    union = "admitted_identity_union_dedup_preserving_all_observed_provenance"
    rrf = "rrf_k_60_over_admitted_branch_contributions_only"
    fused = "fused_top_18"
    for arm_name in ("hybrid", "hybrid_rerank"):
        stages = arms[arm_name]["stage_order"]
        assert_before(stages, "raw_dense_top_18", "dense_branch_admission_score_gte_0_35")
        assert_before(stages, "raw_bm25_top_18", "bm25_top_18_membership_admission")
        assert_before(stages, "dense_branch_admission_score_gte_0_35", union)
        assert_before(stages, "bm25_top_18_membership_admission", union)
        assert_before(stages, union, rrf)
        assert_before(stages, rrf, fused)
    d_stages = arms["hybrid_rerank"]["stage_order"]
    assert_before(d_stages, fused, "rerank_all_fused_candidates_max_18")
    assert_before(d_stages, "rerank_all_fused_candidates_max_18", "overlap_dedup")


def test_or_admission_preserves_observed_nonadmitting_dense_provenance():
    admission = design_v1_1()["admission_contract"]
    assert admission["selected_option"] == "B_BRANCH_ELIGIBILITY_BEFORE_FUSION"
    assert admission["candidate_rule"] == (
        "candidate_admitted = branch_admitted_dense OR branch_admitted_bm25"
    )
    assert set(admission["required_fields"]) >= {
        "branch_admitted_dense",
        "branch_admitted_bm25",
        "candidate_admitted",
        "dense_score",
        "dense_rank",
        "bm25_score",
        "bm25_rank",
        "dense_fusion_rank",
        "bm25_fusion_rank",
    }
    example = admission["dual_hit_example"]
    assert example["dense_score"] == 0.31
    assert example["dense_rank"] == 8
    assert example["bm25_rank"] == 3
    assert example["branch_admitted_dense"] is False
    assert example["branch_admitted_bm25"] is True
    assert example["candidate_admitted"] is True
    assert example["dense_fusion_rank"] is None
    assert example["bm25_fusion_rank"] == 3
    assert example["rrf_contributing_branches"] == ["bm25"]
    assert admission["observed_but_nonadmitting_rule"].startswith(
        "Observed raw score/rank provenance is retained"
    )


def test_candidate_budgets_are_maxima_with_no_padding_or_rank19_refill():
    manifest = design_v1_1()
    budget = manifest["candidate_budget"]
    assert {arm["raw_dense_limit"] for arm in manifest["arms"].values()} == {18}
    assert manifest["arms"]["hybrid"]["raw_bm25_limit"] == 18
    assert manifest["arms"]["hybrid_rerank"]["raw_bm25_limit"] == 18
    assert manifest["arms"]["hybrid"]["union_identity_limit"] == 36
    assert manifest["arms"]["hybrid_rerank"]["union_identity_limit"] == 36
    assert manifest["arms"]["hybrid"]["fused_limit"] == 18
    assert manifest["arms"]["dense_rerank"]["reranker_input_limit"] == 18
    assert manifest["arms"]["hybrid_rerank"]["reranker_input_limit"] == 18
    assert all(arm["no_padding_or_refill"] for arm in manifest["arms"].values())
    assert budget["limit_is_maximum_not_padding_requirement"] is True
    assert budget["dense_rank_greater_than_18_refill_forbidden"] is True
    assert "reranks 12" in budget["underfill_example"]
    assert "ranks 19+" in budget["underfill_example"]


def test_fused_top18_contains_only_admitted_identities_and_rrf_is_ordering_only():
    manifest = design_v1_1()
    rrf = manifest["rrf_contract"]
    assert "Only candidate_admitted identities" in rrf["input"]
    assert "branch_admitted flag is true" in rrf["input"]
    assert rrf["rrf_constant"] == 60
    assert rrf["rank_start"] == 1
    assert rrf["branch_weights"] == {"dense": 1.0, "bm25": 1.0}
    assert rrf["missing_or_nonadmitting_branch_contribution"] == 0.0
    assert rrf["limit_after_fusion"] == 18
    assert rrf["raw_scores_are_telemetry_only"] is True
    assert rrf["tie_break_order"] == [
        "best admitted branch fusion rank ascending",
        "dense_fusion_rank ascending with null last",
        "bm25_fusion_rank ascending with null last",
        "stable_chunk_id ascending",
    ]
    scores = manifest["score_contract"]
    assert scores["fusion_score"] == "Ordering only."
    assert scores["reranker_score"].startswith("Raw relevance logit; ordering only")
    assert scores["normalization_or_calibration_introduced"] is False
    assert len(scores["forbidden_comparisons"]) == 4


def test_reranker_model_revision_input_limit_score_and_placement_are_frozen():
    reranker = design_v1_1()["reranker_contract"]
    assert reranker["model_id"] == "BAAI/bge-reranker-v2-m3"
    assert reranker["revision"] == "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
    assert reranker["input_pair"] == ["effective retrieval query", "raw chunk text"]
    assert reranker["maximum_pair_count"] == 18
    assert reranker["pair_token_cap"] == 1024
    assert reranker["truncation"].startswith("Preserve the query")
    assert reranker["score"] == "raw single-logit relevance score"
    assert reranker["normalization"] is None
    assert reranker["threshold"] is None
    assert reranker["use"] == "ordering only"
    assert reranker["automatic_backup_fallback"] is False
    assert reranker["changes_eligibility"] is False
    assert reranker["placement_dense_rerank"].startswith("after Dense admission")
    assert reranker["placement_hybrid_rerank"].startswith("after branch admission")


def test_governance_generation_citation_answerability_and_v1_parameters_are_unchanged():
    old = design_v1()
    new = design_v1_1()
    frozen = new["unchanged_v1_contract"]
    old_bm25 = old["hybrid"]["bm25_branch"]
    assert (frozen["bm25"]["k1"], frozen["bm25"]["b"], frozen["bm25"]["epsilon"]) == (
        old_bm25["parameters"]["k1"],
        old_bm25["parameters"]["b"],
        old_bm25["parameters"]["epsilon"],
    )
    for key, value in frozen["bm25"]["bilingual_analyzer"].items():
        assert old_bm25["tokenizer_contract"][key] == value
    assert frozen["rrf"] == {
        "constant": old["hybrid"]["fusion"]["rrf_constant"],
        "branch_weights": old["hybrid"]["fusion"]["branch_weights"],
    }
    old_reranker = old["reranker"]
    assert frozen["reranker"]["model_id"] == old_reranker["preferred_model"]["model_id"]
    assert frozen["reranker"]["revision"] == old_reranker["preferred_model"]["revision"]
    assert frozen["reranker"]["pair_token_cap"] == old_reranker["input_contract"][
        "preferred_model_pair_token_limit"
    ]
    assert frozen["generation"] == old["shared"]["generation"]
    assert frozen["citation"] == old["shared"]["citation"]
    governance = new["governance_contract"]
    old_governance = old["shared"]["evidence_governance"]
    assert governance["frozen_unchanged"] is True
    assert governance["admission_is_part_of_governance"] is False
    assert governance["max_sources"] == old_governance["max_sources"] == 6
    assert governance["final_top_k"] == old_governance["final_top_k"] == 6
    assert governance["max_chunk_chars"] == old_governance["max_chunk_chars"] == 2200
    assert governance["context_budget_chars"] == old_governance["context_budget_chars"] == 12000
    assert frozen["governance"]["diversity_first_pass_max_per_material"] == 3
    assert frozen["answerability"]["frozen_across_arms"] is True


def test_metrics_regression_latency_and_production_decision_rule_remain_v1():
    old = design_v1()
    frozen = design_v1_1()["unchanged_v1_contract"]
    metric = frozen["metrics_and_regression_guard"]
    assert metric["hybrid_primary"] == old["metrics"]["retrieval_primary"]["name"]
    assert metric["reranker_primary"] == old["metrics"]["reranker_primary"]["name"]
    assert metric["regression_transitions"] == old["metrics"]["regression_transitions"]
    assert metric["semantic_review_required"] == old["metrics"]["semantic_review_required"]
    assert metric["overall_accuracy_as_sole_decision_metric_forbidden"] is True
    latency = frozen["latency_reporting"]
    assert latency["required_per_arm_stages"] == old["latency"]["required_per_arm_stages"]
    assert latency["required_aggregates"] == old["latency"]["required_aggregates"]
    assert latency["timeout_and_error_counts_required"] is True
    rule = frozen["production_decision_rule"]
    old_rule = old["production_decision_rule"]
    assert rule["rule_id"] == old_rule["rule_id"]
    assert rule["automatic_best_overall_score_selection_forbidden"] is True
    assert rule["numeric_latency_gate"] is old_rule["numeric_latency_gate"] is None
    assert rule["hybrid_rerank_complementarity_required"] is True
    assert rule["automatic_deployment_authorized"] is False


def test_target_sets_exactly_match_frozen_failure_analysis_and_v1():
    new_sets = design_v1_1()["target_case_sets"]
    old_sets = design_v1()["target_case_sets"]
    source = load(FAILURE / "ablation_hypotheses.json")["arms"]
    for arm in ("dense_only", "hybrid", "dense_rerank", "hybrid_rerank"):
        assert new_sets[arm] == old_sets[arm] == source[arm]["target_case_ids"]
    assert new_sets["reranker_ranking_miss"] == old_sets["reranker_ranking_miss"]
    assert new_sets["reranker_diversity_miss"] == old_sets["reranker_diversity_miss"]
    assert new_sets["hybrid_rerank_requires_both"] == old_sets[
        "hybrid_rerank_requires_both"
    ] == []
    assert len(new_sets["hybrid"]) == 9
    assert len(new_sets["dense_rerank"]) == 10
    assert len(new_sets["reranker_ranking_miss"]) == 2
    assert len(new_sets["reranker_diversity_miss"]) == 8


def test_production_files_match_binding_and_experiment_only_seam_is_declared():
    failure_manifest = load(FAILURE / "failure_analysis_manifest.json")
    historical = failure_manifest["frozen_bindings"]["production_code"]
    binding = load(POST_C_PRODUCTION)
    assert historical["all_match"] is True
    assert binding["strict_equality_required"] is True
    assert binding["hash_algorithm"] == "SHA-256"
    assert binding["file_count"] == len(binding["baseline_sha256"]) == 15
    assert set(binding["baseline_sha256"]) == set(historical["baseline_sha256"])
    for relative_path, expected_hash in binding["baseline_sha256"].items():
        assert digest(ROOT / relative_path) == expected_hash
    seam = design_v1_1()["production_seam_contract"]
    assert seam["result"] == "PRODUCTION_SEAM_WITHOUT_BOUND_FILE_CHANGE=YES"
    assert "retrieve_sources" in seam["seam"]
    assert seam["phase_1_expected_adapter"].startswith("Experiment-only adapter/composition")
    assert seam["bound_production_file_change_required_to_execute_ablation"] is False
    assert seam["production_refactor_in_v1_1"] is False
    assert seam["implemented_in_this_round"] is False


def test_design_only_declarations_forbid_all_runtime_or_production_work():
    declarations = design_v1_1()["scope_declarations"]
    assert declarations == {
        "design_only": True,
        "hybrid_implemented": False,
        "reranker_implemented": False,
        "experimental_llm_calls": 0,
        "model_downloads": 0,
        "reranker_instantiations": 0,
        "reranker_inference_calls": 0,
        "embedding_executions": 0,
        "faiss_experimental_executions": 0,
        "bm25_executions": 0,
        "baseline_rerun": False,
        "production_rag_modified": False,
        "gold_modified": False,
        "corpus_modified": False,
        "parameter_tuning_performed": False,
    }
    implementation = design_v1_1()["implementation_binding"]
    assert implementation["phase_1_status"] == "NOT_STARTED"
    assert implementation["predecessor_hash_must_not_be_used_for_v1_1_implementation"] is True
    assert implementation["direct_implementation_to_216_llm_calls_forbidden"] is True


def test_report_has_all_13_sections_hashes_and_exact_completion_suffix():
    report = (ROOT / "RAG_HYBRID_RERANK_ABLATION_DESIGN_V1_1.md").read_text(
        encoding="utf-8"
    )
    section_titles = [
        "V1.1 design status",
        "Reason for revision",
        "Exact canonical A/B/C/D ordering",
        "Candidate-budget semantics",
        "Multi-branch admission and provenance",
        "Unchanged V1 fields",
        "V1 predecessor and audit binding",
        "New V1.1 detached SHA-256",
        "Files created or modified",
        "V1 historical hash verification",
        "Production binding verification",
        "Contract-test result",
        "External/model/retrieval execution counts",
    ]
    for index, title in enumerate(section_titles, start=1):
        assert f"## {index}. {title}" in report
    assert EXPECTED["v1_design"] in report
    assert EXPECTED["v1_1_design"] in report
    assert "PRODUCTION_SEAM_WITHOUT_BOUND_FILE_CHANGE=YES" in report
    assert report.rstrip().endswith(
        "RAG_HYBRID_RERANK_ABLATION_DESIGN_V1_1 = COMPLETE\n"
        "READY_FOR_HYBRID_RERANK_IMPLEMENTATION = YES"
    )
