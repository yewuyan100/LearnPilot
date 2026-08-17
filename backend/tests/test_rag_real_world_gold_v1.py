from __future__ import annotations

from collections import Counter
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "evals" / "rag_real_world_corpus" / "v1" / "gold" / "v1"
CORPUS = ROOT / "evals" / "rag_real_world_corpus" / "v1"
if str(GOLD) not in sys.path:
    sys.path.insert(0, str(GOLD))

import gold_common as COMMON  # noqa: E402


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def gold():
    return load(GOLD / "gold_cases.json")


def case(case_id: str):
    return next(item for item in gold()["cases"] if item["case_id"] == case_id)


def anchors():
    return {item["evidence_id"]: item for item in load(GOLD / "evidence_anchors.json")["anchors"]}


def required_documents(item):
    return {doc for group in item["evidence_groups"] for doc in group["any_of_document_ids"]}


def test_72_case_distribution_and_core_stress_counts():
    cases = gold()["cases"]
    assert len(cases) == 72
    assert Counter(item["tier"] for item in cases) == {"CORE": 60, "STRESS": 12}
    assert Counter(item["case_type"] for item in cases) == {
        "single_doc_fact": 10,
        "semantic_paraphrase": 10,
        "long_doc_localization": 10,
        "multi_doc_synthesis": 10,
        "source_disambiguation": 10,
        "unanswerable_near_boundary": 10,
        "deep_long_doc_localization": 4,
        "cross_topic_multi_doc": 4,
        "high_overlap_source_conflict": 4,
    }


def test_and_evidence_groups_require_every_group():
    target = case("rw-gold-v1-stress-cross-retrieval-evaluation")
    assert len(target["evidence_groups"]) == 3
    chosen = [group["any_of_document_ids"][0] for group in target["evidence_groups"]]
    assert COMMON.minimum_hitting_documents(target["evidence_groups"]) == 3
    assert not all(set(chosen[:-1]) & set(group["any_of_document_ids"]) for group in target["evidence_groups"])
    assert all(set(chosen) & set(group["any_of_document_ids"]) for group in target["evidence_groups"])


def test_or_evidence_group_accepts_alternative_stable_anchors():
    target = case("rw-gold-v1-semantic-bge-functions")
    group = target["evidence_groups"][0]
    assert set(group["any_of_document_ids"]) == {"rw-rag-bge-m3"}
    assert set(group["any_of_evidence_ids"]) == {"ev-rw-bge-capabilities", "ev-rw-bge-methods"}


def test_acceptable_supporting_source_is_not_unsupported():
    target = case("rw-gold-v1-disambig-bge-long")
    acceptable = {item["document_id"] for item in target["acceptable_supporting_evidence"]}
    unsupported = {item["document_id"] for item in target["plausible_distractor_documents"]}
    assert "rw-rag-faiss-overview" in acceptable
    assert acceptable.isdisjoint(unsupported | required_documents(target))


def test_pdf_page_locator_resolves_against_frozen_pdf():
    anchor = anchors()["ev-rw-interrupt-approval"]
    assert anchor["locator"]["kind"] == "PDF_PAGE"
    assert anchor["locator"]["page_number"] == 6
    assert anchor["locator"]["source_path"].endswith("rw-agent-interrupts.pdf")
    assert len(anchor["anchor_text_hash"]) == 64


def test_txt_source_locator_uses_lines_and_stable_document_id():
    anchor = anchors()["ev-rw-persist-thread-id"]
    assert anchor["document_id"] == "rw-agent-persistence"
    assert anchor["locator"]["kind"] == "SOURCE_LINES"
    assert anchor["locator"]["source_path"].endswith("rw-agent-persistence.txt")
    assert anchor["locator"]["start_line"] <= anchor["locator"]["end_line"]


def test_long_document_source_anchor_has_deep_region():
    target = case("rw-gold-v1-stress-deep-bge-mldr-comparison")
    evidence_id = target["evidence_groups"][0]["any_of_evidence_ids"][0]
    assert target["localization_region"] == "deep"
    assert anchors()[evidence_id]["locator"]["region"] == "deep"


def test_core_multi_document_requirement_includes_two_three_source_cases():
    cases = [item for item in gold()["cases"] if item["case_type"] == "multi_doc_synthesis"]
    counts = Counter(len(required_documents(item)) for item in cases)
    assert counts[2] >= 6
    assert counts[3] >= 2


def test_cross_topic_stress_requirement_is_explicit():
    manifest = load(CORPUS / "corpus_manifest.json")
    topics = {item["document_id"]: item["topic_cluster"] for item in manifest["documents"]}
    cases = [item for item in gold()["cases"] if item["case_type"] == "cross_topic_multi_doc"]
    assert len(cases) == 4
    assert all(item["secondary_topics"] for item in cases)
    assert all(len({topics[doc] for doc in required_documents(item)}) >= 2 for item in cases)


def test_near_boundary_unanswerable_has_no_required_evidence_or_citation():
    target = case("rw-gold-v1-unanswerable-threadpool-workers")
    assert target["answerable"] is False
    assert target["evidence_groups"] == []
    assert target["claims"][0]["evaluation_mode"] == "ANSWERABILITY_ONLY"
    assert target["citation_contract"]["citation_required"] is False
    assert target["citation_contract"]["forbid_citations"] is True
    assert target["unanswerable_contract"]["fabricated_citation_forbidden"] is True


def test_chinese_query_targets_english_corpus_evidence():
    target = case("rw-gold-v1-single-bge-shape")
    manifest = load(CORPUS / "corpus_manifest.json")
    languages = {item["document_id"]: item["language"] for item in manifest["documents"]}
    assert target["query_language"] == "zh-CN"
    assert all(languages[doc] == "en" for doc in required_documents(target))


def test_duplicate_question_detection_is_rejected():
    target = gold()
    target["cases"][1]["question"] = target["cases"][0]["question"]
    questions = [" ".join(item["question"].casefold().split()) for item in target["cases"]]
    assert len(questions) != len(set(questions))


def test_invalid_document_reference_is_detected():
    target = deepcopy(case("rw-gold-v1-single-bge-shape"))
    target["evidence_groups"][0]["any_of_document_ids"] = ["rw-does-not-exist"]
    errors = COMMON.validate_case(target, COMMON.load_manifest(), COMMON.load_anchor_specs())
    assert any("unresolved evidence-group document" in item for item in errors)


def test_invalid_evidence_anchor_is_detected():
    target = deepcopy(case("rw-gold-v1-single-bge-shape"))
    target["evidence_groups"][0]["any_of_evidence_ids"] = ["ev-rw-does-not-exist"]
    errors = COMMON.validate_case(target, COMMON.load_manifest(), COMMON.load_anchor_specs())
    assert any("unresolved evidence anchor" in item for item in errors)


def test_manifest_hash_binding_matches_corpus_and_gold():
    binding = load(GOLD / "evaluation_manifest.json")
    assert binding["corpus_manifest_hash"] == sha256((CORPUS / "corpus_manifest.json").read_bytes()).hexdigest()
    assert binding["gold_dataset_hash"] == sha256((GOLD / "gold_cases.json").read_bytes()).hexdigest()
    assert binding["case_count"] == 72


def test_gold_immutability_is_bound_to_independent_review_and_manifest():
    draft_hash = sha256((GOLD / "merged_draft.json").read_bytes()).hexdigest()
    reviews = load(GOLD / "independent_reviews.json")
    assert reviews["draft_file_sha256"] == draft_hash
    assert reviews["verified_count"] == 72
    assert all(item["verification_status"] == "VERIFIED" for item in reviews["reviews"])
    assert reviews["verification_scope"] == {
        "structural_contract_validation": True,
        "frozen_corpus_locator_revalidation": True,
        "anchor_hash_recomputation": True,
        "independent_semantic_rejudgment_performed": False,
    }
    claim_reviews = [claim for review in reviews["reviews"] for claim in review["claim_reviews"]]
    assert len(claim_reviews) == 132
    assert all(item["semantic_rejudgment"] == "NOT_PERFORMED" for item in claim_reviews)
    assert all("verdict" not in item for item in claim_reviews)


def test_required_document_participation_invariant_is_recomputed_from_gold():
    cases = gold()["cases"]
    per_case = {
        item["case_id"]: required_documents(item)
        for item in cases
    }
    per_document = Counter(document_id for documents in per_case.values() for document_id in documents)
    assert Counter(len(documents) for documents in per_case.values()) == {0: 10, 1: 41, 2: 18, 3: 3}
    assert sum(map(len, per_case.values())) == 86
    assert sum(per_document.values()) == 86
    assert per_case["rw-gold-v1-semantic-checkpointer-store"] == {
        "rw-agent-langgraph-overview",
        "rw-agent-persistence",
    }


def test_final_validator_and_external_immutability_scopes_pass():
    result = subprocess.run(
        [sys.executable, str(GOLD / "validate_gold.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    validation = json.loads(result.stdout)
    assert validation["status"] == "PASS"
    assert validation["v2_helper_compatibility"] == "PASS"
    assert validation["immutable_scope_mismatch_count"] == {
        "frozen_real_world_corpus": 0,
        "controlled_corpus_v2": 0,
        "production_rag": 0,
    }
