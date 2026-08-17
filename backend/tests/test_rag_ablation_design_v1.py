from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "evals/rag_real_world_corpus/v1"
DESIGN = V1 / "ablation_design_v1"
FAILURE = V1 / "failure_analysis_v1"
POST_C_PRODUCTION = V1 / "post_c_production_integrity_v1.json"
GOLD_HELPERS = V1 / "gold/v1"
if str(GOLD_HELPERS) not in sys.path:
    sys.path.insert(0, str(GOLD_HELPERS))

from gold_common import json_schema_errors  # noqa: E402


EXPECTED = {
    "gold": "33a0b69901fa47e3fe45be0277228cd4a5519fe780fe5b9d2c52b1bfe614927a",
    "freeze": "d979079be4eb901a825ab29414dd7b5124d030182e09b55eea1e93749c12a5c2",
    "corpus": "6f67d510cd35197f107400d33033972c0c3c84478174e4991e491f6c8e4ab563",
    "baseline_raw": "bf718aed08e226149c9310cbf20bf25c403708217e2908789120178ac5574e28",
    "failure_manifest": "e869fd73e2570413595c1af194b6ec6876e8b822fbd4eac279541a03cac27fb8",
    "hypotheses": "27184ff8ddbf628f78767ede545e202ee66cb9ff17f56728961a8ce2d801f610",
    "matrix": "877d2ba3948e5bdcf530307b4719cd46df74ae5c4680547fab7fa09374f31726",
    "case_analysis": "406527bcb6b7efeea885175bb9ea5f99af1b3bf91ccc0c79711d88854bc57b1e",
    "schema": "73c4dff4082d85f3aec383a59e4e18eaeff8eb65f467e8dcbd587085a054e626",
    "design": "4c3b2e294b63dcc0ae57be1d30d713b3cf1ffed5b0f3a989499f1298902703c6",
}


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def design():
    return load(DESIGN / "ablation_design_manifest.json")


def test_design_manifest_is_schema_valid_complete_and_detached_hash_bound():
    manifest = design()
    schema_path = DESIGN / "ablation_design_manifest.schema.json"
    schema = load(schema_path)
    assert json_schema_errors(manifest, schema) == []
    assert digest(schema_path) == EXPECTED["schema"]
    assert manifest["status"] == "COMPLETE"
    assert manifest["ready_for_hybrid_rerank_implementation"] is True
    assert digest(DESIGN / "ablation_design_manifest.json") == EXPECTED["design"]
    detached = (DESIGN / "ablation_design_manifest.sha256").read_text(
        encoding="ascii"
    ).split()
    assert detached == [EXPECTED["design"], "ablation_design_manifest.json"]
    assert "created_at" not in manifest


def test_all_frozen_input_hashes_are_exact_and_unchanged():
    baseline = (
        V1
        / "results/dense_only_baseline_v1/20260814T052007Z-593cd2ac/raw_results.json"
    )
    assert digest(V1 / "gold/v1/gold_cases.json") == EXPECTED["gold"]
    assert digest(V1 / "gold/v1/gold_dataset_v1_freeze_manifest.json") == EXPECTED["freeze"]
    assert digest(V1 / "corpus_manifest.json") == EXPECTED["corpus"]
    assert digest(baseline) == EXPECTED["baseline_raw"]
    assert digest(FAILURE / "failure_analysis_manifest.json") == EXPECTED["failure_manifest"]
    assert digest(FAILURE / "ablation_hypotheses.json") == EXPECTED["hypotheses"]
    assert digest(FAILURE / "optimization_addressability_matrix.json") == EXPECTED["matrix"]
    assert digest(FAILURE / "case_failure_analysis.json") == EXPECTED["case_analysis"]


def test_exactly_four_arms_are_defined_with_only_the_registered_interventions():
    arms = design()["arms"]
    assert list(arms) == ["dense_only", "hybrid", "dense_rerank", "hybrid_rerank"]
    assert arms["dense_only"]["allowed_changes"] == []
    assert arms["hybrid"]["allowed_changes"] == ["candidate retrieval", "fusion"]
    assert arms["dense_rerank"]["allowed_changes"] == ["reranker ordering"]
    assert arms["hybrid_rerank"]["allowed_changes"] == [
        "candidate retrieval",
        "fusion",
        "reranker ordering",
    ]
    assert arms["dense_only"]["fusion"] is None
    assert arms["dense_only"]["reranker"] is None
    assert arms["hybrid"]["fusion"] == "rrf_k_60"
    assert arms["hybrid"]["reranker"] is None
    assert arms["dense_rerank"]["fusion"] is None
    assert arms["dense_rerank"]["reranker"] == "preferred_frozen_reranker"
    assert arms["hybrid_rerank"]["fusion"] == "rrf_k_60"
    assert arms["hybrid_rerank"]["reranker"] == "preferred_frozen_reranker"


def test_dense_control_references_the_frozen_run_and_cannot_be_rerun_normally():
    control = design()["frozen_inputs"]["dense_control"]
    assert control["run_id"] == "20260814T052007Z-593cd2ac"
    assert control["raw_results_sha256"] == EXPECTED["baseline_raw"]
    assert control["reuse_without_rerun"] is True
    assert control["rerun_only_if_execution_is_proven_invalid"] is True
    assert design()["scope_declarations"]["baseline_rerun"] is False


def test_candidate_pool_is_at_most_18_before_governance_for_every_arm():
    manifest = design()
    assert manifest["candidate_budget"]["final_ablation_candidate_pool"] == 18
    assert {arm["candidate_pool_limit"] for arm in manifest["arms"].values()} == {18}
    assert manifest["candidate_budget"]["hybrid"] == {
        "dense_branch_limit": 18,
        "bm25_branch_limit": 18,
        "maximum_union_before_identity_dedup": 36,
        "fused_pre_governance_limit": 18,
    }
    assert manifest["candidate_budget"]["hybrid_rerank"]["reranker_input_limit"] == 18
    assert manifest["candidate_budget"]["forbidden_depths_in_v1"] == [50, 100, 200]


def test_hybrid_uses_same_442_chunks_fixed_rrf_and_no_score_calibration():
    manifest = design()
    hybrid = manifest["hybrid"]
    assert manifest["candidate_identity"]["lexical_unit"].startswith("Exactly the same 442")
    assert manifest["candidate_identity"]["whole_document_bm25_forbidden"] is True
    assert hybrid["fusion"]["method"] == "Reciprocal Rank Fusion"
    assert hybrid["fusion"]["rrf_constant"] == 60
    assert hybrid["fusion"]["branch_weights"] == {"dense": 1.0, "bm25": 1.0}
    assert hybrid["fusion"]["score_calibration"] is False
    assert hybrid["fusion"]["tuning_in_v1"] is False
    assert hybrid["bm25_branch"]["parameters"] == {
        "k1": 1.5,
        "b": 0.75,
        "epsilon": 0.25,
        "parameter_source": "rank_bm25 BM25Okapi published defaults",
        "tuning_in_v1": False,
    }


def test_threshold_contract_never_mixes_dense_bm25_rrf_or_reranker_scores():
    manifest = design()
    contract = manifest["hybrid"]["threshold_contract"]
    assert contract["selected_option"] == "A_BRANCH_TYPED_ELIGIBILITY_GATE"
    assert contract["no_cross_space_comparisons"] is True
    assert manifest["arms"]["dense_only"]["eligibility_gate"] == "dense_score >= 0.35"
    assert manifest["arms"]["dense_rerank"]["eligibility_gate"] == "dense_score >= 0.35"
    hybrid_gate = "dense_score >= 0.35 OR bm25_rank IS NOT NULL"
    assert manifest["arms"]["hybrid"]["eligibility_gate"] == hybrid_gate
    assert manifest["arms"]["hybrid_rerank"]["eligibility_gate"] == hybrid_gate
    reranker_score = manifest["reranker"]["score_contract"]
    assert reranker_score["normalization"] is None
    assert reranker_score["threshold"] is None
    assert reranker_score["use"] == "ordering only"
    assert reranker_score["never_compare_to_dense_or_bm25_or_rrf_scores"] is True


def test_target_case_sets_exactly_match_frozen_failure_analysis_hypotheses():
    manifest_sets = design()["target_case_sets"]
    source_sets = load(FAILURE / "ablation_hypotheses.json")["arms"]
    assert manifest_sets["dense_only"] == source_sets["dense_only"]["target_case_ids"]
    assert manifest_sets["hybrid"] == source_sets["hybrid"]["target_case_ids"]
    assert manifest_sets["dense_rerank"] == source_sets["dense_rerank"]["target_case_ids"]
    assert manifest_sets["hybrid_rerank"] == source_sets["hybrid_rerank"]["target_case_ids"]
    assert manifest_sets["hybrid_rerank_requires_both"] == []
    assert len(manifest_sets["hybrid"]) == 9
    assert len(manifest_sets["dense_rerank"]) == 10
    assert len(manifest_sets["reranker_ranking_miss"]) == 2
    assert len(manifest_sets["reranker_diversity_miss"]) == 8
    assert set(manifest_sets["reranker_ranking_miss"]) | set(
        manifest_sets["reranker_diversity_miss"]
    ) == set(manifest_sets["dense_rerank"])


def test_query_rewrite_governance_generation_and_citation_are_shared_by_all_arms():
    manifest = design()
    assert {arm["shared_contract_ref"] for arm in manifest["arms"].values()} == {"#/shared"}
    shared = manifest["shared"]
    assert shared["query_rewrite"]["enabled"] is True
    assert shared["query_rewrite"]["prompt_version"] == "rag-rewrite-v1"
    governance = shared["evidence_governance"]
    assert governance["document_diversity"].startswith("Current two-pass policy")
    assert governance["diversity_change_allowed"] is False
    assert governance["max_sources"] == governance["final_top_k"] == 6
    assert governance["max_chunk_chars"] == 2200
    assert governance["context_budget_chars"] == 12000
    generation = shared["generation"]
    assert generation == {
        "provider": "openai_compatible",
        "model": "deepseek-v4-flash",
        "structured_model": "deepseek-v4-flash",
        "temperature": 0.1,
        "reasoning_enabled": False,
        "structured_output_token_limit": 2400,
        "timeout_seconds": 60,
        "max_retries": 2,
        "prompt_version": "rag-answer-v2-evidence-binding",
        "grounding_repair_limit": 1,
        "frozen_across_arms": True,
    }
    assert shared["citation"]["frozen_across_arms"] is True


def test_reranker_model_input_revision_and_placement_are_frozen():
    reranker = design()["reranker"]
    assert reranker["candidate_limit"] == 18
    assert reranker["input_contract"]["pair"] == ["effective retrieval query", "raw chunk text"]
    assert reranker["input_contract"]["document_title_included"] is False
    assert reranker["input_contract"]["section_title_included"] is False
    assert reranker["input_contract"]["metadata_included"] is False
    assert reranker["preferred_model"]["model_id"] == "BAAI/bge-reranker-v2-m3"
    assert reranker["preferred_model"]["revision"] == (
        "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
    )
    assert reranker["preferred_model"]["license"] == "Apache-2.0"
    assert reranker["backup_model"]["revision"] == (
        "1427fd652930e4ba29e8149678df786c240d8825"
    )
    assert reranker["model_switch_rule"].startswith("The backup is documentation only")
    assert reranker["downloaded_in_this_round"] is False
    assert reranker["executed_in_this_round"] is False
    assert reranker["diversity_policy_change_allowed"] is False


def test_score_provenance_requires_nulls_and_final_rejection_reason():
    provenance = design()["score_provenance"]
    assert list(provenance["required_fields"]) == [
        "dense_score",
        "dense_rank",
        "bm25_score",
        "bm25_rank",
        "fusion_score",
        "fusion_rank",
        "reranker_score",
        "reranker_rank",
        "final_selection_status",
        "selection_rejection_reason",
    ]
    assert provenance["null_rule"].startswith("A score or rank absent")
    assert "DIVERSITY_DEFERRED_NOT_BACKFILLED" in provenance["rejection_reason_enum"]
    assert "reranker_input_truncated" in provenance["additional_telemetry"]


def test_production_code_still_matches_the_frozen_dense_baseline_binding():
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


def test_design_only_declarations_and_staged_execution_are_frozen():
    manifest = design()
    declarations = manifest["scope_declarations"]
    assert declarations == {
        "design_only": True,
        "hybrid_implemented": False,
        "reranker_implemented": False,
        "experimental_llm_calls": 0,
        "embedding_executions": 0,
        "faiss_retrieval_executions": 0,
        "baseline_rerun": False,
        "production_rag_modified": False,
        "gold_modified": False,
        "corpus_modified": False,
        "parameter_tuning_performed": False,
    }
    isolation = manifest["execution_isolation"]
    assert isolation["maximum_new_generation_requests"] == 216
    assert isolation["request_calculation"] == "72 cases x 3 experimental arms"
    staging = manifest["implementation_staging"]
    assert staging["phase_order_mandatory"] is True
    assert staging["direct_implementation_to_216_llm_calls_forbidden"] is True


def test_production_gate_prefers_minimal_architecture_and_requires_complementarity_for_d():
    rule = design()["production_decision_rule"]
    assert rule["automatic_best_overall_score_selection_forbidden"] is True
    assert len(rule["hard_reject_conditions"]) >= 6
    assert rule["minimal_complexity_rules"]["hybrid_rerank"].startswith(
        "D may advance over B or C only if it fixes at least one target case"
    )
    assert rule["numeric_latency_gate"] is None
    assert "research-effective" not in rule["research_effective_but_not_production_worthy"]
    assert rule["final_authority"].endswith("never authorizes automatic deployment.")


def test_report_contains_all_required_sections_and_frozen_design_hash():
    report = (ROOT / "RAG_HYBRID_RERANK_ABLATION_DESIGN_V1.md").read_text(
        encoding="utf-8"
    )
    for number, title in enumerate(
        [
            "Design status",
            "Frozen inputs",
            "Current dense-only architecture",
            "Target architecture",
            "Four arms",
            "Hybrid design",
            "Fusion design",
            "Threshold/score contract",
            "Reranker design",
            "Reranker placement",
            "Diversity confound handling",
            "Candidate budget",
            "Frozen target case sets",
            "Metrics",
            "Latency metrics",
            "Regression metrics",
            "Production decision rule",
            "Implementation staging",
            "Tests",
            "Files created",
        ],
        start=1,
    ):
        assert f"## {number}. {title}" in report
    assert EXPECTED["design"] in report
    assert "HYBRID_IMPLEMENTED = NO" in report
    assert "RERANKER_IMPLEMENTED = NO" in report
    assert "EXPERIMENTAL_LLM_CALLS = 0" in report
    assert "PRODUCTION_RAG_MODIFIED = NO" in report
