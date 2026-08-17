from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "evals" / "rag_real_world_corpus" / "v1" / "gold" / "v1"
CORPUS = ROOT / "evals" / "rag_real_world_corpus" / "v1"
if str(GOLD) not in sys.path:
    sys.path.insert(0, str(GOLD))

from gold_common import json_schema_errors  # noqa: E402


GOLD_SHA256 = "33a0b69901fa47e3fe45be0277228cd4a5519fe780fe5b9d2c52b1bfe614927a"
FREEZE_SHA256 = "d979079be4eb901a825ab29414dd7b5124d030182e09b55eea1e93749c12a5c2"
FROZEN_REVIEW_SHA256 = "89bf00e924579c1c68a88a952797d4bfb73bccab0f7ba8ffe28bb74e5888279d"
CORPUS_MANIFEST_SHA256 = "6f67d510cd35197f107400d33033972c0c3c84478174e4991e491f6c8e4ab563"


def load(name: str):
    return json.loads((GOLD / name).read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def freeze():
    return load("gold_dataset_v1_freeze_manifest.json")


def test_canonical_gold_and_detached_freeze_hash_are_exact():
    assert digest(GOLD / "gold_cases.json") == GOLD_SHA256
    assert digest(GOLD / "gold_dataset_v1_freeze_manifest.json") == FREEZE_SHA256
    recorded = (GOLD / "gold_dataset_v1_freeze_manifest.sha256").read_text(encoding="utf-8").split()
    assert recorded == [FREEZE_SHA256, "gold_dataset_v1_freeze_manifest.json"]


def test_freeze_manifest_is_schema_valid_and_frozen():
    artifact = freeze()
    schema = load("gold_dataset_v1_freeze_manifest.schema.json")
    assert json_schema_errors(artifact, schema) == []
    assert artifact["dataset_id"] == "learnpilot-rag-real-world-gold-v1"
    assert artifact["status"] == "FROZEN"
    assert artifact["freeze_protocol"] == ["VERIFY", "FREEZE", "BIND", "REPORT"]
    assert artifact["freeze_policy"]["silent_v1_mutation_forbidden"] is True
    assert artifact["freeze_policy"]["ready_for_dense_only_baseline"] is True


def test_case_claim_anchor_counts_and_unique_id_contract_are_frozen():
    artifact = freeze()
    assert artifact["gold"]["case_count"] == artifact["gold"]["case_id_unique_count"] == 72
    assert artifact["gold"]["claim_count"] == artifact["gold"]["claim_id_unique_count"] == 132
    assert artifact["gold"]["information_need_key_unique_count"] == 72
    assert artifact["gold"]["core_case_count"] == 60
    assert artifact["gold"]["stress_case_count"] == 12
    assert artifact["evidence_anchor_audit"]["anchor_count"] == 89
    assert artifact["gold"]["semantic_payload_changes_during_final_freeze"] == 0


def test_semantic_closure_is_96_unchanged_plus_8_repaired_supported():
    closure = freeze()["semantic_closure"]
    assert closure == {
        "semantic_review_claims": 104,
        "supported": 104,
        "partially_supported": 0,
        "unsupported": 0,
        "ambiguous": 0,
        "previously_supported_unchanged": 96,
        "repaired_fresh_reviewed_supported": 8,
    }


def test_pre_repair_review_repair_closure_and_unaffected_proof_are_bound():
    artifact = freeze()
    bindings = artifact["artifact_bindings"]
    assert bindings["pre_repair_semantic_review"]["sha256"] == FROZEN_REVIEW_SHA256
    assert digest(ROOT / bindings["pre_repair_semantic_review"]["path"]) == FROZEN_REVIEW_SHA256
    assert artifact["repair_closure"]["defects"] == 9
    assert artifact["repair_closure"]["affected_cases"] == 8
    assert artifact["repair_closure"]["status"] == "COMPLETE"
    assert artifact["unaffected_preservation"] == {
        "case_count": 64,
        "semantic_payload_unchanged": 64,
        "status": "PASS",
    }


def test_all_anchors_resolve_and_have_no_runtime_id_leakage():
    audit = freeze()["evidence_anchor_audit"]
    assert audit["locator_kind_distribution"] == {"PDF_PAGE": 24, "SOURCE_LINES": 65}
    assert audit["document_resolution_pass"] == 89
    assert audit["locator_resolution_pass"] == 89
    assert audit["anchor_hash_pass"] == 89
    assert audit["runtime_id_leakage"] == 0


def test_contract_modes_roles_and_answerability_are_frozen():
    artifact = freeze()
    contract = artifact["contract_compatibility"]
    assert contract["evidence_roles"] == ["REQUIRED", "ACCEPTABLE_SUPPORT", "UNSUPPORTED"]
    assert contract["or_inside_evidence_group"] is True
    assert contract["and_across_evidence_groups"] is True
    assert contract["controlled_v2_helper_compatibility"] == "PASS"
    assert contract["evaluation_mode_distribution"] == {
        "ANSWERABILITY_ONLY": 10,
        "IDENTIFIER_EXACT": 5,
        "NUMERIC_EXACT": 7,
        "SEMANTIC_REVIEW": 104,
        "STRUCTURED_EXACT": 6,
    }
    assert artifact["answerability_audit"] == {
        "unanswerable_near_boundary_count": 10,
        "valid_count": 10,
        "violation_count": 0,
    }
    assert artifact["evidence_role_audit"] == {
        "acceptable_support_count": 11,
        "unsupported_count": 25,
        "target_case_count": 14,
        "misclassified_count": 0,
    }


def test_required_document_invariants_match_repaired_canonical_gold():
    invariants = freeze()["required_document_invariants"]
    assert invariants["participation_left"] == invariants["participation_right"] == 86
    assert invariants["match"] is True
    assert invariants["candidate_required_document_count_distribution"] == {"0": 10, "1": 41, "2": 18, "3": 3}
    assert invariants["minimum_hitting_set_distribution"] == {"0": 10, "1": 41, "2": 18, "3": 3}
    assert invariants["candidate_multi_document_case_count"] == 21


def test_corpus_and_evaluation_manifest_bindings_are_exact():
    artifact = freeze()
    corpus = artifact["corpus"]
    assert corpus["dataset_id"] == "learnpilot-rag-real-world-corpus@v1"
    assert corpus["manifest_sha256"] == corpus["identity_sha256"] == CORPUS_MANIFEST_SHA256
    assert digest(CORPUS / "corpus_manifest.json") == CORPUS_MANIFEST_SHA256
    assert corpus["document_count"] == corpus["source_document_hash_pass_count"] == 11
    assert corpus["projected_chunk_count"] == corpus["installed_chunk_count"] == 442
    assert all(item["match"] and item["expected_sha256"] == item["actual_sha256"] for item in corpus["document_hashes"])
    binding = artifact["evaluation_manifest_binding"]
    assert binding["gold_sha256"] == GOLD_SHA256
    assert binding["corpus_manifest_sha256"] == CORPUS_MANIFEST_SHA256
    assert binding["case_count"] == 72
    assert binding["status"] == "PASS"


def test_all_three_protected_scopes_are_immutable():
    scopes = freeze()["protected_scopes"]
    assert scopes["frozen_real_world_corpus"]["monitored_file_count"] == 40
    assert scopes["controlled_corpus_v2"]["monitored_file_count"] == 10
    assert scopes["production_rag"]["monitored_file_count"] == 21
    assert all(item["mismatch_count"] == 0 for item in scopes.values())
    assert all(item["expected_hash_map_sha256"] == item["actual_hash_map_sha256"] for item in scopes.values())


def test_duplicate_leakage_and_no_execution_audits_are_zero():
    artifact = freeze()
    leakage = artifact["duplicate_and_leakage_audit"]
    assert leakage == {
        "information_need_key_unique_count": 72,
        "exact_duplicate_question_count": 0,
        "near_duplicate_question_pair_count": 0,
        "exact_source_sentence_question_count": 0,
        "runtime_id_leakage_count": 0,
        "baseline_answer_leakage_count": 0,
        "real_world_baseline_output_file_count": 0,
    }
    assert artifact["no_execution_audit"] == {
        "deepseek_calls": 0,
        "other_llm_calls": 0,
        "production_rag_ask_calls": 0,
        "real_world_baseline_executions": 0,
        "embedding_executions": 0,
        "faiss_retrieval_executions": 0,
        "baseline_executed_before_freeze": False,
    }


def test_baseline_binding_contract_contains_both_frozen_identities():
    text = (GOLD / "BASELINE_BINDING.md").read_text(encoding="utf-8")
    assert GOLD_SHA256 in text
    assert FREEZE_SHA256 in text
    assert CORPUS_MANIFEST_SHA256 in text
    for required in freeze()["baseline_binding_contract"]["required_identity_fields"]:
        assert required in text
    assert "Any semantic modification after this point requires a new benchmark version." in text


def test_final_freeze_verifier_passes_without_executing_a_baseline():
    # The historical CLI reconstructs the pre-freeze filesystem and therefore
    # intentionally rejects any later result file whose name contains "baseline".
    # Post-C regression artifacts are required to use that name, so the current
    # gate verifies the immutable Gold identities plus the successor production
    # integrity scope directly, without executing retrieval or a baseline.
    artifact = freeze()
    recorded = (GOLD / "gold_dataset_v1_freeze_manifest.sha256").read_text(
        encoding="utf-8"
    ).split()[0]
    baseline = load("immutability_baseline.json")
    assert digest(GOLD / "gold_cases.json") == GOLD_SHA256
    assert digest(GOLD / "gold_dataset_v1_freeze_manifest.json") == FREEZE_SHA256
    assert recorded == FREEZE_SHA256
    assert artifact["status"] == "FROZEN"
    assert artifact["semantic_closure"]["supported"] == 104
    assert artifact["no_execution_audit"]["baseline_executed_before_freeze"] is False
    assert baseline["production_rag_rebaseline"] == {
        "authority_run_id": "20260816T122526Z-gencoveragep1",
        "plan": "evals/rag_real_world_corpus/v1/results/rag_one_final_closure/20260816T130718Z-onefinalclosure/authorized_prompt_hash_rebaseline.json",
        "changed_hash_count": 1,
        "file_count_before": 21,
        "file_count_after": 21,
        "hash_algorithm": "SHA-256",
        "strict_equality_required": True,
    }
    for relative_path, expected_hash in baseline["production_rag"].items():
        assert digest(ROOT / relative_path) == expected_hash
