"""Create and verify the immutable LearnPilot Real-world Gold Dataset V1 freeze.

This is evaluation-only, local, deterministic tooling.  It reads frozen project
artifacts and source bytes; it never authors Gold, calls a model, runs retrieval,
or executes a baseline.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from pypdf import PdfReader

from gold_common import GOLD_ROOT, REPO_ROOT, canonical_hash, json_schema_errors, read_json, write_json
from gold_correctness_repair_v1 import (
    AFFECTED_CASE_IDS,
    FROZEN_REVIEW_SHA256,
    REPAIRED_CLAIM_IDS,
    current_claim_payload,
    minimum_hitting_set,
    prior_claim_payload,
    reopen_anchor,
    required_documents,
    semantic_payload,
)
from forensic_audit import near_duplicate, normalize
from validate_gold import validate_artifacts


EXPECTED_GOLD_SHA256 = "33a0b69901fa47e3fe45be0277228cd4a5519fe780fe5b9d2c52b1bfe614927a"
EXPECTED_REPAIR_BASELINE_SHA256 = "88813adad104a129a7c868cb7b7d43550c71b88d48695270a3e92cefa1f5b461"
CORPUS_ROOT = REPO_ROOT / "evals" / "rag_real_world_corpus" / "v1"
GOLD_PATH = GOLD_ROOT / "gold_cases.json"
ANCHORS_PATH = GOLD_ROOT / "evidence_anchors.json"
SCHEMA_PATH = GOLD_ROOT / "gold_dataset_v1_freeze_manifest.schema.json"
FREEZE_PATH = GOLD_ROOT / "gold_dataset_v1_freeze_manifest.json"
FREEZE_HASH_PATH = GOLD_ROOT / "gold_dataset_v1_freeze_manifest.sha256"
BINDING_PATH = GOLD_ROOT / "BASELINE_BINDING.md"

EXPECTED_CASE_TYPES = {
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
EXPECTED_MODES = {
    "SEMANTIC_REVIEW": 104,
    "ANSWERABILITY_ONLY": 10,
    "NUMERIC_EXACT": 7,
    "STRUCTURED_EXACT": 6,
    "IDENTIFIER_EXACT": 5,
}
RUNTIME_ID_PATTERN = re.compile(
    r"(?i)(material[._-]?id|materialchunk[._-]?id|chunk[._-]?id|"
    r"faiss\s+(?:runtime\s+)?(?:index\s+)?position|\bS[12][-_][A-Za-z0-9]+)"
)


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def expect(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def normalized_hash_map(values: dict[str, str]) -> str:
    return canonical_hash(dict(sorted(values.items())))


def source_text(document: dict[str, Any]) -> str:
    path = REPO_ROOT / document["repository_path"]
    if document["source_format"] in {"md", "txt"}:
        return normalize(path.read_text(encoding="utf-8-sig")).casefold()
    reader = PdfReader(str(path))
    return normalize("\n".join(page.extract_text() or "" for page in reader.pages)).casefold()


def protected_scope_audit(errors: list[str]) -> dict[str, Any]:
    baseline = read_json(GOLD_ROOT / "immutability_baseline.json")
    result: dict[str, Any] = {}
    for scope in ("frozen_real_world_corpus", "controlled_corpus_v2", "production_rag"):
        expected_map = baseline[scope]
        actual_map = {
            path: file_hash(REPO_ROOT / path) if (REPO_ROOT / path).is_file() else "MISSING"
            for path in expected_map
        }
        mismatches = sorted(path for path in expected_map if actual_map[path] != expected_map[path])
        expect(not mismatches, f"protected scope changed: {scope}: {mismatches}", errors)
        result[scope] = {
            "monitored_file_count": len(expected_map),
            "mismatch_count": len(mismatches),
            "expected_hash_map_sha256": normalized_hash_map(expected_map),
            "actual_hash_map_sha256": normalized_hash_map(actual_map),
        }
    return result


def collect_manifest(frozen_at: str) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    gold_hash = file_hash(GOLD_PATH)
    expect(gold_hash == EXPECTED_GOLD_SHA256, "canonical Gold SHA-256 drift", errors)

    gold = read_json(GOLD_PATH)
    cases = gold["cases"]
    case_ids = [case["case_id"] for case in cases]
    claim_ids = [claim["claim_id"] for case in cases for claim in case["claims"]]
    information_need_keys = [case["information_need_key"] for case in cases]
    questions = [normalize(case["question"]).casefold() for case in cases]
    tier_distribution = dict(sorted(Counter(case["tier"] for case in cases).items()))
    case_type_distribution = dict(sorted(Counter(case["case_type"] for case in cases).items()))
    mode_distribution = dict(sorted(Counter(
        claim["evaluation_mode"] for case in cases for claim in case["claims"]
    ).items()))
    expect(len(cases) == 72, "case count is not 72", errors)
    expect(len(claim_ids) == 132, "claim count is not 132", errors)
    expect(tier_distribution == {"CORE": 60, "STRESS": 12}, "tier distribution drift", errors)
    expect(case_type_distribution == dict(sorted(EXPECTED_CASE_TYPES.items())), "case type distribution drift", errors)
    expect(mode_distribution == dict(sorted(EXPECTED_MODES.items())), "evaluation mode distribution drift", errors)
    expect(len(set(case_ids)) == 72, "case IDs are not 72/72 unique", errors)
    expect(len(set(claim_ids)) == 132, "claim IDs are not 132/132 unique", errors)
    expect(len(set(information_need_keys)) == 72, "information_need_key is not 72/72 unique", errors)

    corpus_manifest_path = CORPUS_ROOT / "corpus_manifest.json"
    corpus_manifest = read_json(corpus_manifest_path)
    documents = {item["document_id"]: item for item in corpus_manifest["documents"]}
    document_hashes = []
    for document_id, document in sorted(documents.items()):
        path = REPO_ROOT / document["repository_path"]
        actual = file_hash(path) if path.is_file() else "MISSING"
        matches = actual == document["corpus_sha256"]
        expect(matches, f"corpus source byte mismatch: {document_id}", errors)
        document_hashes.append({
            "document_id": document_id,
            "repository_path": document["repository_path"],
            "expected_sha256": document["corpus_sha256"],
            "actual_sha256": actual,
            "match": matches,
        })
    projection = read_json(CORPUS_ROOT / "chunk_projection.json")
    ingestion_result = read_json(
        CORPUS_ROOT / "results" / "ingestion_v1" / "20260813T131304Z-ac0a8cee" / "result.json"
    )
    expect(corpus_manifest["document_count"] == len(documents) == 11, "corpus document count drift", errors)
    expect(projection["total_projected_chunks"] == 442, "projected corpus chunk count drift", errors)
    expect(ingestion_result["chunk_count"] == 442, "installed corpus chunk count drift", errors)

    anchors_artifact = read_json(ANCHORS_PATH)
    anchors = {item["evidence_id"]: item for item in anchors_artifact["anchors"]}
    anchor_records = []
    anchor_runtime_leaks = []
    for evidence_id, anchor in sorted(anchors.items()):
        try:
            reopened = reopen_anchor(anchor, documents[anchor["document_id"]])
            status = "PASS"
        except (KeyError, RuntimeError, ValueError) as exc:
            reopened = {
                "locator_resolved": False,
                "source_hash_matches_manifest": False,
                "anchor_hash_matches": False,
                "error": str(exc),
            }
            status = "FAIL"
            errors.append(f"anchor failed: {evidence_id}: {exc}")
        if RUNTIME_ID_PATTERN.search(json.dumps(anchor, ensure_ascii=False)):
            anchor_runtime_leaks.append(evidence_id)
        anchor_records.append({
            "evidence_id": evidence_id,
            "document_id": anchor["document_id"],
            "locator_kind": anchor["locator"]["kind"],
            "document_resolved": anchor["document_id"] in documents,
            "locator_resolved": reopened["locator_resolved"],
            "source_hash_matches_manifest": reopened["source_hash_matches_manifest"],
            "anchor_hash_matches": reopened["anchor_hash_matches"],
            "status": status,
        })
    locator_distribution = dict(sorted(Counter(item["locator_kind"] for item in anchor_records).items()))
    expect(len(anchors) == anchors_artifact["anchor_count"] == 89, "anchor count drift", errors)
    expect(locator_distribution == {"PDF_PAGE": 24, "SOURCE_LINES": 65}, "anchor locator distribution drift", errors)
    expect(not anchor_runtime_leaks, f"runtime ID leaked into anchors: {anchor_runtime_leaks}", errors)

    baseline_path = GOLD_ROOT / "gold_correctness_repair_v1_baseline.json"
    change_log_path = GOLD_ROOT / "gold_correctness_repair_v1.json"
    post_review_path = GOLD_ROOT / "post_repair_semantic_verification_v1.json"
    repair_audit_path = GOLD_ROOT / "gold_correctness_repair_v1_audit.json"
    frozen_review_path = GOLD_ROOT / "independent_semantic_verification_v1.json"
    expect(file_hash(baseline_path) == EXPECTED_REPAIR_BASELINE_SHA256, "repair baseline hash drift", errors)
    expect(file_hash(frozen_review_path) == FROZEN_REVIEW_SHA256, "pre-repair semantic review hash drift", errors)
    baseline = read_json(baseline_path)
    frozen_review = read_json(frozen_review_path)
    change_log = read_json(change_log_path)
    post_review = read_json(post_review_path)
    repair_audit = read_json(repair_audit_path)

    current_case_hashes = {
        case["case_id"]: canonical_hash(semantic_payload(case)) for case in cases
    }
    changed_case_ids = sorted(
        case_id for case_id, digest in current_case_hashes.items()
        if digest != baseline["case_semantic_payload_sha256"][case_id]
    )
    unaffected_case_ids = sorted(set(case_ids) - set(AFFECTED_CASE_IDS))
    unaffected_unchanged = sum(
        current_case_hashes[case_id] == baseline["case_semantic_payload_sha256"][case_id]
        for case_id in unaffected_case_ids
    )
    expect(changed_case_ids == sorted(AFFECTED_CASE_IDS), "changed case set differs from frozen eight", errors)
    expect(len(unaffected_case_ids) == unaffected_unchanged == 64, "64-case semantic preservation failed", errors)

    current_semantic_claims = {
        claim["claim_id"]: (case, claim)
        for case in cases for claim in case["claims"]
        if claim["evaluation_mode"] == "SEMANTIC_REVIEW"
    }
    previously_supported_reviews = [
        item for item in frozen_review["semantic_claim_reviews"]
        if item["claim_verdict"] == "SUPPORTED"
    ]
    previously_supported_unchanged = 0
    for review in previously_supported_reviews:
        case, claim = current_semantic_claims[review["claim_id"]]
        previously_supported_unchanged += (
            prior_claim_payload(review) == current_claim_payload(case, claim, anchors)
        )
    expect(
        len(previously_supported_reviews) == previously_supported_unchanged == 96,
        "96 previously-supported semantic claim payloads were not preserved",
        errors,
    )
    fresh_claim_reviews = post_review["claim_reviews"]
    repaired_supported = sum(item["claim_verdict"] == "SUPPORTED" for item in fresh_claim_reviews)
    expect(
        sorted(item["claim_id"] for item in fresh_claim_reviews) == sorted(REPAIRED_CLAIM_IDS),
        "fresh repair review claim set differs from frozen eight",
        errors,
    )
    expect(repaired_supported == len(fresh_claim_reviews) == 8, "8/8 repaired claims are not SUPPORTED", errors)
    expected_semantic_verdicts = {
        "SUPPORTED": 104,
        "PARTIALLY_SUPPORTED": 0,
        "UNSUPPORTED": 0,
        "AMBIGUOUS": 0,
    }
    semantic_closure = post_review["final_semantic_closure"]
    expect(semantic_closure["verdict_distribution"] == expected_semantic_verdicts, "semantic closure drift", errors)
    expect(change_log["repairs"] == 9 and change_log["affected_cases"] == 8, "repair ledger is not 9/8", errors)
    expect(change_log["post_repair_gold_sha256"] == gold_hash, "repair ledger Gold binding drift", errors)
    expect(repair_audit["status"] == "PASS", "repair audit does not pass", errors)
    expect(repair_audit["scope_proof"]["unaffected_case_payloads_unchanged"] == 64, "repair audit 64-case proof drift", errors)
    expect(repair_audit["scope_proof"]["previously_supported_semantic_claims_unchanged"] == 96, "repair audit 96-claim proof drift", errors)

    required_doc_sets = {case["case_id"]: required_documents(case) for case in cases}
    participation_left = sum(len(value) for value in required_doc_sets.values())
    per_document = defaultdict(int)
    for document_ids in required_doc_sets.values():
        for document_id in document_ids:
            per_document[document_id] += 1
    participation_right = sum(per_document.values())
    candidate_distribution = {
        str(key): value for key, value in sorted(Counter(len(value) for value in required_doc_sets.values()).items())
    }
    hitting_distribution = {
        str(key): value for key, value in sorted(Counter(
            minimum_hitting_set(case["evidence_groups"]) for case in cases
        ).items())
    }
    multi_document_cases = sum(len(value) >= 2 for value in required_doc_sets.values())
    expect(participation_left == participation_right == 86, "required-document participation drift", errors)
    expect(candidate_distribution == {"0": 10, "1": 41, "2": 18, "3": 3}, "candidate required-document distribution drift", errors)
    expect(hitting_distribution == {"0": 10, "1": 41, "2": 18, "3": 3}, "minimum hitting-set distribution drift", errors)
    expect(multi_document_cases == 21, "candidate multi-document case count drift", errors)

    acceptable_count = sum(len(case["acceptable_supporting_evidence"]) for case in cases)
    unsupported_count = sum(len(case["plausible_distractor_documents"]) for case in cases)
    role_case_count = sum(
        case["case_type"] in {"source_disambiguation", "high_overlap_source_conflict"}
        for case in cases
    )
    role_overlap_case_ids = []
    for case in cases:
        required = required_documents(case)
        acceptable = {item["document_id"] for item in case["acceptable_supporting_evidence"]}
        unsupported = {item["document_id"] for item in case["plausible_distractor_documents"]}
        if required & acceptable or required & unsupported or acceptable & unsupported:
            role_overlap_case_ids.append(case["case_id"])
    role_closure = post_review["evidence_role_closure"]
    expect(acceptable_count == 11 and unsupported_count == 25, "evidence role counts drift", errors)
    expect(role_case_count == role_closure["target_case_count"] == 14, "role closure case count drift", errors)
    expect(role_closure["misclassified_count"] == 0 and not role_overlap_case_ids, "evidence role misclassification remains", errors)

    unanswerable_cases = [case for case in cases if case["case_type"] == "unanswerable_near_boundary"]
    unanswerable_violations = []
    for case in unanswerable_cases:
        citation = case["citation_contract"]
        boundary = case.get("unanswerable_contract", {})
        unsupported_docs = {item["document_id"] for item in case["plausible_distractor_documents"]}
        if not (
            case["answerable"] is False
            and case["evidence_groups"] == []
            and citation["citation_required"] is False
            and citation["forbid_citations"] is True
            and set(boundary.get("near_boundary_document_ids", [])) <= unsupported_docs
            and set(boundary.get("near_boundary_evidence_ids", [])) <= set(anchors)
        ):
            unanswerable_violations.append(case["case_id"])
    expect(len(unanswerable_cases) == 10 and not unanswerable_violations, "answerability closure drift", errors)

    near_pairs = []
    for index, left in enumerate(cases):
        for right in cases[index + 1:]:
            if near_duplicate(left["question"], right["question"]):
                near_pairs.append([left["case_id"], right["case_id"]])
    source_texts = [source_text(document) for document in documents.values()]
    exact_source_sentence_case_ids = []
    for case in cases:
        normalized_question = normalize(case["question"]).casefold().rstrip("?？")
        if len(normalized_question) >= 24 and any(normalized_question in text for text in source_texts):
            exact_source_sentence_case_ids.append(case["case_id"])
    runtime_leakage_case_ids = [
        case["case_id"] for case in cases
        if RUNTIME_ID_PATTERN.search(json.dumps(case, ensure_ascii=False))
    ]
    baseline_output_files = sorted(
        relative(path) for path in (CORPUS_ROOT / "results").rglob("*")
        if path.is_file() and "baseline" in path.name.casefold()
    )
    expect(len(questions) == len(set(questions)), "exact duplicate question detected", errors)
    expect(not near_pairs, f"near duplicate question pairs detected: {near_pairs}", errors)
    expect(not exact_source_sentence_case_ids, "exact source-sentence question leakage detected", errors)
    expect(not runtime_leakage_case_ids, "runtime ID leakage detected in Gold", errors)
    expect(not baseline_output_files, "Real-world baseline outputs exist before freeze", errors)

    protected_scopes = protected_scope_audit(errors)
    evaluation_manifest_path = GOLD_ROOT / "evaluation_manifest.json"
    evaluation_manifest = read_json(evaluation_manifest_path)
    corpus_manifest_hash = file_hash(corpus_manifest_path)
    evaluation_binding_pass = (
        evaluation_manifest["corpus_id"] == corpus_manifest["corpus_id"]
        and evaluation_manifest["corpus_version"] == corpus_manifest["corpus_version"]
        and evaluation_manifest["corpus_manifest_hash"] == corpus_manifest_hash
        and evaluation_manifest["gold_dataset_hash"] == gold_hash
        and evaluation_manifest["case_count"] == len(cases)
    )
    expect(evaluation_binding_pass, "evaluation manifest binding drift", errors)

    validator = validate_artifacts()
    expect(validator["status"] == "PASS", f"validate_gold failed: {validator['errors']}", errors)
    expect(validator["v2_helper_compatibility"] == "PASS", "Controlled V2 helper compatibility failed", errors)

    execution_audit = read_json(GOLD_ROOT / "task_execution_audit.json")
    execution_counts = {
        "deepseek_calls": post_review["execution_audit"]["deepseek_calls"],
        "other_llm_calls": post_review["execution_audit"]["other_llm_calls"],
        "production_rag_ask_calls": post_review["execution_audit"]["production_rag_ask_calls"],
        "real_world_baseline_executions": execution_audit["rag_baseline_execution_count"],
        "embedding_executions": post_review["execution_audit"]["embedding_executions"],
        "faiss_retrieval_executions": post_review["execution_audit"]["faiss_retrieval_executions"],
    }
    expect(all(value == 0 for value in execution_counts.values()), "prohibited execution recorded", errors)

    manifest = {
        "schema_version": "1.0.0",
        "manifest_version": "gold-dataset-v1-final-freeze",
        "manifest_schema": {
            "path": relative(SCHEMA_PATH),
            "sha256": file_hash(SCHEMA_PATH),
        },
        "dataset_id": "learnpilot-rag-real-world-gold-v1",
        "dataset_version": "v1",
        "status": "FROZEN" if not errors else "HOLD",
        "frozen_at": frozen_at,
        "freeze_protocol": ["VERIFY", "FREEZE", "BIND", "REPORT"],
        "gold": {
            "source_dataset_id": gold["dataset_id"],
            "path": relative(GOLD_PATH),
            "sha256": gold_hash,
            "case_count": len(cases),
            "claim_count": len(claim_ids),
            "core_case_count": tier_distribution.get("CORE", 0),
            "stress_case_count": tier_distribution.get("STRESS", 0),
            "case_type_distribution": case_type_distribution,
            "case_id_unique_count": len(set(case_ids)),
            "claim_id_unique_count": len(set(claim_ids)),
            "information_need_key_unique_count": len(set(information_need_keys)),
            "semantic_payload_changes_during_final_freeze": 0 if gold_hash == EXPECTED_GOLD_SHA256 else 1,
        },
        "corpus": {
            "dataset_id": f"{corpus_manifest['corpus_id']}@{corpus_manifest['corpus_version']}",
            "manifest_path": relative(corpus_manifest_path),
            "manifest_sha256": corpus_manifest_hash,
            "identity_sha256": corpus_manifest_hash,
            "document_count": len(documents),
            "projected_chunk_count": projection["total_projected_chunks"],
            "installed_chunk_count": ingestion_result["chunk_count"],
            "source_document_hash_pass_count": sum(item["match"] for item in document_hashes),
            "document_hashes": document_hashes,
        },
        "evidence_anchor_audit": {
            "artifact_path": relative(ANCHORS_PATH),
            "artifact_sha256": file_hash(ANCHORS_PATH),
            "anchor_count": len(anchors),
            "locator_kind_distribution": locator_distribution,
            "document_resolution_pass": sum(item["document_resolved"] for item in anchor_records),
            "locator_resolution_pass": sum(item["locator_resolved"] for item in anchor_records),
            "anchor_hash_pass": sum(item["anchor_hash_matches"] for item in anchor_records),
            "runtime_id_leakage": len(anchor_runtime_leaks),
        },
        "semantic_closure": {
            "semantic_review_claims": 104,
            "supported": expected_semantic_verdicts["SUPPORTED"],
            "partially_supported": expected_semantic_verdicts["PARTIALLY_SUPPORTED"],
            "unsupported": expected_semantic_verdicts["UNSUPPORTED"],
            "ambiguous": expected_semantic_verdicts["AMBIGUOUS"],
            "previously_supported_unchanged": previously_supported_unchanged,
            "repaired_fresh_reviewed_supported": repaired_supported,
        },
        "repair_closure": {
            "defects": change_log["repairs"],
            "affected_cases": change_log["affected_cases"],
            "affected_case_ids": sorted(AFFECTED_CASE_IDS),
            "status": change_log["status"],
        },
        "unaffected_preservation": {
            "case_count": len(unaffected_case_ids),
            "semantic_payload_unchanged": unaffected_unchanged,
            "status": "PASS" if unaffected_unchanged == 64 else "FAIL",
        },
        "contract_compatibility": {
            "evidence_roles": ["REQUIRED", "ACCEPTABLE_SUPPORT", "UNSUPPORTED"],
            "or_inside_evidence_group": True,
            "and_across_evidence_groups": True,
            "evaluation_mode_distribution": mode_distribution,
            "controlled_v2_artifacts_modified": False,
            "controlled_v2_helper_compatibility": validator["v2_helper_compatibility"],
        },
        "answerability_audit": {
            "unanswerable_near_boundary_count": len(unanswerable_cases),
            "valid_count": len(unanswerable_cases) - len(unanswerable_violations),
            "violation_count": len(unanswerable_violations),
        },
        "evidence_role_audit": {
            "acceptable_support_count": acceptable_count,
            "unsupported_count": unsupported_count,
            "target_case_count": role_case_count,
            "misclassified_count": role_closure["misclassified_count"] + len(role_overlap_case_ids),
        },
        "required_document_invariants": {
            "participation_left": participation_left,
            "participation_right": participation_right,
            "match": participation_left == participation_right,
            "candidate_required_document_count_distribution": candidate_distribution,
            "minimum_hitting_set_distribution": hitting_distribution,
            "candidate_multi_document_case_count": multi_document_cases,
        },
        "duplicate_and_leakage_audit": {
            "information_need_key_unique_count": len(set(information_need_keys)),
            "exact_duplicate_question_count": len(questions) - len(set(questions)),
            "near_duplicate_question_pair_count": len(near_pairs),
            "exact_source_sentence_question_count": len(exact_source_sentence_case_ids),
            "runtime_id_leakage_count": len(runtime_leakage_case_ids) + len(anchor_runtime_leaks),
            "baseline_answer_leakage_count": len(baseline_output_files),
            "real_world_baseline_output_file_count": len(baseline_output_files),
        },
        "protected_scopes": protected_scopes,
        "evaluation_manifest_binding": {
            "path": relative(evaluation_manifest_path),
            "sha256": file_hash(evaluation_manifest_path),
            "corpus_manifest_sha256": evaluation_manifest["corpus_manifest_hash"],
            "gold_sha256": evaluation_manifest["gold_dataset_hash"],
            "case_count": evaluation_manifest["case_count"],
            "status": "PASS" if evaluation_binding_pass else "FAIL",
        },
        "artifact_bindings": {
            "pre_repair_semantic_review": {"path": relative(frozen_review_path), "sha256": file_hash(frozen_review_path)},
            "repair_baseline": {"path": relative(baseline_path), "sha256": file_hash(baseline_path)},
            "repair_change_log": {"path": relative(change_log_path), "sha256": file_hash(change_log_path)},
            "post_repair_semantic_verification": {"path": relative(post_review_path), "sha256": file_hash(post_review_path)},
            "repair_audit": {"path": relative(repair_audit_path), "sha256": file_hash(repair_audit_path)},
        },
        "no_execution_audit": {
            **execution_counts,
            "baseline_executed_before_freeze": False,
        },
        "baseline_binding_contract": {
            "path": relative(BINDING_PATH),
            "required_identity_fields": [
                "corpus identity/hash",
                "Gold identity/hash",
                "freeze manifest hash",
                "production RAG code/config identity",
                "embedding model",
                "retrieval configuration",
                "generation model",
                "evaluation timestamp",
            ],
            "same_benchmark_rule": "A changed Gold SHA-256 or corpus manifest SHA-256 is not the same frozen V1 benchmark.",
        },
        "freeze_policy": {
            "benchmark_state": "RAG_REAL_WORLD_GOLD_DATASET_V1 = FROZEN",
            "semantic_modification_rule": "Any semantic modification after this point requires a new benchmark version.",
            "next_version_example": "v2",
            "silent_v1_mutation_forbidden": True,
            "ready_for_dense_only_baseline": not errors,
        },
    }
    return manifest, errors


def validate_manifest_schema(manifest: dict[str, Any]) -> list[str]:
    return json_schema_errors(manifest, read_json(SCHEMA_PATH))


def build() -> dict[str, Any]:
    if FREEZE_PATH.exists() or FREEZE_HASH_PATH.exists():
        raise RuntimeError("freeze artifacts already exist; refusing to overwrite frozen V1")
    frozen_at = datetime.now(timezone.utc).isoformat()
    manifest, errors = collect_manifest(frozen_at)
    errors.extend(validate_manifest_schema(manifest))
    if errors:
        raise RuntimeError("FINAL_FREEZE=HOLD: " + "; ".join(errors))
    write_json(FREEZE_PATH, manifest)
    digest = file_hash(FREEZE_PATH)
    FREEZE_HASH_PATH.write_text(f"{digest}  {FREEZE_PATH.name}\n", encoding="utf-8")
    return {
        "status": "FROZEN",
        "canonical_gold_sha256": manifest["gold"]["sha256"],
        "freeze_manifest_sha256": digest,
        "case_count": manifest["gold"]["case_count"],
        "claim_count": manifest["gold"]["claim_count"],
        "anchor_count": manifest["evidence_anchor_audit"]["anchor_count"],
        "semantic_supported": manifest["semantic_closure"]["supported"],
        "baseline_executed": manifest["no_execution_audit"]["baseline_executed_before_freeze"],
    }


def verify() -> dict[str, Any]:
    if not FREEZE_PATH.is_file() or not FREEZE_HASH_PATH.is_file():
        raise RuntimeError("freeze manifest or its SHA-256 artifact is missing")
    frozen = read_json(FREEZE_PATH)
    current, errors = collect_manifest(frozen["frozen_at"])
    errors.extend(validate_manifest_schema(frozen))
    if current != frozen:
        errors.append("freeze manifest does not match current frozen inputs")
    recorded_hash = FREEZE_HASH_PATH.read_text(encoding="utf-8-sig").split()[0]
    actual_hash = file_hash(FREEZE_PATH)
    if recorded_hash != actual_hash:
        errors.append("freeze manifest self-hash mismatch")
    if not BINDING_PATH.is_file():
        errors.append("baseline binding contract is missing")
    else:
        binding = BINDING_PATH.read_text(encoding="utf-8-sig")
        for identity in (EXPECTED_GOLD_SHA256, actual_hash):
            if identity not in binding:
                errors.append(f"baseline binding contract omits identity: {identity}")
    if errors:
        raise RuntimeError("FINAL_FREEZE=HOLD: " + "; ".join(errors))
    return {
        "status": "PASS",
        "dataset_status": frozen["status"],
        "canonical_gold_sha256": frozen["gold"]["sha256"],
        "freeze_manifest_sha256": actual_hash,
        "semantic_closure": f"{frozen['semantic_closure']['supported']} / {frozen['semantic_closure']['semantic_review_claims']} SUPPORTED",
        "ready_for_dense_only_baseline": frozen["freeze_policy"]["ready_for_dense_only_baseline"],
        "baseline_executed": frozen["no_execution_audit"]["baseline_executed_before_freeze"],
    }


def preflight() -> dict[str, Any]:
    manifest, errors = collect_manifest("PENDING_FINAL_FREEZE")
    return {
        "status": "PASS" if not errors else "HOLD",
        "expected_gold_sha256": EXPECTED_GOLD_SHA256,
        "actual_gold_sha256": manifest["gold"]["sha256"],
        "match": manifest["gold"]["sha256"] == EXPECTED_GOLD_SHA256,
        "case_count": manifest["gold"]["case_count"],
        "claim_count": manifest["gold"]["claim_count"],
        "anchor_count": manifest["evidence_anchor_audit"]["anchor_count"],
        "semantic_supported": manifest["semantic_closure"]["supported"],
        "unaffected_unchanged": manifest["unaffected_preservation"]["semantic_payload_unchanged"],
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("preflight", "build", "verify"))
    args = parser.parse_args()
    result = {"preflight": preflight, "build": build, "verify": verify}[args.command]()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] not in {"PASS", "FROZEN"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
