"""Validate all file-backed shards, then merge deterministically for review."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256

from gold_common import (
    CORE_TYPES, DRAFT_ROOT, GOLD_ROOT, STRESS_TYPES, TYPE_ORDER, canonical_hash,
    load_anchor_specs, load_manifest, read_json, validate_shard, write_json,
)


def main() -> None:
    manifest = load_manifest()
    specs = load_anchor_specs()
    cases = []
    shard_results = []
    for case_type in TYPE_ORDER:
        shard = read_json(DRAFT_ROOT / f"{case_type}.json")
        expected_count = CORE_TYPES.get(case_type, STRESS_TYPES.get(case_type))
        expected_tier = "CORE" if case_type in CORE_TYPES else "STRESS"
        errors = validate_shard(
            shard, manifest, specs, expected_type=case_type,
            expected_count=expected_count, expected_tier=expected_tier,
        )
        if errors:
            raise RuntimeError("\n".join(errors))
        ordered_cases = sorted(shard["cases"], key=lambda item: item["case_id"])
        cases.extend(ordered_cases)
        shard_results.append({"case_type": case_type, "case_count": len(ordered_cases), "status": "PASS"})
    case_ids = [item["case_id"] for item in cases]
    claim_ids = [claim["claim_id"] for item in cases for claim in item["claims"]]
    questions = [" ".join(item["question"].casefold().split()) for item in cases]
    if len(cases) != 72 or len(case_ids) != len(set(case_ids)):
        raise ValueError("merged draft must contain 72 unique case IDs")
    if len(claim_ids) != len(set(claim_ids)):
        raise ValueError("merged draft contains duplicate claim IDs")
    if len(questions) != len(set(questions)):
        raise ValueError("merged draft contains duplicate questions")
    tier_counts = Counter(item["tier"] for item in cases)
    type_counts = Counter(item["case_type"] for item in cases)
    if tier_counts != Counter({"CORE": 60, "STRESS": 12}):
        raise ValueError(f"wrong tier distribution: {tier_counts}")
    expected_types = Counter(CORE_TYPES) + Counter(STRESS_TYPES)
    if type_counts != expected_types:
        raise ValueError(f"wrong case-type distribution: {type_counts}")
    artifact = {
        "schema_version": "1.0.0",
        "contract_ref": "learnpilot-rag-eval-gold-contract-v2",
        "dataset_id": "learnpilot-rag-real-world-gold",
        "dataset_version": "v1",
        "draft_status": "PENDING_INDEPENDENT_REVIEW",
        "corpus_ref": {"corpus_id": manifest["corpus_id"], "corpus_version": manifest["corpus_version"]},
        "case_count": len(cases),
        "cases": cases,
    }
    write_json(GOLD_ROOT / "merged_draft.json", artifact)
    file_hash = sha256((GOLD_ROOT / "merged_draft.json").read_bytes()).hexdigest()
    (GOLD_ROOT / "merged_draft.sha256").write_text(file_hash + "\n", encoding="ascii")
    write_json(GOLD_ROOT / "pre_review_merge_validation.json", {
        "schema_version": "1.0.0",
        "status": "PASS",
        "shards": shard_results,
        "case_count": len(cases),
        "tier_distribution": dict(sorted(tier_counts.items())),
        "case_type_distribution": dict(sorted(type_counts.items())),
        "merged_draft_file_sha256": file_hash,
        "merged_draft_canonical_sha256": canonical_hash(artifact),
        "duplicate_case_id_count": 0,
        "duplicate_claim_id_count": 0,
        "duplicate_question_count": 0,
    })


if __name__ == "__main__":
    main()
