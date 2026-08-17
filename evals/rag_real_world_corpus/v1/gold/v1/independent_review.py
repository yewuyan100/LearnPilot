"""Deterministic structural and frozen-corpus binding review.

This pass deliberately does not assign semantic support verdicts. It proves
that authored claims bind to resolvable evidence groups and byte-stable source
locators; the semantic judgment embodied by the authored Gold is not re-judged
by an independent human or model here.
"""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import re
from typing import Any

from pypdf import PdfReader

from gold_common import GOLD_ROOT, REPO_ROOT, json_schema_errors, read_json, write_json


REVIEW_VERSION = "real-world-gold-review-v1"
REVIEWER_MODE = "FRESH_CORPUS_EVIDENCE_PASS"
VERIFICATION_SCOPE = {
    "structural_contract_validation": True,
    "frozen_corpus_locator_revalidation": True,
    "anchor_hash_recomputation": True,
    "independent_semantic_rejudgment_performed": False,
}


def normalize(text: str) -> str:
    return " ".join(text.replace("\x00", "").split())


def recompute_anchor_text(anchor: dict[str, Any]) -> str:
    locator = anchor["locator"]
    path = REPO_ROOT / locator["source_path"]
    if locator["kind"] == "SOURCE_LINES":
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        return normalize("\n".join(lines[locator["start_line"] - 1:locator["end_line"]]))
    return normalize(PdfReader(str(path)).pages[locator["page_number"] - 1].extract_text() or "")


def question_fingerprint(text: str) -> set[str]:
    normalized = re.sub(r"\s+", "", text.casefold())
    character_grams = {"c:" + normalized[index:index + 3] for index in range(max(0, len(normalized) - 2))}
    latin_words = {"w:" + item for item in re.findall(r"[a-z0-9_]+", text.casefold()) if len(item) > 2}
    return character_grams | latin_words


def question_near_duplicate(left: str, right: str) -> bool:
    a, b = question_fingerprint(left), question_fingerprint(right)
    if not a or not b:
        return normalize(left).casefold() == normalize(right).casefold()
    return len(a & b) / len(a | b) >= 0.82


def review_case(case: dict[str, Any], anchors: dict[str, dict[str, Any]], document_topics: dict[str, str]) -> dict[str, Any]:
    case_id = case["case_id"]
    errors: list[str] = []
    groups = case["evidence_groups"]
    group_by_id = {item["evidence_group_id"]: item for item in groups}
    required_docs = {doc for group in groups for doc in group["any_of_document_ids"]}
    acceptable_docs = {item["document_id"] for item in case["acceptable_supporting_evidence"]}
    distractor_docs = {item["document_id"] for item in case["plausible_distractor_documents"]}
    if (required_docs & acceptable_docs) or (required_docs & distractor_docs) or (acceptable_docs & distractor_docs):
        errors.append("evidence roles overlap")
    evidence_ids = {
        evidence_id for group in groups for evidence_id in group["any_of_evidence_ids"]
    }
    if not case["answerable"]:
        evidence_ids |= set(case["unanswerable_contract"]["near_boundary_evidence_ids"])
    evidence_reviews = []
    for evidence_id in sorted(evidence_ids):
        anchor = anchors[evidence_id]
        text = recompute_anchor_text(anchor)
        actual_hash = sha256(text.encode("utf-8")).hexdigest()
        if actual_hash != anchor["anchor_text_hash"]:
            errors.append(f"anchor hash mismatch: {evidence_id}")
        evidence_reviews.append({
            "evidence_id": evidence_id,
            "document_id": anchor["document_id"],
            "locator_kind": anchor["locator"]["kind"],
            "anchor_hash_recomputed": actual_hash,
            "locator_resolution": "PASS",
            "source_binding_status": "PASS",
        })
    claim_reviews = []
    for claim in case["claims"]:
        referenced = claim["evidence_group_ids"]
        if set(referenced) - set(group_by_id):
            errors.append(f"claim has unresolved group: {claim['claim_id']}")
        if case["answerable"] and not referenced:
            errors.append(f"answerable claim has no evidence group: {claim['claim_id']}")
        if not case["answerable"] and claim["evaluation_mode"] != "ANSWERABILITY_ONLY":
            errors.append(f"unanswerable claim mode is not ANSWERABILITY_ONLY: {claim['claim_id']}")
        claim_reviews.append({
            "claim_id": claim["claim_id"],
            "binding_status": (
                "EVIDENCE_GROUP_BINDING_VERIFIED"
                if case["answerable"] else
                "NEAR_BOUNDARY_ANCHOR_BINDING_VERIFIED"
            ),
            "semantic_rejudgment": "NOT_PERFORMED",
            "evidence_group_ids": referenced,
            "rationale": (
                "Claim references resolve to evidence groups whose frozen-source locators and hashes were recomputed; semantic support was not independently re-judged."
                if case["answerable"] else
                "The authored near-boundary anchors resolve and hash-match; corpus-wide absence and answerability were not independently re-judged."
            ),
        })
    citation = case["citation_contract"]
    if case["answerable"]:
        if not citation["citation_required"] or citation["forbid_citations"]:
            errors.append("answerable citation contract is invalid")
    else:
        if groups or citation["citation_required"] or not citation["forbid_citations"]:
            errors.append("unanswerable evidence/citation contract is invalid")
    case_type = case["case_type"]
    if case_type == "single_doc_fact" and len(required_docs) != 1:
        errors.append("single_doc_fact does not resolve to one document")
    if case_type == "long_doc_localization" and case["localization_region"] not in {"early", "middle", "deep"}:
        errors.append("long_doc_localization has no source region")
    if case_type == "multi_doc_synthesis" and len(required_docs) < 2:
        errors.append("multi_doc_synthesis does not require multiple documents")
    if case_type == "source_disambiguation" and not (acceptable_docs or distractor_docs):
        errors.append("source_disambiguation has no competing source role")
    if case_type == "deep_long_doc_localization":
        if case["localization_region"] != "deep":
            errors.append("deep stress case is not marked deep")
        if any(anchors[evidence_id]["locator"]["region"] != "deep" for evidence_id in evidence_ids):
            errors.append("deep stress case references a non-deep anchor")
    if case_type == "cross_topic_multi_doc":
        source_topics = {document_topics[doc] for doc in required_docs}
        if len(required_docs) < 2 or len(source_topics) < 2 or not case["secondary_topics"]:
            errors.append("cross-topic stress contract is not satisfied")
    if case_type == "high_overlap_source_conflict":
        if not groups or not acceptable_docs or not distractor_docs:
            errors.append("high-overlap conflict lacks REQUIRED/ACCEPTABLE_SUPPORT/UNSUPPORTED")
    if errors:
        raise RuntimeError(case_id + ": " + "; ".join(errors))
    reason = (
        "Deterministic refusal-contract structure and near-boundary anchor binding passed; corpus-wide absence was not independently re-judged."
        if not case["answerable"] else
        "Deterministic contract structure and frozen-corpus anchor binding passed; claim semantics were not independently re-judged."
    )
    return {
        "case_id": case_id,
        "verification_status": "VERIFIED",
        "review_reason": reason,
        "reviewer_mode": REVIEWER_MODE,
        "review_version": REVIEW_VERSION,
        "checks": {
            "question_field_present": bool(case["question"].strip()),
            "answerability_contract_structure_valid": True,
            "claim_group_references_resolve": True,
            "evidence_anchors_recomputed": True,
            "evidence_role_sets_disjoint": True,
            "citation_contract_structurally_valid": True,
            "case_type_structurally_valid": True,
            "duplicate_question_heuristics_passed": True,
            "independent_semantic_rejudgment_performed": False,
        },
        "claim_reviews": claim_reviews,
        "evidence_reviews": evidence_reviews,
    }


def main() -> None:
    draft_path = GOLD_ROOT / "merged_draft.json"
    draft = read_json(draft_path)
    anchor_artifact = read_json(GOLD_ROOT / "evidence_anchors.json")
    anchors = {item["evidence_id"]: item for item in anchor_artifact["anchors"]}
    manifest = read_json(REPO_ROOT / "evals" / "rag_real_world_corpus" / "v1" / "corpus_manifest.json")
    document_topics = {item["document_id"]: item["topic_cluster"] for item in manifest["documents"]}
    questions = [item["question"] for item in draft["cases"]]
    exact_duplicates = len(questions) - len(set(normalize(item).casefold() for item in questions))
    near_pairs = []
    for left_index, left in enumerate(draft["cases"]):
        for right in draft["cases"][left_index + 1:]:
            if question_near_duplicate(left["question"], right["question"]):
                near_pairs.append([left["case_id"], right["case_id"]])
    if exact_duplicates or near_pairs:
        raise RuntimeError(f"question duplication risk: exact={exact_duplicates}, near={near_pairs}")
    reviews = [review_case(item, anchors, document_topics) for item in draft["cases"]]
    artifact = {
        "schema_version": "1.0.0",
        "review_version": REVIEW_VERSION,
        "reviewer_mode": REVIEWER_MODE,
        "verification_scope": VERIFICATION_SCOPE,
        "draft_file_sha256": sha256(draft_path.read_bytes()).hexdigest(),
        "review_count": len(reviews),
        "verified_count": sum(item["verification_status"] == "VERIFIED" for item in reviews),
        "reviews": reviews,
    }
    schema_errors = json_schema_errors(artifact, read_json(GOLD_ROOT / "independent_reviews.schema.json"))
    if schema_errors:
        raise RuntimeError("\n".join(schema_errors))
    write_json(GOLD_ROOT / "independent_reviews.json", artifact)
    write_json(GOLD_ROOT / "independent_review_summary.json", {
        "schema_version": "1.0.0",
        "status": "PASS",
        "review_count": len(reviews),
        "verified_count": artifact["verified_count"],
        "verification_scope": VERIFICATION_SCOPE,
        "answerable_review_count": sum(item["answerable"] for item in draft["cases"]),
        "unanswerable_review_count": sum(not item["answerable"] for item in draft["cases"]),
        "claim_review_count": sum(len(item["claim_reviews"]) for item in reviews),
        "independent_semantic_rejudgment_count": 0,
        "evidence_review_count": sum(len(item["evidence_reviews"]) for item in reviews),
        "recomputed_anchor_hash_failure_count": 0,
        "exact_duplicate_question_count": 0,
        "near_duplicate_question_pair_count": 0,
        "case_type_failure_count": 0,
        "role_conflict_count": 0,
    })


if __name__ == "__main__":
    main()
