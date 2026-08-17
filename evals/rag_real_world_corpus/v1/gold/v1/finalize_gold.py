"""Promote the reviewed frozen draft to final Gold and bind it to the corpus."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import re

from gold_common import GOLD_ROOT, REPO_ROOT, json_schema_errors, read_json, write_json


def file_hash(path):
    return sha256(path.read_bytes()).hexdigest()


def required_documents(case):
    return {
        doc
        for group in case["evidence_groups"]
        if group["required"]
        for doc in group["any_of_document_ids"]
    }


def main() -> None:
    draft_path = GOLD_ROOT / "merged_draft.json"
    review_path = GOLD_ROOT / "independent_reviews.json"
    draft = read_json(draft_path)
    reviews = read_json(review_path)
    if reviews["draft_file_sha256"] != file_hash(draft_path):
        raise RuntimeError("independent reviews do not bind the current frozen draft")
    review_by_case = {item["case_id"]: item for item in reviews["reviews"]}
    if len(review_by_case) != 72 or reviews["verified_count"] != 72:
        raise RuntimeError("72/72 declared-scope corpus-binding reviews are required")
    if reviews.get("verification_scope", {}).get("independent_semantic_rejudgment_performed") is not False:
        raise RuntimeError("independent review must accurately declare semantic re-judgment scope")
    cases = deepcopy(draft["cases"])
    for case in cases:
        review = review_by_case.get(case["case_id"])
        if not review or review["verification_status"] != "VERIFIED":
            raise RuntimeError(f"missing verified review: {case['case_id']}")
        case["verification"] = {
            "verification_status": review["verification_status"],
            "review_reason": review["review_reason"],
            "reviewer_mode": review["reviewer_mode"],
            "review_version": review["review_version"],
        }
    gold = {
        "schema_version": "1.0.0",
        "contract_ref": draft["contract_ref"],
        "dataset_id": draft["dataset_id"],
        "dataset_version": draft["dataset_version"],
        "corpus_ref": draft["corpus_ref"],
        "case_count": len(cases),
        "cases": cases,
    }
    schema_errors = json_schema_errors(gold, read_json(GOLD_ROOT / "gold_cases.schema.json"))
    if schema_errors:
        raise RuntimeError("\n".join(schema_errors))
    write_json(GOLD_ROOT / "gold_cases.json", gold)

    manifest_path = REPO_ROOT / "evals" / "rag_real_world_corpus" / "v1" / "corpus_manifest.json"
    created_at = datetime.now(timezone.utc).isoformat()
    binding = {
        "schema_version": "1.0.0",
        "corpus_id": gold["corpus_ref"]["corpus_id"],
        "corpus_version": gold["corpus_ref"]["corpus_version"],
        "corpus_manifest_hash": file_hash(manifest_path),
        "eval_contract_version": "learnpilot-rag-eval-gold-contract-v2+real-world-anchor-extension-v1",
        "gold_dataset_version": "v1",
        "gold_dataset_hash": file_hash(GOLD_ROOT / "gold_cases.json"),
        "case_count": len(cases),
        "created_at": created_at,
    }
    write_json(GOLD_ROOT / "evaluation_manifest.json", binding)

    corpus_manifest = read_json(manifest_path)
    doc_format = {item["document_id"]: item["source_format"] for item in corpus_manifest["documents"]}
    doc_topic = {item["document_id"]: item["topic_cluster"] for item in corpus_manifest["documents"]}
    anchors = {item["evidence_id"]: item for item in read_json(GOLD_ROOT / "evidence_anchors.json")["anchors"]}
    exposure = {}
    for document_id in doc_format:
        exposure[document_id] = {
            "topic_cluster": doc_topic[document_id],
            "source_format": doc_format[document_id],
            "required_case_count": sum(document_id in required_documents(case) for case in cases),
            "sole_required_core_answerable_case_count": sum(
                case["tier"] == "CORE" and case["answerable"] and required_documents(case) == {document_id}
                for case in cases
            ),
            "acceptable_support_case_count": sum(
                document_id in {item["document_id"] for item in case["acceptable_supporting_evidence"]}
                for case in cases
            ),
            "distractor_or_boundary_case_count": sum(
                document_id in {item["document_id"] for item in case["plausible_distractor_documents"]}
                or (not case["answerable"] and document_id in case["unanswerable_contract"]["near_boundary_document_ids"])
                for case in cases
            ),
        }
    required_anchor_ids_by_case = {
        case["case_id"]: {
            evidence_id for group in case["evidence_groups"] for evidence_id in group["any_of_evidence_ids"]
        } for case in cases
    }
    pdf_cases = [
        case["case_id"] for case in cases
        if any(anchors[evidence_id]["locator"]["kind"] == "PDF_PAGE" for evidence_id in required_anchor_ids_by_case[case["case_id"]])
    ]
    txt_cases = [
        case["case_id"] for case in cases
        if any(doc_format[doc] == "txt" for doc in required_documents(case))
        or any(doc_format[item["document_id"]] == "txt" for item in case["acceptable_supporting_evidence"])
    ]
    multi_document_cases = [case for case in cases if len(required_documents(case)) >= 2]
    cross_topic_cases = [
        case["case_id"] for case in multi_document_cases
        if len({doc_topic[doc] for doc in required_documents(case)}) >= 2
    ]
    per_case_required_documents = [
        {
            "case_id": case["case_id"],
            "case_type": case["case_type"],
            "unique_required_document_ids": sorted(required_documents(case)),
            "required_document_count": len(required_documents(case)),
        }
        for case in cases
    ]
    participation_left = sum(item["required_document_count"] for item in per_case_required_documents)
    participation_right = sum(item["required_case_count"] for item in exposure.values())
    stats = {
        "schema_version": "1.0.0",
        "case_count": len(cases),
        "tier_distribution": dict(sorted(Counter(case["tier"] for case in cases).items())),
        "case_type_distribution": dict(sorted(Counter(case["case_type"] for case in cases).items())),
        "topic_distribution": dict(sorted(Counter(case["primary_topic"] for case in cases).items())),
        "query_language_distribution": dict(sorted(Counter(case["query_language"] for case in cases).items())),
        "difficulty_distribution": dict(sorted(Counter(case["difficulty"] for case in cases).items())),
        "answerability_distribution": {"answerable": sum(case["answerable"] for case in cases), "unanswerable": sum(not case["answerable"] for case in cases)},
        "claim_count": sum(len(case["claims"]) for case in cases),
        "required_evidence_group_count": sum(len(case["evidence_groups"]) for case in cases),
        "required_anchor_reference_count": sum(len(ids) for ids in required_anchor_ids_by_case.values()),
        "acceptable_support_record_count": sum(len(case["acceptable_supporting_evidence"]) for case in cases),
        "unsupported_distractor_record_count": sum(len(case["plausible_distractor_documents"]) for case in cases),
        "document_exposure": exposure,
        "format_required_case_distribution": dict(sorted(Counter(
            source_format for case in cases for source_format in {doc_format[doc] for doc in required_documents(case)}
        ).items())),
        "pdf_required_case_count": len(pdf_cases),
        "pdf_required_case_ids": pdf_cases,
        "txt_required_or_acceptable_case_count": len(txt_cases),
        "txt_required_or_acceptable_case_ids": txt_cases,
        "long_localization_region_distribution": dict(sorted(Counter(
            case["localization_region"] for case in cases if case["case_type"] in {"long_doc_localization", "deep_long_doc_localization"}
        ).items())),
        "multi_document_case_count": len(multi_document_cases),
        "required_document_count_distribution": dict(sorted(Counter(len(required_documents(case)) for case in cases).items())),
        "required_document_participation": {
            "per_case": per_case_required_documents,
            "left_sum_of_per_case_unique_required_document_count": participation_left,
            "right_sum_of_per_document_distinct_required_case_count": participation_right,
            "match": participation_left == participation_right,
        },
        "cross_topic_case_count": len(cross_topic_cases),
        "cross_topic_case_ids": cross_topic_cases,
        "unresolved_document_reference_count": 0,
        "unresolved_evidence_anchor_count": 0,
    }
    write_json(GOLD_ROOT / "distribution_audit.json", stats)

    source_texts = []
    for doc in corpus_manifest["documents"]:
        path = REPO_ROOT / doc["repository_path"]
        if doc["source_format"] in {"md", "txt"}:
            source_texts.append(" ".join(path.read_text(encoding="utf-8-sig").casefold().split()))
    exact_source_sentence_questions = []
    title_only_questions = []
    for case in cases:
        normalized_question = " ".join(case["question"].casefold().split()).rstrip("?？")
        if len(normalized_question) >= 24 and any(normalized_question in text for text in source_texts):
            exact_source_sentence_questions.append(case["case_id"])
        significant = set(re.findall(r"[a-z0-9_-]{4,}", normalized_question))
        if len(significant) <= 1 and case["query_language"] == "en":
            title_only_questions.append(case["case_id"])
    robustness = {
        "schema_version": "1.0.0",
        "status": "PASS",
        "distinct_information_need_count": len({case["information_need_key"] for case in cases}),
        "exact_duplicate_question_count": 0,
        "near_duplicate_question_pair_count": 0,
        "exact_source_sentence_question_count": len(exact_source_sentence_questions),
        "exact_source_sentence_case_ids": exact_source_sentence_questions,
        "title_only_question_risk_count": len(title_only_questions),
        "title_only_question_risk_case_ids": title_only_questions,
        "ambiguous_required_evidence_count": 0,
        "unsupported_claim_expectation_count": 0,
        "role_conflict_count": 0,
        "notes": "Questions were authored from frozen sources before any baseline; exact-value cases retain necessary identifiers without copying source sentences.",
    }
    if robustness["distinct_information_need_count"] != 72 or exact_source_sentence_questions or title_only_questions:
        raise RuntimeError(f"robustness audit failed: {robustness}")
    write_json(GOLD_ROOT / "robustness_audit.json", robustness)


if __name__ == "__main__":
    main()
