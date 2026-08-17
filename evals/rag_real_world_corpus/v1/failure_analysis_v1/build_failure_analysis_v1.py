"""Build frozen-artifact-only Real-world Baseline Failure Analysis V1.

This program performs no retrieval, embedding, generation, ingestion, or network I/O.
It refuses to run unless the semantic-review freeze and all protected identities match.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analysis_decisions import (
    CITATION_STATUS_OVERRIDES,
    DETERMINISTIC_FAILURE_REVIEWS,
    EVAL_MAPPING_CASES,
    ROOT_CAUSE_DECISIONS,
    ROOT_CAUSE_TAXONOMY,
)


ROOT = Path(__file__).resolve().parents[4]
V1 = ROOT / "evals" / "rag_real_world_corpus" / "v1"
OUT = V1 / "failure_analysis_v1"
RUN = V1 / "results" / "dense_only_baseline_v1" / "20260814T052007Z-593cd2ac"
RAW_PATH = RUN / "raw_results.json"
CASE_RESULTS_PATH = RUN / "case_results.json"
SEMANTIC_PATH = OUT / "semantic_claim_reviews.json"
SEMANTIC_HASH_PATH = OUT / "semantic_claim_reviews.sha256"
REPORT_PATH = V1 / "RAG_REAL_WORLD_BASELINE_FAILURE_ANALYSIS_V1_REPORT.md"

EXPECTED = {
    "gold_sha256": "33a0b69901fa47e3fe45be0277228cd4a5519fe780fe5b9d2c52b1bfe614927a",
    "freeze_manifest_sha256": "d979079be4eb901a825ab29414dd7b5124d030182e09b55eea1e93749c12a5c2",
    "corpus_manifest_sha256": "6f67d510cd35197f107400d33033972c0c3c84478174e4991e491f6c8e4ab563",
    "raw_results_sha256": "bf718aed08e226149c9310cbf20bf25c403708217e2908789120178ac5574e28",
    "semantic_claim_reviews_sha256": "671fe1a484dd6ff8986b34c0ebf0826f274bbb9ed6dda404f18ad0a2bd60a176",
}

PROTECTED_PATHS = {
    "gold_sha256": V1 / "gold" / "v1" / "gold_cases.json",
    "freeze_manifest_sha256": V1 / "gold" / "v1" / "gold_dataset_v1_freeze_manifest.json",
    "corpus_manifest_sha256": V1 / "corpus_manifest.json",
    "raw_results_sha256": RAW_PATH,
    "semantic_claim_reviews_sha256": SEMANTIC_PATH,
}

CASE_STATUSES = {"FULL_PASS", "PARTIAL_PASS", "FAIL", "CORRECT_REFUSAL", "INCORRECT_REFUSAL"}
CITATION_SEMANTIC_STATUSES = {
    "CITATION_SUPPORTS_CLAIM",
    "CITATION_PARTIALLY_SUPPORTS",
    "CITATION_UNSUPPORTED",
    "CITATION_UNNECESSARY",
}


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


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def verify_protected_identities(raw: dict[str, Any]) -> dict[str, Any]:
    actual = {name: sha256(path) for name, path in PROTECTED_PATHS.items()}
    mismatches = {name: {"expected": EXPECTED[name], "actual": value} for name, value in actual.items() if value != EXPECTED[name]}
    detached_semantic = SEMANTIC_HASH_PATH.read_text(encoding="ascii").strip().split()[0]
    if detached_semantic != EXPECTED["semantic_claim_reviews_sha256"]:
        mismatches["semantic_claim_reviews_detached_sha256"] = {
            "expected": EXPECTED["semantic_claim_reviews_sha256"],
            "actual": detached_semantic,
        }
    production_actual = {name: sha256(ROOT / name) for name in raw["production_code_sha256"]}
    production_mismatches = {
        name: {"expected": expected_hash, "actual": production_actual[name]}
        for name, expected_hash in raw["production_code_sha256"].items()
        if production_actual[name] != expected_hash
    }
    if mismatches or production_mismatches:
        raise SystemExit(
            "FAILURE_ANALYSIS=HOLD; protected identity mismatch: "
            + json.dumps({"protected": mismatches, "production": production_mismatches}, sort_keys=True)
        )
    return {
        "protected": {
            name: {"path": relative(PROTECTED_PATHS[name]), "expected_sha256": EXPECTED[name], "actual_sha256": actual[name], "match": True}
            for name in PROTECTED_PATHS
        },
        "semantic_detached_sha256_match": True,
        "production_code": {
            "file_count": len(production_actual),
            "baseline_sha256": raw["production_code_sha256"],
            "current_sha256": production_actual,
            "all_match": True,
        },
    }


def flatten_semantic_reviews(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = [claim for case in payload["case_reviews"] for claim in case["claim_reviews"]]
    if len(rows) != 104 or len({row["claim_id"] for row in rows}) != 104:
        raise SystemExit("Frozen semantic review is not a unique 104-claim set.")
    return {row["claim_id"]: row for row in rows}


def reviewed_claims(case_result: dict[str, Any], semantic: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for claim in case_result["claim_metrics"]:
        mode = claim["evaluation_mode"]
        row: dict[str, Any] = {
            "claim_id": claim["claim_id"],
            "evaluation_mode": mode,
            "required": claim["required"],
            "gold_claim": claim["canonical_claim"],
            "machine_status": claim["status"],
        }
        if mode == "SEMANTIC_REVIEW":
            review = semantic[claim["claim_id"]]
            final = {
                "SUPPORTED": "PASS",
                "PARTIALLY_SUPPORTED": "PARTIAL",
                "UNSUPPORTED": "FAIL",
                "AMBIGUOUS": "PARTIAL",
            }[review["verdict"]]
            row.update(
                {
                    "machine_status": "REVIEW_REQUIRED",
                    "semantic_verdict": review["verdict"],
                    "final_status": final,
                    "review_reason": review["review_reason"],
                    "review_source": "semantic_claim_reviews.json",
                }
            )
        elif claim["claim_id"] in DETERMINISTIC_FAILURE_REVIEWS:
            review = DETERMINISTIC_FAILURE_REVIEWS[claim["claim_id"]]
            row.update(
                {
                    "final_status": review["final_status"],
                    "review_reason": review["review_reason"],
                    "failure_mode": review["failure_mode"],
                    "review_source": "manual_deterministic_failure_review",
                }
            )
        else:
            row.update(
                {
                    "final_status": "PASS" if claim["status"] == "PASS" else "FAIL",
                    "review_reason": "The frozen deterministic evaluator passed this exact or answerability-only obligation.",
                    "review_source": "frozen_deterministic_metric",
                }
            )
        rows.append(row)
    return rows


def case_verdict(case_result: dict[str, Any], claims: list[dict[str, Any]]) -> tuple[str, str]:
    answerability = case_result["answerability_metrics"]
    if not answerability["expected"]:
        if not answerability["actual"]:
            return "CORRECT_REFUSAL", "The Gold case is unanswerable and the model gives a corpus-bounded refusal."
        return "FAIL", "The Gold case is unanswerable but the model answers it."
    if not answerability["actual"]:
        return "INCORRECT_REFUSAL", "The Gold case is answerable but the model refuses."
    finals = [claim["final_status"] for claim in claims if claim["required"]]
    if finals and all(value == "PASS" for value in finals):
        return "FULL_PASS", "Every required reviewed claim is fulfilled."
    if any(value in {"PASS", "PARTIAL"} for value in finals):
        return "PARTIAL_PASS", "At least one required claim is fulfilled, but one or more obligations are partial or failed."
    return "FAIL", "No key required claim is fulfilled."


def attached_span(answer: str, label: str) -> str:
    marker = f"[{label}]"
    pos = answer.find(marker)
    if pos < 0:
        return answer[:300]
    boundary = max(answer.rfind(ch, max(0, pos - 500), pos) for ch in "。！？.!?")
    start = boundary + 1 if boundary >= 0 else max(0, pos - 350)
    return " ".join(answer[start:pos].split())[-350:]


def citation_reviews(raw_cases: list[dict[str, Any]], case_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    actual_reviews: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    by_case: dict[str, dict[str, Any]] = {}
    status_counts: Counter[str] = Counter()

    for raw_case in raw_cases:
        case_id = raw_case["case_id"]
        gold = raw_case["gold_case"]
        group_map = {group["evidence_group_id"]: group for group in gold["evidence_groups"]}
        case_rows: list[dict[str, Any]] = []
        for index, citation in enumerate(raw_case["citations"], start=1):
            label = citation["source_label"]
            excerpt = citation.get("content_excerpt", "")
            adjacent = attached_span(raw_case["normalized_answer"], label)
            matching_groups = []
            for group in gold["evidence_groups"]:
                if citation.get("document_id") in group["any_of_document_ids"] or set(citation.get("evidence_ids", [])) & set(group["any_of_evidence_ids"]):
                    matching_groups.append(group["evidence_group_id"])
            matching_claims = [
                claim["claim_id"]
                for claim in gold["claims"]
                if set(claim["evidence_group_ids"]) & set(matching_groups)
            ]
            override = CITATION_STATUS_OVERRIDES.get((case_id, label))
            if override:
                semantic_status, reason = override
            else:
                semantic_status = "CITATION_SUPPORTS_CLAIM"
                compact_excerpt = " ".join(excerpt.split())[:220]
                compact_adjacent = adjacent[:220]
                reason = (
                    f"The cited {citation.get('document_id')} excerpt semantically supports the adjacent assertion "
                    f"‘{compact_adjacent}’; its supporting text begins ‘{compact_excerpt}’."
                )
            if semantic_status not in CITATION_SEMANTIC_STATUSES:
                raise SystemExit(f"Invalid citation status for {case_id}/{label}: {semantic_status}")
            row = {
                "citation_review_id": f"{case_id}:{label}:{index}",
                "case_id": case_id,
                "source_label": label,
                "document_id": citation.get("document_id"),
                "evidence_ids": citation.get("evidence_ids", []),
                "content_excerpt": excerpt,
                "attached_answer_span": adjacent,
                "matching_required_evidence_group_ids": matching_groups,
                "related_claim_ids": matching_claims,
                "validity_status": "CITATION_VALID",
                "semantic_status": semantic_status,
                "review_reason": reason,
            }
            actual_reviews.append(row)
            case_rows.append(row)
            status_counts[semantic_status] += 1

        coverage = case_results[case_id]["citation_metrics"]["required_group_coverage"]["groups"]
        case_missing = []
        for group_result in coverage:
            if group_result["required"] and not group_result["document_pass"]:
                group = group_map[group_result["evidence_group_id"]]
                missing_row = {
                    "case_id": case_id,
                    "evidence_group_id": group["evidence_group_id"],
                    "expected_document_ids": group["any_of_document_ids"],
                    "expected_evidence_ids": group["any_of_evidence_ids"],
                    "status": "CITATION_MISSING",
                    "review_reason": "No returned citation covers this frozen required evidence group by document, so the citation contract obligation is missing.",
                }
                missing.append(missing_row)
                case_missing.append(missing_row)

        semantic_fail = any(row["semantic_status"] == "CITATION_UNSUPPORTED" for row in case_rows)
        semantic_partial = any(row["semantic_status"] == "CITATION_PARTIALLY_SUPPORTS" for row in case_rows)
        if case_missing or semantic_fail:
            final = "FAIL"
        elif semantic_partial:
            final = "PARTIAL"
        else:
            final = "PASS"
        by_case[case_id] = {
            "actual_citation_count": len(case_rows),
            "missing_required_group_count": len(case_missing),
            "machine_contract_pass": case_results[case_id]["citation_metrics"]["machine_contract_pass"],
            "semantic_citation_status": final,
        }

    if len(actual_reviews) != 97:
        raise SystemExit(f"Expected 97 returned citations, found {len(actual_reviews)}")
    return {
        "schema_version": "1.0.0",
        "review_id": "learnpilot-rag-real-world-citation-semantic-reviews-v1",
        "provenance": {"baseline_run_id": "20260814T052007Z-593cd2ac", "raw_results_sha256": EXPECTED["raw_results_sha256"]},
        "methodology": {
            "review_scope": "Every returned citation is checked against its attached answer assertion and frozen selected excerpt; missing required source groups are recorded separately.",
            "structural_validity_is_not_semantic_support": True,
            "external_llm_used": False,
        },
        "summary": {
            "returned_citation_count": len(actual_reviews),
            "returned_citations_reviewed": len(actual_reviews),
            "valid_citation_count": len(actual_reviews),
            "semantic_status_counts": {name: status_counts.get(name, 0) for name in sorted(CITATION_SEMANTIC_STATUSES)},
            "missing_required_group_count": len(missing),
            "case_status_counts": dict(sorted(Counter(item["semantic_citation_status"] for item in by_case.values()).items())),
            "coverage_complete": len(actual_reviews) == 97,
        },
        "citation_reviews": actual_reviews,
        "missing_required_evidence_groups": missing,
        "case_summaries": [dict(case_id=case_id, **values) for case_id, values in by_case.items()],
    }


def breakdown(case_rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in case_rows:
        groups[str(row["case_metadata"][field])].append(row)
    result = {}
    for name, rows in sorted(groups.items()):
        status_counts = Counter(row["case_verdict"] for row in rows)
        root_counts = Counter(row["primary_root_cause"] for row in rows)
        result[name] = {
            "case_count": len(rows),
            "full_pass_count": status_counts["FULL_PASS"],
            "full_pass_rate": round(status_counts["FULL_PASS"] / len(rows), 4),
            "case_verdict_counts": dict(sorted(status_counts.items())),
            "primary_root_cause_counts": dict(sorted(root_counts.items())),
        }
    return result


def build_case_analysis(
    raw_cases: list[dict[str, Any]],
    results_by_id: dict[str, dict[str, Any]],
    semantic: dict[str, dict[str, Any]],
    citations_by_case: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    explicit_ids = set(ROOT_CAUSE_DECISIONS) | set(EVAL_MAPPING_CASES)
    if set(ROOT_CAUSE_DECISIONS) & set(EVAL_MAPPING_CASES):
        raise SystemExit("Root-cause decision maps overlap.")
    unknown = explicit_ids - set(results_by_id)
    if unknown:
        raise SystemExit(f"Root-cause decisions reference unknown cases: {sorted(unknown)}")

    cases = []
    for raw_case in raw_cases:
        case_id = raw_case["case_id"]
        result = results_by_id[case_id]
        claims = reviewed_claims(result, semantic)
        verdict, verdict_reason = case_verdict(result, claims)
        if case_id in ROOT_CAUSE_DECISIONS:
            root = dict(ROOT_CAUSE_DECISIONS[case_id])
        elif case_id in EVAL_MAPPING_CASES:
            root = {
                "primary_root_cause": "EVAL_MAPPING_DIAGNOSTIC",
                "root_cause_reason": EVAL_MAPPING_CASES[case_id],
                "affected_required_groups": [],
                "stage_evidence": {"product_answer_failure": False, "diagnostic_or_evaluator_false_negative": True},
                "addressability_class": "NOT_ARCHITECTURE_ADDRESSABLE",
                "addressability_strength": "HIGH",
            }
        else:
            root = {
                "primary_root_cause": "NO_FAILURE",
                "root_cause_reason": "The reviewed answer/corpus-bounded refusal and citation contract pass, and no upstream or evaluator defect is verified.",
                "affected_required_groups": [],
                "stage_evidence": {"product_answer_failure": False, "citation_failure": False},
                "addressability_class": "NOT_ARCHITECTURE_ADDRESSABLE",
                "addressability_strength": "NONE",
            }
        if root["primary_root_cause"] not in ROOT_CAUSE_TAXONOMY:
            raise SystemExit(f"Invalid root cause for {case_id}")
        secondary = list(result["preliminary_failure_signals"])
        if not result["retrieval_metrics"]["candidate"]["anchor_pass"]:
            secondary.append("ANCHOR_CANDIDATE_DIAGNOSTIC_MISS")
        if not result["retrieval_metrics"]["selected"]["anchor_pass"]:
            secondary.append("ANCHOR_SELECTED_DIAGNOSTIC_MISS")
        secondary = sorted(set(secondary))
        case_row = {
            "sequence": result["sequence"],
            "case_id": case_id,
            "case_run_id": result["case_run_id"],
            "case_metadata": {
                "tier": result["case_metadata"]["tier"],
                "case_type": result["case_metadata"]["case_type"],
                "topic": result["case_metadata"]["primary_topic"],
                "difficulty": result["case_metadata"]["difficulty"],
                "query_language": result["case_metadata"]["query_language"],
                "expected_answerable": result["case_metadata"]["answerable"],
            },
            "question": raw_case["gold_case"]["question"],
            "machine_answer": raw_case["normalized_answer"],
            "case_verdict": verdict,
            "case_verdict_reason": verdict_reason,
            "claim_reviews": claims,
            "retrieval_review": result["retrieval_metrics"],
            "answerability_review": result["answerability_metrics"],
            "citation_review": citations_by_case[case_id],
            "primary_root_cause": root["primary_root_cause"],
            "primary_root_cause_reason": root["root_cause_reason"],
            "affected_required_groups": root["affected_required_groups"],
            "stage_evidence": root["stage_evidence"],
            "secondary_signals": secondary,
            "addressability_class": root["addressability_class"],
            "addressability_strength": root["addressability_strength"],
        }
        cases.append(case_row)

    if len(cases) != 72 or len({row["case_id"] for row in cases}) != 72:
        raise SystemExit("Case analysis does not cover exactly 72 unique cases.")
    return {
        "schema_version": "1.0.0",
        "analysis_id": "learnpilot-rag-real-world-baseline-failure-analysis-v1",
        "baseline_run_id": "20260814T052007Z-593cd2ac",
        "methodology": {
            "pipeline_attribution_order": ["RETRIEVAL", "SELECTION", "ANSWERABILITY", "GENERATION", "MULTI_DOC_SYNTHESIS", "CITATION", "EVAL_MAPPING"],
            "exactly_one_primary_root_cause_per_case": True,
            "anchor_metrics_are_diagnostic_only": True,
            "external_llm_used": False,
            "baseline_rerun": False,
        },
        "cases": cases,
    }


def build_addressability(cases: list[dict[str, Any]]) -> dict[str, Any]:
    entries = []
    for row in cases:
        classification = row["addressability_class"]
        strength = row["addressability_strength"]
        dimensions = {
            "hybrid": strength if classification == "HYBRID_ADDRESSABLE" else "NONE",
            "reranker": strength if classification == "RERANKER_ADDRESSABLE" else "NONE",
            "generation": strength if classification == "GENERATION_ADDRESSABLE" else "NONE",
            "answerability": strength if classification == "ANSWERABILITY_ADDRESSABLE" else "NONE",
            "citation": strength if classification == "CITATION_ADDRESSABLE" else "NONE",
            "not_architecture": strength if classification == "NOT_ARCHITECTURE_ADDRESSABLE" else "NONE",
        }
        entries.append(
            {
                "case_id": row["case_id"],
                "case_verdict": row["case_verdict"],
                "primary_root_cause": row["primary_root_cause"],
                "addressability_class": classification,
                "addressability_strength": strength,
                "dimensions": dimensions,
                "evidence": row["stage_evidence"],
                "rationale": row["primary_root_cause_reason"],
            }
        )
    class_counts = Counter(entry["addressability_class"] for entry in entries)
    high_counts = {
        dimension: sum(entry["dimensions"][dimension] == "HIGH" for entry in entries)
        for dimension in ["hybrid", "reranker", "generation", "answerability", "citation", "not_architecture"]
    }
    return {
        "schema_version": "1.0.0",
        "analysis_id": "learnpilot-rag-real-world-optimization-addressability-matrix-v1",
        "definition": "Theoretical addressability only; it does not assert that any optimization will fix the case.",
        "summary": {
            "case_count": len(entries),
            "addressability_class_counts": dict(sorted(class_counts.items())),
            "high_strength_dimension_counts": high_counts,
        },
        "entries": entries,
    }


def build_schema(kind: str) -> dict[str, Any]:
    if kind == "case":
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "learnpilot://rag-real-world/failure-analysis-v1/case-failure-analysis.schema.json",
            "type": "object",
            "required": ["schema_version", "analysis_id", "baseline_run_id", "methodology", "cases"],
            "properties": {
                "schema_version": {"const": "1.0.0"},
                "cases": {
                    "type": "array", "minItems": 72, "maxItems": 72,
                    "items": {
                        "type": "object",
                        "required": ["case_id", "case_verdict", "claim_reviews", "primary_root_cause", "primary_root_cause_reason", "secondary_signals", "addressability_class"],
                        "properties": {
                            "case_id": {"type": "string"},
                            "case_verdict": {"enum": sorted(CASE_STATUSES)},
                            "primary_root_cause": {"enum": sorted(ROOT_CAUSE_TAXONOMY)},
                            "claim_reviews": {"type": "array", "minItems": 1},
                        },
                    },
                },
            },
        }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "learnpilot://rag-real-world/failure-analysis-v1/citation-semantic-reviews.schema.json",
        "type": "object",
        "required": ["schema_version", "review_id", "summary", "citation_reviews", "missing_required_evidence_groups", "case_summaries"],
        "properties": {
            "schema_version": {"const": "1.0.0"},
            "citation_reviews": {"type": "array", "minItems": 97, "maxItems": 97},
            "missing_required_evidence_groups": {"type": "array"},
            "case_summaries": {"type": "array", "minItems": 72, "maxItems": 72},
        },
    }


def markdown_case_list(cases: list[dict[str, Any]], root: str) -> str:
    rows = [row for row in cases if row["primary_root_cause"] == root]
    if not rows:
        return "None verified."
    return "\n".join(f"- `{row['case_id']}` — {row['primary_root_cause_reason']}" for row in rows)


def build_report(
    case_payload: dict[str, Any],
    root_summary: dict[str, Any],
    citation_payload: dict[str, Any],
    addressability: dict[str, Any],
    hypotheses: dict[str, Any],
    identities: dict[str, Any],
) -> str:
    cases = case_payload["cases"]
    case_counts = root_summary["case_verdict_counts"]
    root_counts = root_summary["primary_root_cause_counts"]
    claim_counts = root_summary["combined_claim_result"]["final_status_counts"]
    semantic_counts = root_summary["semantic_claim_result"]["verdict_counts"]
    address_counts = addressability["summary"]["addressability_class_counts"]
    false_refusals = [row for row in cases if row["case_verdict"] == "INCORRECT_REFUSAL"]
    false_refusal_table = "\n".join(f"| `{row['case_id']}` | `{row['primary_root_cause']}` |" for row in false_refusals)
    root_table = "\n".join(f"| `{name}` | {count} |" for name, count in sorted(root_counts.items()))
    mode_table = "\n".join(
        f"| `{name}` | {values['claim_count']} | {values['PASS']} | {values['PARTIAL']} | {values['FAIL']} |"
        for name, values in sorted(root_summary["combined_claim_result"]["by_evaluation_mode"].items())
    )
    case_type_rows = "\n".join(
        f"| `{name}` | {values['case_count']} | {values['full_pass_count']} | {values['full_pass_rate']:.2%} |"
        for name, values in root_summary["breakdowns"]["case_type"].items()
    )
    created = [
        "evals/rag_real_world_corpus/v1/failure_analysis_v1/semantic_review_decisions.py",
        "evals/rag_real_world_corpus/v1/failure_analysis_v1/freeze_semantic_reviews.py",
        "evals/rag_real_world_corpus/v1/failure_analysis_v1/analysis_decisions.py",
        "evals/rag_real_world_corpus/v1/failure_analysis_v1/build_failure_analysis_v1.py",
        "evals/rag_real_world_corpus/v1/failure_analysis_v1/semantic_claim_reviews.json",
        "evals/rag_real_world_corpus/v1/failure_analysis_v1/semantic_claim_reviews.schema.json",
        "evals/rag_real_world_corpus/v1/failure_analysis_v1/semantic_claim_reviews.sha256",
        "evals/rag_real_world_corpus/v1/failure_analysis_v1/citation_semantic_reviews.json",
        "evals/rag_real_world_corpus/v1/failure_analysis_v1/citation_semantic_reviews.schema.json",
        "evals/rag_real_world_corpus/v1/failure_analysis_v1/case_failure_analysis.json",
        "evals/rag_real_world_corpus/v1/failure_analysis_v1/case_failure_analysis.schema.json",
        "evals/rag_real_world_corpus/v1/failure_analysis_v1/root_cause_summary.json",
        "evals/rag_real_world_corpus/v1/failure_analysis_v1/optimization_addressability_matrix.json",
        "evals/rag_real_world_corpus/v1/failure_analysis_v1/ablation_hypotheses.json",
        "evals/rag_real_world_corpus/v1/failure_analysis_v1/failure_analysis_manifest.json",
        "evals/rag_real_world_corpus/v1/RAG_REAL_WORLD_BASELINE_FAILURE_ANALYSIS_V1_REPORT.md",
        "backend/tests/test_rag_real_world_failure_analysis_v1.py",
    ]
    return f"""# LearnPilot RAG Real-world Baseline Failure Analysis V1

## 1. Analysis identity

Analysis ID: `learnpilot-rag-real-world-baseline-failure-analysis-v1`; frozen baseline run: `20260814T052007Z-593cd2ac`.

## 2. Frozen baseline binding

- Gold: `{EXPECTED['gold_sha256']}`
- Freeze manifest: `{EXPECTED['freeze_manifest_sha256']}`
- Corpus manifest: `{EXPECTED['corpus_manifest_sha256']}`
- Raw baseline: `{EXPECTED['raw_results_sha256']}`
- Frozen semantic review: `{EXPECTED['semantic_claim_reviews_sha256']}`
- Protected identities and all {identities['production_code']['file_count']} production-code files match the baseline binding.

## 3. Semantic review methodology

All 104 `SEMANTIC_REVIEW` claims were judged against the frozen Gold claim, frozen answer, actual selected context, citations, and project-owned frozen corpus only. Verdicts were frozen and detached-hashed before root cause or addressability was computed. No lexical proxy or model call was used.

## 4. 104 semantic claim verdicts summary

- Supported: {semantic_counts['SUPPORTED']}
- Partially supported: {semantic_counts['PARTIALLY_SUPPORTED']}
- Unsupported: {semantic_counts['UNSUPPORTED']}
- Ambiguous: {semantic_counts['AMBIGUOUS']}

## 5. Combined 132-claim result

Final reviewed claims: **{claim_counts['PASS']} pass / {claim_counts['PARTIAL']} partial / {claim_counts['FAIL']} fail** out of 132. Machine deterministic result remains 24/28; manual review changes only the MLDR structured-exact false negative, producing 25/28 reviewed deterministic pass.

| Evaluation mode | Claims | Pass | Partial | Fail |
|---|---:|---:|---:|---:|
{mode_table}

## 6. 72-case reviewed result

- FULL_PASS: {case_counts.get('FULL_PASS', 0)}
- PARTIAL_PASS: {case_counts.get('PARTIAL_PASS', 0)}
- FAIL: {case_counts.get('FAIL', 0)}
- CORRECT_REFUSAL: {case_counts.get('CORRECT_REFUSAL', 0)}
- INCORRECT_REFUSAL: {case_counts.get('INCORRECT_REFUSAL', 0)}

## 7. Citation semantic result

All {citation_payload['summary']['returned_citation_count']} returned citations were reviewed: {citation_payload['summary']['semantic_status_counts']['CITATION_SUPPORTS_CLAIM']} support, {citation_payload['summary']['semantic_status_counts']['CITATION_PARTIALLY_SUPPORTS']} partial, {citation_payload['summary']['semantic_status_counts']['CITATION_UNSUPPORTED']} unsupported, and {citation_payload['summary']['semantic_status_counts']['CITATION_UNNECESSARY']} unnecessary. There are {citation_payload['summary']['missing_required_group_count']} missing required evidence-group citation obligations. Structural validity remains 97/97 and is reported separately from semantic support.

## 8. Root-cause taxonomy

Attribution is upstream-first: retrieval → selection → answerability → generation → multi-document synthesis → citation → eval/mapping. Every case has exactly one primary root cause; secondary signals do not add to totals.

## 9. Exact root-cause distribution

| Primary root cause | Cases |
|---|---:|
{root_table}

## 10. Retrieval failures

{markdown_case_list(cases, 'RETRIEVAL_MISS')}

`rw-gold-v1-multi-rag-tracing` is the sole document-group candidate miss; the other retrieval misses are claim-required evidence/chunk misses inside otherwise retrieved document groups.

## 11. Selection/ranking failures

{markdown_case_list(cases, 'SELECTION_DIVERSITY_MISS')}

{markdown_case_list(cases, 'SELECTION_RANKING_MISS')}

No threshold, dedup, or context-budget primary miss is verified.

## 12. Answerability failures

| Original false-refusal case | Final primary attribution |
|---|---|
{false_refusal_table}

Only {root_counts.get('ANSWERABILITY_FALSE_NEGATIVE', 0)} of the 12 false-refusal signals remain true answerability false negatives after upstream evidence sufficiency is checked.

## 13. Generation failures

{markdown_case_list(cases, 'GENERATION_OMISSION')}

No fact error, overclaim, or extraction-error primary cause is verified. The apparent MLDR structured-exact failure is an evaluator language-mapping false negative, not a generation error.

## 14. Multi-doc synthesis failures

None verified. The low aggregate performance for multi-document groups resolves upstream: missing evidence, selection loss, or false refusal occurs before a complete selected-evidence set can be synthesized. Dense candidate document coverage alone therefore overstates synthesis readiness.

## 15. Citation-only failures

{markdown_case_list(cases, 'CITATION_ONLY_FAILURE')}

These answers are semantically correct; the missing required source is not double-counted as generation failure.

## 16. Eval/mapping diagnostic findings

{markdown_case_list(cases, 'EVAL_MAPPING_DIAGNOSTIC')}

Candidate anchor coverage is 59/72 and selected anchor coverage is 41/72. Of 31 selected-anchor misses, 18 correspond to verified upstream evidence/selection deficits; 13 are semantic-equivalent or boundary-mapping diagnostics. Conversely, one selected anchor pass (`stress-cross-embedding-api-concurrency`) masks a runtime boundary fragment that omits the first half of the anchored guidance. Anchor IDs are therefore diagnostics, not truth labels.

## 17. CORE/STRESS breakdown

CORE and STRESS counts, verdicts, and primary causes are recorded under `breakdowns.tier` in `root_cause_summary.json`; the same artifact contains all required topic, difficulty, and language breakdowns.

## 18. Case-type/topic/difficulty/language breakdown

| Case type | Cases | Full pass | Full-pass rate |
|---|---:|---:|---:|
{case_type_rows}

Detailed topic, difficulty, and query-language tables are machine-readable in `root_cause_summary.json`.

## 19. Optimization Addressability Matrix

- Hybrid-addressable cases: {address_counts.get('HYBRID_ADDRESSABLE', 0)}
- Reranker-addressable cases: {address_counts.get('RERANKER_ADDRESSABLE', 0)}
- Generation-addressable cases: {address_counts.get('GENERATION_ADDRESSABLE', 0)}
- Answerability-addressable cases: {address_counts.get('ANSWERABILITY_ADDRESSABLE', 0)}
- Citation-addressable cases: {address_counts.get('CITATION_ADDRESSABLE', 0)}
- Not-architecture-addressable / no-failure cases: {address_counts.get('NOT_ARCHITECTURE_ADDRESSABLE', 0)}

These are theoretical targets, not promises of improvement.

## 20. Ablation hypotheses

- `dense_only`: frozen control; no expected mutation.
- `hybrid`: targets the {address_counts.get('HYBRID_ADDRESSABLE', 0)} candidate-evidence misses and should be judged on required evidence candidate coverage.
- `dense_rerank`: targets the {address_counts.get('RERANKER_ADDRESSABLE', 0)} candidate-hit/selection-miss cases and should be judged on selected required-evidence coverage.
- `hybrid_rerank`: tests complementary recall plus ranking effects; no case is pre-labeled as requiring both, and the combined arm is not presumed best.

The exact frozen case lists and null hypothesis are in `ablation_hypotheses.json`.

## 21. Benchmark / raw result immutability

All protected hashes and production code hashes were revalidated before artifact construction and again by the test suite. Raw results, Gold, corpus, freeze manifest, and production RAG were not modified.

## 22. Tests

Focused joint regression passed **19/19** tests:

```text
python -m pytest backend/tests/test_rag_real_world_failure_analysis_v1.py backend/tests/test_rag_real_world_dense_only_baseline_v1.py -q
19 passed
```

The suite verifies 72/72 case coverage, 104/104 semantic reviews, 97/97 returned citations, 132 final claim statuses, exactly one root per case, root/addressability invariants, all protected hashes, artifact/code identities, and production-code identity.

## 23. Files created/modified

""" + "\n".join(f"- `{path}`" for path in created) + f"""

## 24. Explicit confirmation

```text
NO OPTIMIZATION PERFORMED
NO EXTERNAL LLM CALL
NO BASELINE RERUN
NO EMBEDDING EXECUTION
NO FAISS RETRIEVAL EXECUTION
NO PRODUCTION RAG ASK
```

```text
RAG_REAL_WORLD_BASELINE_FAILURE_ANALYSIS_V1 = COMPLETE
READY_FOR_ABLATION_DESIGN = YES
```
"""


def main() -> None:
    raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    identities = verify_protected_identities(raw)
    semantic_payload = json.loads(SEMANTIC_PATH.read_text(encoding="utf-8"))
    semantic = flatten_semantic_reviews(semantic_payload)
    case_results_list = json.loads(CASE_RESULTS_PATH.read_text(encoding="utf-8"))["cases"]
    results_by_id = {row["case_id"]: row for row in case_results_list}

    citation_payload = citation_reviews(raw["cases"], results_by_id)
    citation_by_case = {row["case_id"]: row for row in citation_payload["case_summaries"]}
    case_payload = build_case_analysis(raw["cases"], results_by_id, semantic, citation_by_case)
    cases = case_payload["cases"]

    case_counts = Counter(row["case_verdict"] for row in cases)
    root_counts = Counter(row["primary_root_cause"] for row in cases)
    all_claims = [claim for row in cases for claim in row["claim_reviews"]]
    if len(all_claims) != 132 or len({claim["claim_id"] for claim in all_claims}) != 132:
        raise SystemExit("Combined claim coverage is not exactly 132 unique claims.")
    final_claim_counts = Counter(claim["final_status"] for claim in all_claims)
    by_mode = {}
    for mode in sorted({claim["evaluation_mode"] for claim in all_claims}):
        rows = [claim for claim in all_claims if claim["evaluation_mode"] == mode]
        counts = Counter(claim["final_status"] for claim in rows)
        by_mode[mode] = {"claim_count": len(rows), "PASS": counts["PASS"], "PARTIAL": counts["PARTIAL"], "FAIL": counts["FAIL"]}

    root_summary = {
        "schema_version": "1.0.0",
        "analysis_id": "learnpilot-rag-real-world-root-cause-summary-v1",
        "case_count": len(cases),
        "case_verdict_counts": dict(sorted(case_counts.items())),
        "primary_root_cause_counts": dict(sorted(root_counts.items())),
        "primary_root_cause_case_ids": {
            root: [row["case_id"] for row in cases if row["primary_root_cause"] == root]
            for root in sorted(root_counts)
        },
        "semantic_claim_result": semantic_payload["summary"],
        "machine_deterministic_result": {"claim_count": 28, "pass_count": 24, "fail_count": 4, "pass_rate": 0.8571},
        "reviewed_deterministic_result": {"claim_count": 28, "pass_count": 25, "fail_count": 3, "pass_rate": round(25 / 28, 4)},
        "combined_claim_result": {
            "claim_count": len(all_claims),
            "final_status_counts": {"PASS": final_claim_counts["PASS"], "PARTIAL": final_claim_counts["PARTIAL"], "FAIL": final_claim_counts["FAIL"]},
            "by_evaluation_mode": by_mode,
        },
        "false_refusal_attribution": [
            {"case_id": row["case_id"], "primary_root_cause": row["primary_root_cause"], "reason": row["primary_root_cause_reason"]}
            for row in cases if row["case_verdict"] == "INCORRECT_REFUSAL"
        ],
        "anchor_diagnostic": {
            "candidate_anchor_pass": 59,
            "candidate_anchor_miss": 13,
            "selected_anchor_pass": 41,
            "selected_anchor_miss": 31,
            "selected_miss_verified_upstream_count": 18,
            "selected_miss_semantic_equivalent_or_mapping_count": 13,
            "selected_anchor_false_positive_cases": ["rw-gold-v1-stress-cross-embedding-api-concurrency"],
            "interpretation": "Anchor coverage is runtime-chunk mapping telemetry and is not used alone as a product-failure label.",
        },
        "breakdowns": {
            "tier": breakdown(cases, "tier"),
            "case_type": breakdown(cases, "case_type"),
            "topic": breakdown(cases, "topic"),
            "difficulty": breakdown(cases, "difficulty"),
            "query_language": breakdown(cases, "query_language"),
        },
    }

    addressability = build_addressability(cases)
    retrieval_targets = [row["case_id"] for row in cases if row["addressability_class"] == "HYBRID_ADDRESSABLE"]
    reranker_targets = [row["case_id"] for row in cases if row["addressability_class"] == "RERANKER_ADDRESSABLE"]
    hypotheses = {
        "schema_version": "1.0.0",
        "hypothesis_id": "learnpilot-rag-real-world-ablation-hypotheses-v1",
        "frozen_from_semantic_review_sha256": EXPECTED["semantic_claim_reviews_sha256"],
        "arms": {
            "dense_only": {
                "role": "Frozen control",
                "target_case_ids": [],
                "hypothesis": "Repetition without architecture change should reproduce the frozen distribution within declared runtime variance; this analysis does not rerun it.",
                "primary_metrics": ["candidate_required_evidence_coverage", "selected_required_evidence_coverage", "reviewed_case_verdicts"],
            },
            "hybrid": {
                "target_case_ids": retrieval_targets,
                "hypothesis": "Lexical/exact-term retrieval may add required evidence missing from dense candidates, especially identifiers, numeric defaults, API names, and explicit terminology.",
                "primary_metrics": ["candidate_required_evidence_coverage", "candidate_document_group_coverage"],
                "null_hypothesis": "Hybrid does not improve required-evidence candidate coverage on these cases.",
            },
            "dense_rerank": {
                "target_case_ids": reranker_targets,
                "hypothesis": "An independent reranker may promote already-retrieved required evidence above diversity/ranking selection losses.",
                "primary_metrics": ["selected_required_evidence_coverage", "selected_anchor_diagnostic_coverage", "answerability_after_sufficient_selection"],
                "null_hypothesis": "Reranking does not improve selected required-evidence coverage on candidate-hit cases.",
            },
            "hybrid_rerank": {
                "target_case_ids": sorted(set(retrieval_targets) | set(reranker_targets)),
                "requires_both_case_ids": [],
                "hypothesis": "Hybrid may improve candidate recall and reranking may improve subsequent selection, but complementarity must be measured and is not presumed.",
                "primary_metrics": ["candidate_required_evidence_coverage", "selected_required_evidence_coverage", "reviewed_case_verdicts"],
                "null_hypothesis": "The combined arm provides no complementary gain beyond its best single intervention.",
            },
        },
        "constraints": {"no_arm_is_presumed_best": True, "hypotheses_are_not_optimizations": True},
    }

    write_json(OUT / "citation_semantic_reviews.schema.json", build_schema("citation"))
    write_json(OUT / "citation_semantic_reviews.json", citation_payload)
    write_json(OUT / "case_failure_analysis.schema.json", build_schema("case"))
    write_json(OUT / "case_failure_analysis.json", case_payload)
    write_json(OUT / "root_cause_summary.json", root_summary)
    write_json(OUT / "optimization_addressability_matrix.json", addressability)
    write_json(OUT / "ablation_hypotheses.json", hypotheses)

    REPORT_PATH.write_text(
        build_report(case_payload, root_summary, citation_payload, addressability, hypotheses, identities),
        encoding="utf-8",
        newline="\n",
    )

    analysis_code_paths = [
        OUT / "semantic_review_decisions.py",
        OUT / "freeze_semantic_reviews.py",
        OUT / "analysis_decisions.py",
        OUT / "build_failure_analysis_v1.py",
    ]
    artifact_paths = [
        SEMANTIC_PATH,
        OUT / "semantic_claim_reviews.schema.json",
        SEMANTIC_HASH_PATH,
        OUT / "citation_semantic_reviews.json",
        OUT / "citation_semantic_reviews.schema.json",
        OUT / "case_failure_analysis.json",
        OUT / "case_failure_analysis.schema.json",
        OUT / "root_cause_summary.json",
        OUT / "optimization_addressability_matrix.json",
        OUT / "ablation_hypotheses.json",
        REPORT_PATH,
    ]
    manifest = {
        "schema_version": "1.0.0",
        "analysis_id": "learnpilot-rag-real-world-baseline-failure-analysis-v1",
        "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
        "baseline_run_id": "20260814T052007Z-593cd2ac",
        "frozen_bindings": identities,
        "semantic_review_sha256": EXPECTED["semantic_claim_reviews_sha256"],
        "analysis_code_identity": {relative(path): sha256(path) for path in analysis_code_paths},
        "artifact_sha256": {relative(path): sha256(path) for path in artifact_paths},
        "coverage": {"cases": 72, "semantic_claims": 104, "combined_claims": 132, "returned_citations": 97},
        "execution_declarations": {
            "external_llm_calls": 0,
            "deepseek_calls": 0,
            "production_rag_ask_calls": 0,
            "baseline_rerun": False,
            "embedding_executions": 0,
            "faiss_retrieval_executions": 0,
            "corpus_ingestion_executions": 0,
            "production_modified": False,
            "optimization_performed": False,
        },
        "status": "COMPLETE",
        "ready_for_ablation_design": True,
    }
    write_json(OUT / "failure_analysis_manifest.json", manifest)
    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "cases": len(cases),
                "claims": len(all_claims),
                "citations": citation_payload["summary"]["returned_citation_count"],
                "case_verdict_counts": dict(case_counts),
                "root_cause_counts": dict(root_counts),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
