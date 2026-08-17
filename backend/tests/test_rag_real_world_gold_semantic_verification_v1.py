from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
GOLD_ROOT = ROOT / "evals" / "rag_real_world_corpus" / "v1" / "gold" / "v1"
ARTIFACT_PATH = GOLD_ROOT / "independent_semantic_verification_v1.json"
SCHEMA_PATH = GOLD_ROOT / "independent_semantic_verification_v1.schema.json"
GOLD_PATH = GOLD_ROOT / "gold_cases.json"
ANCHORS_PATH = GOLD_ROOT / "evidence_anchors.json"
MANIFEST_PATH = ROOT / "evals" / "rag_real_world_corpus" / "v1" / "corpus_manifest.json"
BASELINE_PATH = GOLD_ROOT / "immutability_baseline.json"
EXPECTED_ARTIFACT_SHA256 = "89bf00e924579c1c68a88a952797d4bfb73bccab0f7ba8ffe28bb74e5888279d"
SEMANTIC_VERDICTS = {"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "AMBIGUOUS"}
if str(GOLD_ROOT) not in sys.path:
    sys.path.insert(0, str(GOLD_ROOT))

from gold_common import json_schema_errors  # noqa: E402


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def artifact():
    return load(ARTIFACT_PATH)


def normalize(text: str) -> str:
    return " ".join(text.replace("\x00", "").split())


def reopen(locator: dict) -> tuple[str, str]:
    path = ROOT / locator["source_path"]
    source_hash = sha256(path.read_bytes()).hexdigest()
    if locator["kind"] == "SOURCE_LINES":
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        text = normalize("\n".join(lines[locator["start_line"] - 1:locator["end_line"]]))
    else:
        reader = PdfReader(str(path))
        text = normalize(reader.pages[locator["page_number"] - 1].extract_text() or "")
    return source_hash, sha256(text.encode("utf-8")).hexdigest()


def test_review_artifact_is_schema_valid_and_hash_frozen():
    schema = load(SCHEMA_PATH)
    errors = json_schema_errors(artifact(), schema)
    assert errors == []
    assert sha256(ARTIFACT_PATH.read_bytes()).hexdigest() == EXPECTED_ARTIFACT_SHA256


def test_exactly_every_semantic_claim_is_reviewed_once():
    gold = load(GOLD_PATH)
    expected = [
        claim["claim_id"]
        for case in gold["cases"]
        for claim in case["claims"]
        if claim["evaluation_mode"] == "SEMANTIC_REVIEW"
    ]
    reviewed = [item["claim_id"] for item in artifact()["semantic_claim_reviews"]]
    assert len(expected) == len(reviewed) == 104
    assert len(reviewed) == len(set(reviewed))
    assert set(reviewed) == set(expected)


def test_verdict_vocabulary_distribution_and_total_invariant():
    data = artifact()
    reviews = data["semantic_claim_reviews"]
    assert all(item["claim_verdict"] in SEMANTIC_VERDICTS for item in reviews)
    counts = Counter(item["claim_verdict"] for item in reviews)
    assert counts == {"SUPPORTED": 96, "PARTIALLY_SUPPORTED": 8}
    declared = data["summary"]["claim_verdict_distribution"]
    assert sum(declared.values()) == 104
    assert declared == {
        "AMBIGUOUS": 0,
        "PARTIALLY_SUPPORTED": 8,
        "SUPPORTED": 96,
        "UNSUPPORTED": 0,
    }


def test_group_and_or_semantics_are_recomputable_from_candidate_verdicts():
    for review in artifact()["semantic_claim_reviews"]:
        group_verdicts = []
        for group in review["groups"]:
            candidates = [item["candidate_semantic_verdict"] for item in group["candidate_anchors"]]
            expected_group = (
                "SUPPORTED" if "SUPPORTED" in candidates else
                "PARTIALLY_SUPPORTED" if "PARTIALLY_SUPPORTED" in candidates else
                "AMBIGUOUS" if "AMBIGUOUS" in candidates else
                "UNSUPPORTED"
            )
            assert group["logic"] == "OR"
            assert group["group_verdict"] == expected_group
            group_verdicts.append(expected_group)
        expected_claim = (
            "UNSUPPORTED" if "UNSUPPORTED" in group_verdicts else
            "AMBIGUOUS" if "AMBIGUOUS" in group_verdicts else
            "PARTIALLY_SUPPORTED" if "PARTIALLY_SUPPORTED" in group_verdicts else
            "SUPPORTED"
        )
        assert review["group_combination_logic"] == "AND"
        assert review["claim_verdict"] == expected_claim


def test_all_candidate_anchors_resolve_and_fresh_hashes_match():
    anchors = {item["evidence_id"]: item for item in load(ANCHORS_PATH)["anchors"]}
    documents = {item["document_id"]: item for item in load(MANIFEST_PATH)["documents"]}
    seen = {}
    for review in artifact()["semantic_claim_reviews"]:
        for group in review["groups"]:
            for candidate in group["candidate_anchors"]:
                source_hash, text_hash = reopen(candidate["locator"])
                anchor = anchors[candidate["evidence_id"]]
                document = documents[candidate["document_id"]]
                assert candidate["locator"] == anchor["locator"]
                assert source_hash == candidate["source_bytes_sha256"] == document["corpus_sha256"]
                assert text_hash == candidate["fresh_text_sha256"] == anchor["anchor_text_hash"]
                seen[candidate["evidence_id"]] = True
    assert seen


def test_reviewer_input_isolation_and_no_llm_or_baseline_dependency():
    data = artifact()
    method = data["review_method"]
    assert method["fresh_corpus_reopen"] is True
    assert method["authoring_verdict_used"] is False
    assert method["old_independent_review_verdict_used"] is False
    assert method["baseline_output_used"] is False
    assert method["retrieval_output_used"] is False
    assert method["llm_used"] is False
    assert method["production_rag_used"] is False
    assert all(item["authoring_semantic_verdict_visible_to_reviewer"] is False for item in data["semantic_claim_reviews"])
    assert set(data["execution_audit"].values()) == {0}


def test_non_semantic_sanity_covers_all_28_claims_once():
    gold = load(GOLD_PATH)
    expected = {
        claim["claim_id"]
        for case in gold["cases"]
        for claim in case["claims"]
        if claim["evaluation_mode"] != "SEMANTIC_REVIEW"
    }
    sanity = artifact()["non_semantic_contract_sanity"]
    assert len(sanity) == len(expected) == 28
    assert {item["claim_id"] for item in sanity} == expected
    assert all(item["sanity_status"] == "PASS" for item in sanity)
    assert Counter(item["evaluation_mode"] for item in sanity) == {
        "ANSWERABILITY_ONLY": 10,
        "NUMERIC_EXACT": 7,
        "STRUCTURED_EXACT": 6,
        "IDENTIFIER_EXACT": 5,
    }


def test_role_review_covers_all_10_core_and_4_stress_target_cases():
    gold = load(GOLD_PATH)
    expected_cases = {
        case["case_id"]
        for case in gold["cases"]
        if case["case_type"] in {"source_disambiguation", "high_overlap_source_conflict"}
    }
    reviews = artifact()["evidence_role_reviews"]
    assert len(expected_cases) == 14
    assert {item["case_id"] for item in reviews} == expected_cases
    defects = [item for item in reviews if item["role_semantic_verdict"] == "MISCLASSIFIED"]
    assert [(item["case_id"], item["document_id"], item["recommended_role"]) for item in defects] == [
        ("rw-gold-v1-disambig-fastapi-exceptions", "rw-backend-fastapi-async", "UNSUPPORTED")
    ]


def test_case_verdicts_and_hold_status_follow_detected_defects():
    data = artifact()
    case_counts = Counter(item["case_verdict"] for item in data["case_reviews"])
    assert len(data["case_reviews"]) == 72
    assert case_counts == {"VERIFIED": 64, "NEEDS_GOLD_FIX": 8}
    assert len(data["defects"]) == 9
    assert data["final_status"] == {
        "independent_semantic_verification_v1": "COMPLETE",
        "gold_correctness_repair_required": "YES",
        "rag_real_world_gold_dataset_v1": "HOLD",
    }


def test_frozen_corpus_controlled_v2_and_production_rag_immutability():
    baseline = load(BASELINE_PATH)
    assert set(baseline) >= {"frozen_real_world_corpus", "controlled_corpus_v2", "production_rag"}
    for scope in ("frozen_real_world_corpus", "controlled_corpus_v2", "production_rag"):
        mismatches = [
            relative
            for relative, expected_hash in baseline[scope].items()
            if not (ROOT / relative).is_file() or sha256((ROOT / relative).read_bytes()).hexdigest() != expected_hash
        ]
        assert mismatches == []
