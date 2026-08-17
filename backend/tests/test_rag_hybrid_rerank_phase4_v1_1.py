from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "evals/rag_real_world_corpus/v1"
RUN = V1 / "results/hybrid_rerank_phase4_v1_1/20260814T131417Z-04dfc031"
REPORT = ROOT / "RAG_HYBRID_RERANK_PHASE4_SEMANTIC_REVIEW_V1_1.md"
PASS1_SHA = "0e91fedd1a4b98152e77a093dff1a18ed3f177a92b3d1d4ddc67073b3fcdaf9c"


def read(name: str):
    return json.loads((RUN / name).read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_integrity_gate_passed_without_new_execution():
    preflight = read("integrity_preflight.json")
    assert preflight["status"] == "PASS"
    assert preflight["bundle_validation"] == {
        "case_count": 72,
        "arm_outputs_per_case": 4,
        "frozen_output_count": 288,
        "frozen_claim_count": 132,
        "phase3_record_count": 216,
        "phase3_context_count": 216,
        "answer_text_unchanged": True,
        "citation_lists_unchanged": True,
        "context_digests_unchanged": True,
        "omitted_cases": [],
        "duplicate_cases": [],
    }
    for key in ("new_deepseek_calls", "new_generation_calls", "new_retrieval_runs", "new_reranker_runs", "arm_a_reruns", "production_modifications"):
        assert preflight[key] == 0


def test_blinded_input_contains_no_architecture_identity():
    blinded = read("blinded_review_input.json")
    assert blinded["case_count"] == 72
    assert blinded["response_count"] == 288
    for case in blinded["cases"]:
        assert "arm" not in case
        for response in case["responses"]:
            assert "arm" not in response
            assert "architecture" not in response
            assert response["response_label"] in {"response_X1", "response_X2", "response_X3", "response_X4"}


def test_sealed_mapping_is_a_per_case_permutation():
    mapping = read("sealed_blind_mapping.json")
    assert mapping["mapping_count"] == 72
    for case in mapping["mappings"]:
        assert set(case["response_to_arm"]) == {"response_X1", "response_X2", "response_X3", "response_X4"}
        assert set(case["response_to_arm"].values()) == {"A", "B", "C", "D"}


def test_pass1_was_frozen_before_unblinding():
    freeze = read("pass1_freeze.json")
    assert freeze["frozen_before_unblinding"] is True
    assert freeze["mapping_read_before_freeze"] is False
    assert freeze["blinded_review_sha256"] == PASS1_SHA
    assert digest(RUN / "blinded_adjudication.json") == PASS1_SHA
    assert (RUN / "blinded_adjudication.sha256").read_text(encoding="utf-8").split()[0] == PASS1_SHA


def test_blinded_review_is_complete_and_unique():
    claims = read("blinded_claim_reviews.json")
    verdicts = read("blinded_case_verdicts.json")
    assert claims["claim_review_count"] == 528
    assert claims["unique_frozen_claim_count"] == 132
    assert len({(row["case_id"], row["response_label"], row["claim_id"]) for row in claims["rows"]}) == 528
    assert verdicts["verdict_count"] == 288
    assert len({(row["case_id"], row["response_label"]) for row in verdicts["rows"]}) == 288
    assert not any(row["review_uncertain"] for row in claims["rows"])


def test_unblinded_metrics_have_132_claims_and_72_cases_per_arm():
    metrics = read("unblinded_metrics.json")
    assert metrics["post_unblind_review_corrections"] == []
    for arm in "ABCD":
        assert metrics["arms"][arm]["frozen_claim_count"] == 132
        assert metrics["arms"][arm]["case_count"] == 72


def test_transitions_are_exact_partitions():
    transitions = read("case_transitions.json")
    expected = {
        "B": {"FIXED_FAILURE": 2, "UNCHANGED_FAILURE": 20, "NEW_REGRESSION": 3, "UNCHANGED_PASS": 47},
        "C": {"FIXED_FAILURE": 5, "UNCHANGED_FAILURE": 17, "NEW_REGRESSION": 2, "UNCHANGED_PASS": 48},
        "D": {"FIXED_FAILURE": 4, "UNCHANGED_FAILURE": 18, "NEW_REGRESSION": 2, "UNCHANGED_PASS": 48},
    }
    for arm, counts in expected.items():
        assert transitions["summary"][arm]["counts"] == counts
        assert sum(counts.values()) == 72
        ids = [case_id for values in transitions["summary"][arm]["case_ids"].values() for case_id in values]
        assert len(ids) == len(set(ids)) == 72


def test_target_metrics_reproduce_frozen_phase2_diagnostics():
    target = read("target_group_analysis.json")
    assert target["phase2_diagnostics_reproduction"]["status"] == "PASS"
    assert target["phase2_diagnostics_reproduction"]["observed"] == {
        "B_document": 8,
        "B_anchor": 3,
        "C_document": 10,
        "C_anchor": 5,
        "D_document": 10,
        "D_anchor": 3,
    }
    assert target["hybrid_primary_metric"]["recovered_case_ids"] == ["rw-gold-v1-single-dependency-defaults"]


def test_reranker_split_remains_two_and_eight():
    target = read("target_group_analysis.json")
    for arm in ("C", "D"):
        assert target["reranker_primary_metric"][arm]["SELECTION_RANKING_MISS"]["case_count"] == 2
        assert target["reranker_primary_metric"][arm]["SELECTION_DIVERSITY_MISS"]["case_count"] == 8


def test_d_complementarity_fails_with_no_unique_fix():
    complementarity = read("complementarity.json")
    assert complementarity["d_unique_target_fixes"] == []
    assert complementarity["d_complementarity_gate"] == "FAIL"


def test_all_33_regression_guard_cases_were_inspected():
    severe = read("severe_regressions.json")
    assert severe["frozen_no_failure_case_count"] == 33
    assert severe["inspected_pair_count"] == 99
    assert severe["arms"]["B"]["case_ids"] == ["rw-gold-v1-single-ragas-dataset"]
    assert severe["arms"]["C"]["case_ids"] == []
    assert severe["arms"]["D"]["case_ids"] == []


def test_causal_trace_covers_every_fixed_and_regressed_pair():
    causal = read("causal_traces.json")
    assert causal["changed_case_arm_count"] == 18
    assert sum(causal["dominant_cause_distribution"].values()) == 18
    for row in causal["rows"]:
        assert row["transition"] in {"FIXED_FAILURE", "NEW_REGRESSION"}
        assert row["human_readable_note"]
        assert row["candidate_retrieval"] and row["selected_context"] and row["generation_output"] is not None


def test_production_gates_recommend_keep_a():
    gates = read("production_gate_matrix.json")
    assert gates["recommendation"] == "KEEP_A"
    assert gates["eligible_arms_before_pareto"] == []
    assert gates["pareto_frontier"] == []
    assert all(row["gate_1_validity"]["pass"] for row in gates["arms"])
    assert all(row["gate_2_own_primary_target"]["pass"] for row in gates["arms"])
    assert not any(row["gate_3_hard_regression"]["pass"] for row in gates["arms"])


def test_recommendation_evidence_records_zero_new_execution():
    recommendation = read("final_recommendation_evidence.json")
    assert recommendation["recommendation"] == "KEEP_A"
    for key in ("new_deepseek_calls", "new_generation_calls", "new_retrieval_runs", "new_reranker_runs", "arm_a_reruns", "production_modifications"):
        assert recommendation[key] == 0


def test_final_report_has_22_sections_and_exact_ending():
    report = REPORT.read_text(encoding="utf-8")
    assert sum(line.startswith("## ") for line in report.splitlines()) == 22
    assert report.endswith(
        "RAG_HYBRID_RERANK_PHASE4_V1_1 = PASS\n"
        "READY_FOR_PRODUCTION_DECISION = YES\n"
    )
