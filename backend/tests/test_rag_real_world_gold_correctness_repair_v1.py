from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
GOLD_ROOT = ROOT / "evals" / "rag_real_world_corpus" / "v1" / "gold" / "v1"
if str(GOLD_ROOT) not in sys.path:
    sys.path.insert(0, str(GOLD_ROOT))

from gold_common import json_schema_errors  # noqa: E402
from gold_correctness_repair_v1 import canonical_hash, semantic_payload  # noqa: E402


PRE_GOLD_HASH = "11b71513b00a63e158333eab5d26bc3aded858116f237b1b3b206dc3f444ba9c"
POST_GOLD_HASH = "33a0b69901fa47e3fe45be0277228cd4a5519fe780fe5b9d2c52b1bfe614927a"
FROZEN_REVIEW_HASH = "89bf00e924579c1c68a88a952797d4bfb73bccab0f7ba8ffe28bb74e5888279d"
REPAIRED_CLAIMS = {
    "rw-gold-v1-semantic-checkpointer-store-claim-01",
    "rw-gold-v1-long-langgraph-positioning-claim-02",
    "rw-gold-v1-multi-rag-tracing-claim-01",
    "rw-gold-v1-multi-rag-tracing-claim-02",
    "rw-gold-v1-disambig-fastapi-async-deps-claim-01",
    "rw-gold-v1-disambig-interrupt-static-claim-01",
    "rw-gold-v1-stress-conflict-fastapi-handler-type-claim-01",
    "rw-gold-v1-stress-conflict-ragas-reference-mode-claim-01",
}


def load(name: str):
    return json.loads((GOLD_ROOT / name).read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def normalize(text: str) -> str:
    return " ".join(text.replace("\x00", "").split())


def reopen(locator: dict) -> tuple[str, str]:
    path = ROOT / locator["source_path"]
    source_hash = digest(path)
    if locator["kind"] == "SOURCE_LINES":
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        text = normalize("\n".join(lines[locator["start_line"] - 1:locator["end_line"]]))
    else:
        reader = PdfReader(str(path))
        text = normalize(reader.pages[locator["page_number"] - 1].extract_text() or "")
    return source_hash, sha256(text.encode("utf-8")).hexdigest()


def test_change_log_and_post_repair_review_are_schema_valid():
    change_log = load("gold_correctness_repair_v1.json")
    change_schema = load("gold_correctness_repair_v1.schema.json")
    post_review = load("post_repair_semantic_verification_v1.json")
    post_schema = load("post_repair_semantic_verification_v1.schema.json")
    assert json_schema_errors(change_log, change_schema) == []
    assert json_schema_errors(post_review, post_schema) == []


def test_exactly_nine_frozen_defects_and_eight_cases_are_accounted_for():
    change_log = load("gold_correctness_repair_v1.json")
    frozen = load("independent_semantic_verification_v1.json")
    assert len(frozen["defects"]) == change_log["repairs"] == len(change_log["repair_records"]) == 9
    assert change_log["affected_cases"] == len(change_log["affected_case_ids"]) == 8
    assert len({item["repair_id"] for item in change_log["repair_records"]}) == 9
    assert {item["case_id"] for item in change_log["repair_records"]} == set(change_log["affected_case_ids"])
    assert all(item["information_need_preserved"] is True for item in change_log["repair_records"])


def test_pre_repair_review_artifact_and_baseline_are_immutable():
    assert digest(GOLD_ROOT / "independent_semantic_verification_v1.json") == FROZEN_REVIEW_HASH
    assert digest(GOLD_ROOT / "gold_correctness_repair_v1_baseline.json") == "88813adad104a129a7c868cb7b7d43550c71b88d48695270a3e92cefa1f5b461"
    baseline = load("gold_correctness_repair_v1_baseline.json")
    assert baseline["pre_repair_gold_sha256"] == PRE_GOLD_HASH
    assert baseline["frozen_review_sha256"] == FROZEN_REVIEW_HASH


def test_gold_hash_changed_and_manifest_binds_repaired_gold():
    current = digest(GOLD_ROOT / "gold_cases.json")
    manifest = load("evaluation_manifest.json")
    change_log = load("gold_correctness_repair_v1.json")
    assert current == POST_GOLD_HASH != PRE_GOLD_HASH
    assert manifest["gold_dataset_hash"] == current
    assert change_log["pre_repair_gold_sha256"] == PRE_GOLD_HASH
    assert change_log["post_repair_gold_sha256"] == current


def test_exactly_64_unaffected_case_payload_hashes_are_unchanged():
    baseline = load("gold_correctness_repair_v1_baseline.json")
    gold = load("gold_cases.json")
    current = {case["case_id"]: canonical_hash(semantic_payload(case)) for case in gold["cases"]}
    changed = sorted(
        case_id for case_id, value in current.items()
        if value != baseline["case_semantic_payload_sha256"][case_id]
    )
    assert changed == baseline["affected_case_ids"]
    assert len(changed) == 8
    unchanged = [case_id for case_id in baseline["unaffected_case_ids"] if current[case_id] == baseline["case_semantic_payload_sha256"][case_id]]
    assert len(unchanged) == 64


def test_96_previously_supported_claim_payloads_are_unchanged():
    post = load("post_repair_semantic_verification_v1.json")
    proof = post["previously_supported_claim_payload_proof"]
    assert len(proof) == 96
    assert len({item["claim_id"] for item in proof}) == 96
    assert all(item["unchanged"] for item in proof)
    assert all(item["pre_repair_sha256"] == item["post_repair_sha256"] for item in proof)


def test_all_eight_repaired_semantic_claims_are_freshly_rereviewed_once():
    post = load("post_repair_semantic_verification_v1.json")
    reviews = post["claim_reviews"]
    assert len(reviews) == len({item["claim_id"] for item in reviews}) == 8
    assert {item["claim_id"] for item in reviews} == REPAIRED_CLAIMS
    assert all(item["old_verdict"] == "PARTIALLY_SUPPORTED" for item in reviews)
    assert all(item["new_verdict"] == item["claim_verdict"] == "SUPPORTED" for item in reviews)
    assert all(item["fresh_corpus_reopen"] is True for item in reviews)
    assert all(item["authoring_verdict_used"] is False for item in reviews)
    closure = post["final_semantic_closure"]
    assert closure["semantic_review_total"] == 104
    assert closure["previously_supported_and_unchanged"] == 96
    assert closure["repaired_semantic_claims_reviewed"] == 8
    assert closure["verdict_distribution"] == {
        "SUPPORTED": 104,
        "PARTIALLY_SUPPORTED": 0,
        "UNSUPPORTED": 0,
        "AMBIGUOUS": 0,
    }


def test_post_repair_candidates_resolve_against_frozen_corpus():
    anchors = {item["evidence_id"]: item for item in load("evidence_anchors.json")["anchors"]}
    manifest_path = ROOT / "evals" / "rag_real_world_corpus" / "v1" / "corpus_manifest.json"
    documents = {item["document_id"]: item for item in json.loads(manifest_path.read_text(encoding="utf-8"))["documents"]}
    for review in load("post_repair_semantic_verification_v1.json")["claim_reviews"]:
        assert review["group_combination_logic"] == "AND"
        for group in review["new_evidence_groups"]:
            assert group["logic"] == "OR"
            assert group["group_verdict"] == "SUPPORTED"
            for candidate in group["candidate_anchors"]:
                source_hash, text_hash = reopen(candidate["locator"])
                anchor = anchors[candidate["evidence_id"]]
                assert source_hash == candidate["source_bytes_sha256"] == documents[candidate["document_id"]]["corpus_sha256"]
                assert text_hash == candidate["fresh_text_sha256"] == anchor["anchor_text_hash"]
                assert candidate["candidate_semantic_verdict"] == "SUPPORTED"


def test_evidence_role_defect_is_resolved_without_conflict():
    gold = load("gold_cases.json")
    target = next(case for case in gold["cases"] if case["case_id"] == "rw-gold-v1-disambig-fastapi-exceptions")
    assert target["acceptable_supporting_evidence"] == []
    unsupported = {item["document_id"] for item in target["plausible_distractor_documents"]}
    assert "rw-backend-fastapi-async" in unsupported
    post = load("post_repair_semantic_verification_v1.json")
    role_closure = post["evidence_role_closure"]
    assert role_closure["target_case_count"] == len(role_closure["case_reviews"]) == 14
    assert role_closure["misclassified_count"] == 0
    assert all(item["role_verdict"] == "VERIFIED" for item in role_closure["case_reviews"])


def test_all_89_anchors_resolve_and_audit_passes():
    anchors = load("evidence_anchors.json")["anchors"]
    audit = load("gold_correctness_repair_v1_audit.json")
    assert len(anchors) == audit["anchor_audit"]["anchor_count"] == audit["anchor_audit"]["pass_count"] == 89
    assert audit["anchor_audit"]["new_anchor_count"] == 0
    assert all(item["status"] == "PASS" and item["runtime_id_leakage"] is False for item in audit["anchor_audit"]["records"])
    for anchor in anchors:
        _, text_hash = reopen(anchor["locator"])
        assert text_hash == anchor["anchor_text_hash"]


def test_distribution_changes_are_only_repair_mechanics():
    audit = load("gold_correctness_repair_v1_audit.json")
    before, after = audit["distribution_before"], audit["distribution_after"]
    for key in ("case_count", "claim_count", "case_type_distribution", "topic_distribution", "query_language_distribution", "difficulty_distribution"):
        assert before[key] == after[key]
    assert before["distinct_required_document_participation"] == after["distinct_required_document_participation"] == 86
    assert before["candidate_multi_document_case_count"] == after["candidate_multi_document_case_count"] == 21
    assert before["candidate_required_document_count_distribution"] == after["candidate_required_document_count_distribution"]
    assert before["minimum_hitting_set_distribution"] == {"0": 10, "1": 42, "2": 17, "3": 3}
    assert after["minimum_hitting_set_distribution"] == {"0": 10, "1": 41, "2": 18, "3": 3}
    assert before["evidence_group_count"] == 91
    assert after["evidence_group_count"] == 100
    assert before["role_record_counts"]["ACCEPTABLE_SUPPORT"] == 12
    assert after["role_record_counts"]["ACCEPTABLE_SUPPORT"] == 11
    assert before["role_record_counts"]["UNSUPPORTED"] == 24
    assert after["role_record_counts"]["UNSUPPORTED"] == 25


def test_corpus_controlled_v2_and_production_rag_immutability_pass():
    audit = load("gold_correctness_repair_v1_audit.json")
    assert audit["status"] == "PASS"
    for scope in ("frozen_real_world_corpus", "controlled_corpus_v2", "production_rag"):
        assert audit["immutability"][scope]["mismatch_count"] == 0
        assert audit["immutability"][scope]["mismatches"] == []
    assert audit["final_status"] == {
        "gold_correctness_repair_v1": "COMPLETE",
        "rag_real_world_gold_dataset_v1": "READY_FOR_FINAL_FREEZE",
        "do_not_run_baseline": True,
    }
    assert set(audit["execution_audit"].values()) == {0}
