"""Deterministic final validator for Real-world Gold Dataset V1."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
from typing import Any

from build_evidence_anchors import build_anchor
from gold_common import (
    CORE_TYPES, GOLD_ROOT, REPO_ROOT, STRESS_TYPES, json_schema_errors,
    load_anchor_specs, load_manifest, read_json, validate_case, write_json,
)


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_v2_helpers():
    path = REPO_ROOT / "evals" / "rag_demo_corpus" / "v1" / "contracts" / "v2" / "eval_v2.py"
    spec = importlib.util.spec_from_file_location("learnpilot_controlled_eval_v2_helpers", path)
    if not spec or not spec.loader:
        raise RuntimeError("cannot load Controlled V2 helper module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_immutability(errors: list[str]) -> dict[str, int]:
    baseline = read_json(GOLD_ROOT / "immutability_baseline.json")
    counts = {}
    for scope in ("frozen_real_world_corpus", "controlled_corpus_v2", "production_rag"):
        mismatches = []
        for relative, expected in baseline[scope].items():
            path = REPO_ROOT / relative
            if not path.is_file() or digest(path) != expected:
                mismatches.append(relative)
        counts[scope] = len(mismatches)
        if mismatches:
            errors.append(f"{scope} immutability mismatch: {mismatches}")
    return counts


def validate_artifacts() -> dict[str, Any]:
    errors: list[str] = []
    gold = read_json(GOLD_ROOT / "gold_cases.json")
    gold_schema = read_json(GOLD_ROOT / "gold_cases.schema.json")
    anchors_artifact = read_json(GOLD_ROOT / "evidence_anchors.json")
    anchor_schema = read_json(GOLD_ROOT / "evidence_anchors.schema.json")
    reviews = read_json(GOLD_ROOT / "independent_reviews.json")
    review_scope = reviews.get("verification_scope", {})
    if review_scope.get("independent_semantic_rejudgment_performed") is not False:
        errors.append("independent review semantic re-judgment scope is missing or overstated")
    claim_binding_reviews = [
        claim_review
        for review in reviews.get("reviews", [])
        for claim_review in review.get("claim_reviews", [])
    ]
    if any(
        item.get("semantic_rejudgment") != "NOT_PERFORMED" or "verdict" in item
        for item in claim_binding_reviews
    ):
        errors.append("independent review contains an undeclared semantic verdict")
    reviews_schema = read_json(GOLD_ROOT / "independent_reviews.schema.json")
    binding = read_json(GOLD_ROOT / "evaluation_manifest.json")
    manifest = load_manifest()
    specs = load_anchor_specs()
    errors.extend("gold schema: " + item for item in json_schema_errors(gold, gold_schema))
    errors.extend("anchor schema: " + item for item in json_schema_errors(anchors_artifact, anchor_schema))
    errors.extend("review schema: " + item for item in json_schema_errors(reviews, reviews_schema))
    cases = gold.get("cases", [])
    if len(cases) != 72:
        errors.append(f"case count must be 72, got {len(cases)}")
    case_ids = [item.get("case_id", "") for item in cases]
    claim_ids = [claim.get("claim_id", "") for case in cases for claim in case.get("claims", [])]
    questions = [" ".join(case.get("question", "").casefold().split()) for case in cases]
    if len(case_ids) != len(set(case_ids)):
        errors.append("duplicate case IDs")
    if len(claim_ids) != len(set(claim_ids)):
        errors.append("duplicate claim IDs")
    if len(questions) != len(set(questions)):
        errors.append("duplicate questions")
    tier_counts = Counter(case.get("tier") for case in cases)
    type_counts = Counter(case.get("case_type") for case in cases)
    language_counts = Counter(case.get("query_language") for case in cases)
    topic_counts = Counter(case.get("primary_topic") for case in cases)
    difficulty_counts = Counter(case.get("difficulty") for case in cases)
    if tier_counts != Counter({"CORE": 60, "STRESS": 12}):
        errors.append(f"wrong CORE/STRESS distribution: {tier_counts}")
    if type_counts != Counter(CORE_TYPES) + Counter(STRESS_TYPES):
        errors.append(f"wrong case type distribution: {type_counts}")
    if language_counts != Counter({"zh-CN": 54, "en": 18}):
        errors.append(f"wrong language distribution: {language_counts}")
    if any(not 16 <= topic_counts[topic] <= 20 for topic in topic_counts):
        errors.append(f"primary-topic imbalance: {topic_counts}")
    for case in cases:
        errors.extend(validate_case(case, manifest, specs))
        required_docs = {doc for group in case["evidence_groups"] for doc in group["any_of_document_ids"]}
        acceptable_docs = {item["document_id"] for item in case["acceptable_supporting_evidence"]}
        distractor_docs = {item["document_id"] for item in case["plausible_distractor_documents"]}
        if (required_docs & acceptable_docs) or (required_docs & distractor_docs) or (acceptable_docs & distractor_docs):
            errors.append(f"{case['case_id']}: evidence role overlap")
        if case["case_type"] == "source_disambiguation" and not distractor_docs:
            errors.append(f"{case['case_id']}: source disambiguation lacks UNSUPPORTED source")
        if case["case_type"] == "high_overlap_source_conflict" and not (required_docs and acceptable_docs and distractor_docs):
            errors.append(f"{case['case_id']}: conflict case lacks all three evidence roles")
    anchors = {item["evidence_id"]: item for item in anchors_artifact.get("anchors", [])}
    if len(anchors) != anchors_artifact.get("anchor_count") or len(anchors) != 89:
        errors.append("anchor count/ID uniqueness mismatch")
    document_by_id = {item["document_id"]: item for item in manifest["documents"]}
    spec_by_id = {"ev-rw-" + item["id"]: item for item in specs}
    for evidence_id, anchor in anchors.items():
        spec = spec_by_id.get(evidence_id)
        if not spec or anchor != build_anchor(spec, document_by_id[spec["doc"]]):
            errors.append(f"evidence anchor does not recompute: {evidence_id}")
        serialized = json.dumps(anchor, ensure_ascii=False).casefold()
        if any(term in serialized for term in ("material.id", "materialchunk.id", "chunk_id", "material_id", "faiss index position")):
            errors.append(f"runtime ID in canonical anchor: {evidence_id}")
    review_by_case = {item["case_id"]: item for item in reviews.get("reviews", [])}
    if len(review_by_case) != 72 or reviews.get("verified_count") != 72:
        errors.append("independent review count is not 72/72")
    draft_path = GOLD_ROOT / "merged_draft.json"
    if reviews.get("draft_file_sha256") != digest(draft_path):
        errors.append("independent reviews do not bind current merged draft")
    for case in cases:
        review = review_by_case.get(case["case_id"])
        if not review or review.get("verification_status") != "VERIFIED" or not review.get("review_reason"):
            errors.append(f"{case['case_id']}: missing verified review/audit reason")
        elif case.get("verification", {}).get("review_reason") != review["review_reason"]:
            errors.append(f"{case['case_id']}: final verification differs from independent review")
    manifest_path = REPO_ROOT / "evals" / "rag_real_world_corpus" / "v1" / "corpus_manifest.json"
    if binding.get("corpus_manifest_hash") != digest(manifest_path):
        errors.append("Gold/corpus manifest hash mismatch")
    if binding.get("gold_dataset_hash") != digest(GOLD_ROOT / "gold_cases.json"):
        errors.append("evaluation manifest Gold hash mismatch")
    if binding.get("case_count") != 72 or binding.get("corpus_id") != manifest["corpus_id"] or binding.get("corpus_version") != manifest["corpus_version"]:
        errors.append("evaluation manifest identity/count mismatch")
    robustness = read_json(GOLD_ROOT / "robustness_audit.json")
    if robustness.get("status") != "PASS" or any(robustness.get(field, 1) for field in (
        "exact_duplicate_question_count", "near_duplicate_question_pair_count", "exact_source_sentence_question_count",
        "title_only_question_risk_count", "ambiguous_required_evidence_count", "unsupported_claim_expectation_count", "role_conflict_count",
    )):
        errors.append("robustness audit does not pass")
    execution_audit = read_json(GOLD_ROOT / "task_execution_audit.json")
    if any(execution_audit.get(field) != 0 for field in (
        "llm_or_deepseek_call_count", "rag_answer_call_count", "rag_baseline_execution_count",
        "production_rag_write_count", "frozen_corpus_content_write_count", "controlled_v2_write_count",
    )):
        errors.append("task execution audit records an out-of-scope call or write")
    distribution = read_json(GOLD_ROOT / "distribution_audit.json")
    participation = distribution.get("required_document_participation", {})
    recomputed_left = sum(
        len({doc for group in case["evidence_groups"] if group["required"] for doc in group["any_of_document_ids"]})
        for case in cases
    )
    recomputed_right = sum(
        sum(
            document_id in {
                doc
                for group in case["evidence_groups"]
                if group["required"]
                for doc in group["any_of_document_ids"]
            }
            for case in cases
        )
        for document_id in document_by_id
    )
    if (
        recomputed_left != recomputed_right
        or participation.get("left_sum_of_per_case_unique_required_document_count") != recomputed_left
        or participation.get("right_sum_of_per_document_distinct_required_case_count") != recomputed_right
        or participation.get("match") is not True
    ):
        errors.append("required-document participation invariant does not hold")
    if distribution.get("pdf_required_case_count", 0) < 6 or distribution.get("txt_required_or_acceptable_case_count", 0) < 3:
        errors.append("format coverage below minimum")
    if any(item["sole_required_core_answerable_case_count"] > 8 for item in distribution["document_exposure"].values()):
        errors.append("one document dominates sole-required CORE answerable cases")
    if not all(distribution["document_exposure"][doc]["required_case_count"] + distribution["document_exposure"][doc]["acceptable_support_case_count"] > 0 for doc in document_by_id):
        errors.append("a corpus document has no meaningful Gold participation")
    core_multi = [case for case in cases if case["case_type"] == "multi_doc_synthesis"]
    core_multi_doc_counts = Counter(len({doc for group in case["evidence_groups"] for doc in group["any_of_document_ids"]}) for case in core_multi)
    if core_multi_doc_counts[2] < 6 or core_multi_doc_counts[3] < 2:
        errors.append(f"CORE multi-document coverage below requirement: {core_multi_doc_counts}")
    if not any(len(group["any_of_evidence_ids"]) > 1 for case in cases for group in case["evidence_groups"]):
        errors.append("no OR evidence group with alternative anchors")
    v2 = load_v2_helpers()
    or_case = next(case for case in cases if any(len(group["any_of_evidence_ids"]) > 1 for group in case["evidence_groups"]))
    or_group = next(group for group in or_case["evidence_groups"] if len(group["any_of_evidence_ids"]) > 1)
    if v2.group_coverage(or_case, [or_group["any_of_document_ids"][0]]) <= 0:
        errors.append("Controlled V2 group_coverage helper rejected Real-world OR semantics")
    and_case = next(
        case
        for case in cases
        if len(v2.required_groups(case)) >= 3
        and len({group["any_of_document_ids"][0] for group in v2.required_groups(case)})
        == len(v2.required_groups(case))
    )
    first_docs = [group["any_of_document_ids"][0] for group in v2.required_groups(and_case)]
    if v2.group_coverage(and_case, first_docs[:-1]) >= 1.0 or v2.group_coverage(and_case, first_docs) != 1.0:
        errors.append("Controlled V2 required_groups/group_coverage helper rejected Real-world AND semantics")
    immutable_mismatches = validate_immutability(errors)
    return {
        "schema_version": "1.0.0",
        "status": "PASS" if not errors else "FAIL",
        "case_count": len(cases),
        "reviewed_case_count": len(review_by_case),
        "independent_review_verification_scope": review_scope,
        "independent_semantic_rejudgment_count": sum(
            item.get("semantic_rejudgment") != "NOT_PERFORMED" for item in claim_binding_reviews
        ),
        "tier_distribution": dict(sorted(tier_counts.items())),
        "case_type_distribution": dict(sorted(type_counts.items())),
        "query_language_distribution": dict(sorted(language_counts.items())),
        "topic_distribution": dict(sorted(topic_counts.items())),
        "difficulty_distribution": dict(sorted(difficulty_counts.items())),
        "anchor_count": len(anchors),
        "unresolved_document_reference_count": sum("unresolved" in item and "document" in item for item in errors),
        "unresolved_evidence_anchor_count": sum("unresolved" in item and "anchor" in item for item in errors),
        "invalid_claim_reference_count": sum("claim" in item and ("unknown" in item or "unresolved" in item) for item in errors),
        "unverified_case_count": 72 - sum(item.get("verification_status") == "VERIFIED" for item in review_by_case.values()),
        "duplicate_case_id_count": len(case_ids) - len(set(case_ids)),
        "immutable_scope_mismatch_count": immutable_mismatches,
        "v2_helper_compatibility": "PASS" if not any("Controlled V2" in item for item in errors) else "FAIL",
        "llm_or_baseline_execution_count": execution_audit["llm_or_deepseek_call_count"] + execution_audit["rag_baseline_execution_count"],
        "errors": errors,
    }


def main() -> None:
    result = validate_artifacts()
    write_json(GOLD_ROOT / "final_validation.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
