"""Freeze the human semantic-claim review before downstream failure analysis."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from semantic_review_decisions import ALLOWED_VERDICTS, SEMANTIC_DECISIONS


ROOT = Path(__file__).resolve().parents[4]
V1 = ROOT / "evals" / "rag_real_world_corpus" / "v1"
OUT = V1 / "failure_analysis_v1"
RUN = V1 / "results" / "dense_only_baseline_v1" / "20260814T052007Z-593cd2ac"
QUEUE = RUN / "semantic_review_queue.json"
RAW = RUN / "raw_results.json"
RAW_HASH_FILE = RUN / "raw_results.sha256"

EXPECTED_RAW_SHA256 = "bf718aed08e226149c9310cbf20bf25c403708217e2908789120178ac5574e28"
EXPECTED_CLAIMS = 104
EXPECTED_CASES = 54


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def build_schema() -> dict[str, object]:
    verdicts = sorted(ALLOWED_VERDICTS)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "learnpilot://rag-real-world/failure-analysis-v1/semantic-claim-reviews.schema.json",
        "title": "LearnPilot Real-world Baseline Semantic Claim Reviews V1",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "review_id", "provenance", "methodology", "summary", "case_reviews"],
        "properties": {
            "schema_version": {"const": "1.0.0"},
            "review_id": {"const": "learnpilot-rag-real-world-semantic-claim-reviews-v1"},
            "provenance": {"type": "object"},
            "methodology": {"type": "object"},
            "summary": {"type": "object"},
            "case_reviews": {
                "type": "array",
                "minItems": EXPECTED_CASES,
                "maxItems": EXPECTED_CASES,
                "items": {
                    "type": "object",
                    "required": [
                        "case_id", "case_run_id", "question", "case_metadata", "expected_answerable",
                        "model_answerable", "normalized_answer", "selected_context",
                        "citations", "claim_reviews",
                    ],
                    "properties": {
                        "case_id": {"type": "string"},
                        "case_run_id": {"type": "string"},
                        "question": {"type": "string"},
                        "case_metadata": {"type": "object"},
                        "expected_answerable": {"type": "boolean"},
                        "model_answerable": {"type": "boolean"},
                        "normalized_answer": {"type": "string"},
                        "selected_context": {"type": "array"},
                        "citations": {"type": "array"},
                        "claim_reviews": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "case_id", "claim_id", "case_type", "tier", "topic",
                                    "difficulty", "query_language", "question", "gold_claim",
                                    "machine_answer", "selected_context_summary", "citations",
                                    "required", "evaluation_mode", "evidence_group_ids",
                                    "verdict", "review_reason", "reviewer_mode",
                                ],
                                "properties": {
                                    "case_id": {"type": "string"},
                                    "claim_id": {"type": "string"},
                                    "case_type": {"type": "string"},
                                    "tier": {"type": "string"},
                                    "topic": {"type": "string"},
                                    "difficulty": {"type": "string"},
                                    "query_language": {"type": "string"},
                                    "question": {"type": "string"},
                                    "gold_claim": {"type": "string"},
                                    "machine_answer": {"type": "string"},
                                    "selected_context_summary": {"type": "array"},
                                    "citations": {"type": "array"},
                                    "required": {"type": "boolean"},
                                    "evaluation_mode": {"const": "SEMANTIC_REVIEW"},
                                    "evidence_group_ids": {"type": "array", "items": {"type": "string"}},
                                    "verdict": {"enum": verdicts},
                                    "review_reason": {"type": "string", "minLength": 20},
                                    "reviewer_mode": {"const": "HUMAN_EVIDENCE_REVIEW"},
                                },
                            },
                        },
                    },
                },
            },
        },
    }


def main() -> None:
    output_path = OUT / "semantic_claim_reviews.json"
    hash_path = OUT / "semantic_claim_reviews.sha256"
    if output_path.exists() or hash_path.exists():
        raise SystemExit("Refusing to overwrite an existing frozen semantic review or detached hash.")

    raw_hash = sha256(RAW)
    if raw_hash != EXPECTED_RAW_SHA256:
        raise SystemExit(f"Raw baseline hash mismatch: {raw_hash}")
    detached_raw = RAW_HASH_FILE.read_text(encoding="utf-8").strip().split()[0]
    if detached_raw != EXPECTED_RAW_SHA256:
        raise SystemExit(f"Detached raw baseline hash mismatch: {detached_raw}")

    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    raw_cases = {case["case_id"]: case for case in raw["cases"]}
    if queue.get("semantic_claim_count") != EXPECTED_CLAIMS or queue.get("case_count") != EXPECTED_CASES:
        raise SystemExit("Semantic review queue cardinality does not match the frozen contract.")

    queue_ids = [claim["claim_id"] for item in queue["items"] for claim in item["semantic_claims"]]
    if len(queue_ids) != EXPECTED_CLAIMS or len(set(queue_ids)) != EXPECTED_CLAIMS:
        raise SystemExit("Semantic review queue claim IDs are incomplete or duplicated.")
    missing = sorted(set(queue_ids) - set(SEMANTIC_DECISIONS))
    extra = sorted(set(SEMANTIC_DECISIONS) - set(queue_ids))
    if missing or extra:
        raise SystemExit(f"Semantic decision coverage mismatch; missing={missing}, extra={extra}")

    case_reviews: list[dict[str, object]] = []
    verdict_counts: Counter[str] = Counter()
    for item in queue["items"]:
        raw_case = raw_cases[item["case_id"]]
        gold = raw_case["gold_case"]
        selected_context_summary = [
            {
                "source_label": source["source_label"],
                "rank": source["rank"],
                "document_id": source.get("document_id"),
                "evidence_ids": source.get("evidence_ids", []),
                "section_title": source.get("section_title"),
                "content_excerpt": source["content"][:500],
            }
            for source in item["selected_context"]
        ]
        citation_summary = [
            {
                "source_label": citation["source_label"],
                "document_id": citation.get("document_id"),
                "evidence_ids": citation.get("evidence_ids", []),
                "content_excerpt": citation.get("content_excerpt", "")[:500],
            }
            for citation in item["citations"]
        ]
        claim_reviews = []
        for claim in item["semantic_claims"]:
            decision = SEMANTIC_DECISIONS[claim["claim_id"]]
            if decision["verdict"] not in ALLOWED_VERDICTS:
                raise SystemExit(f"Invalid verdict for {claim['claim_id']}: {decision['verdict']}")
            verdict_counts[decision["verdict"]] += 1
            claim_reviews.append(
                {
                    "case_id": item["case_id"],
                    "claim_id": claim["claim_id"],
                    "case_type": gold["case_type"],
                    "tier": gold["tier"],
                    "topic": gold["primary_topic"],
                    "difficulty": gold["difficulty"],
                    "query_language": gold["query_language"],
                    "question": item["question"],
                    "gold_claim": claim["canonical_claim"],
                    "required": claim["required"],
                    "evaluation_mode": claim["evaluation_mode"],
                    "evidence_group_ids": claim["evidence_group_ids"],
                    "machine_answer": item["normalized_answer"],
                    "selected_context_summary": selected_context_summary,
                    "citations": citation_summary,
                    **decision,
                    "reviewer_mode": "HUMAN_EVIDENCE_REVIEW",
                }
            )
        case_reviews.append(
            {
                "case_id": item["case_id"],
                "case_run_id": item["case_run_id"],
                "question": item["question"],
                "case_metadata": {
                    "case_type": gold["case_type"],
                    "tier": gold["tier"],
                    "topic": gold["primary_topic"],
                    "difficulty": gold["difficulty"],
                    "query_language": gold["query_language"],
                },
                "expected_answerable": item["expected_answerable"],
                "model_answerable": item["model_answerable"],
                "normalized_answer": item["normalized_answer"],
                "selected_context": item["selected_context"],
                "citations": item["citations"],
                "claim_reviews": claim_reviews,
            }
        )

    payload = {
        "schema_version": "1.0.0",
        "review_id": "learnpilot-rag-real-world-semantic-claim-reviews-v1",
        "provenance": {
            "baseline_run_id": "20260814T052007Z-593cd2ac",
            "raw_results_path": str(RAW.relative_to(ROOT)).replace("\\", "/"),
            "raw_results_sha256": raw_hash,
            "semantic_review_queue_path": str(QUEUE.relative_to(ROOT)).replace("\\", "/"),
            "semantic_review_queue_sha256": sha256(QUEUE),
            "frozen_at": datetime.now(timezone.utc).isoformat(),
        },
        "methodology": {
            "reviewer_mode": "HUMAN_EVIDENCE_REVIEW",
            "allowed_verdicts": sorted(ALLOWED_VERDICTS),
            "evidence_scope": "Frozen gold claim, machine answer, and context selected by the frozen baseline only.",
            "external_llm_used": False,
            "baseline_rerun": False,
            "retrieval_or_generation_invoked": False,
            "freeze_order": "This artifact and its detached hash are frozen before root-cause or optimization-addressability analysis.",
        },
        "summary": {
            "case_count": len(case_reviews),
            "semantic_claim_count": sum(verdict_counts.values()),
            "verdict_counts": {name: verdict_counts.get(name, 0) for name in sorted(ALLOWED_VERDICTS)},
            "coverage_complete": len(case_reviews) == EXPECTED_CASES and sum(verdict_counts.values()) == EXPECTED_CLAIMS,
        },
        "case_reviews": case_reviews,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "semantic_claim_reviews.schema.json", build_schema())
    write_json(output_path, payload)
    frozen_hash = sha256(output_path)
    hash_path.write_text(f"{frozen_hash}  semantic_claim_reviews.json\n", encoding="ascii", newline="\n")
    print(json.dumps({"status": "FROZEN", "semantic_claim_count": EXPECTED_CLAIMS, "sha256": frozen_hash}))


if __name__ == "__main__":
    main()
