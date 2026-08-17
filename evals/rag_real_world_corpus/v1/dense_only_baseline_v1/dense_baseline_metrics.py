"""Deterministic metrics for the frozen Real-world Gold V1 baseline.

Semantic-review claims are intentionally never converted into lexical pass/fail
proxies.  They remain REVIEW_REQUIRED in the machine output and are emitted into
the separate review queue with the frozen model answer and retrieved evidence.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
from statistics import mean, median
from typing import Any, Iterable


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 2)


def source_documents(sources: Iterable[dict[str, Any]]) -> set[str]:
    return {item["document_id"] for item in sources if item.get("document_id")}


def source_evidence(sources: Iterable[dict[str, Any]]) -> set[str]:
    return {
        evidence_id
        for item in sources
        for evidence_id in item.get("evidence_ids", [])
    }


def group_coverage(
    groups: list[dict[str, Any]], sources: list[dict[str, Any]]
) -> dict[str, Any]:
    """Apply Gold V2 semantics: OR within a group, AND across required groups."""
    docs = source_documents(sources)
    evidence = source_evidence(sources)
    rows = []
    for group in groups:
        required = bool(group.get("required", False))
        document_match = bool(docs.intersection(group.get("any_of_document_ids", [])))
        anchor_match = bool(evidence.intersection(group.get("any_of_evidence_ids", [])))
        rows.append(
            {
                "evidence_group_id": group["evidence_group_id"],
                "required": required,
                "document_match": document_match,
                "anchor_match": anchor_match,
                "document_pass": (not required) or document_match,
                "anchor_pass": (not required) or anchor_match,
            }
        )
    required_rows = [item for item in rows if item["required"]]
    return {
        "groups": rows,
        "required_group_count": len(required_rows),
        "document_groups_covered": sum(item["document_pass"] for item in required_rows),
        "anchor_groups_covered": sum(item["anchor_pass"] for item in required_rows),
        "document_pass": all(item["document_pass"] for item in required_rows),
        "anchor_pass": all(item["anchor_pass"] for item in required_rows),
    }


def evaluate_claim(claim: dict[str, Any], answer: str, answerable: bool, citation_count: int) -> dict[str, Any]:
    mode = claim["evaluation_mode"]
    row = {
        "claim_id": claim["claim_id"],
        "evaluation_mode": mode,
        "required": claim.get("required", False),
        "canonical_claim": claim["canonical_claim"],
    }
    if mode == "SEMANTIC_REVIEW":
        return {**row, "status": "REVIEW_REQUIRED", "machine_pass": None}
    if mode == "ANSWERABILITY_ONLY":
        passed = not answerable and citation_count == 0
        return {**row, "status": "PASS" if passed else "FAIL", "machine_pass": passed}
    terms = claim.get("deterministic_match", {}).get("all_terms", [])
    normalized = normalize_text(answer)
    matched = [term for term in terms if normalize_text(str(term)) in normalized]
    passed = bool(terms) and len(matched) == len(terms)
    return {
        **row,
        "status": "PASS" if passed else "FAIL",
        "machine_pass": passed,
        "all_terms": terms,
        "matched_terms": matched,
    }


def citation_evaluation(case: dict[str, Any], citations: list[dict[str, Any]]) -> dict[str, Any]:
    contract = case["citation_contract"]
    labels = [item.get("source_label") for item in citations]
    validity = all(
        item.get("chunk_id") is not None
        and item.get("material_id") is not None
        and item.get("document_id")
        and item.get("source_available", True)
        for item in citations
    )
    uniqueness = len(labels) == len(set(labels))
    forbidden_ok = not (contract.get("forbid_citations") and citations)
    required_ok = not contract.get("citation_required") or bool(citations)
    coverage = group_coverage(case.get("evidence_groups", []), citations)
    required_docs = {
        doc
        for group in case.get("evidence_groups", [])
        if group.get("required")
        for doc in group.get("any_of_document_ids", [])
    }
    distinct_required_docs = len(source_documents(citations).intersection(required_docs))
    minimum_ok = distinct_required_docs >= contract.get("minimum_distinct_required_documents", 0)
    acceptable_docs = {
        item["document_id"] for item in case.get("acceptable_supporting_evidence", [])
    }
    unsupported_docs = {
        item["document_id"] for item in case.get("plausible_distractor_documents", [])
    }
    citation_rows = []
    for citation in citations:
        document_id = citation.get("document_id")
        if document_id in required_docs:
            role = "REQUIRED"
        elif document_id in acceptable_docs:
            role = "ACCEPTABLE_SUPPORT"
        elif document_id in unsupported_docs:
            role = "UNSUPPORTED"
        else:
            role = "UNCLASSIFIED"
        citation_rows.append(
            {
                "source_label": citation.get("source_label"),
                "document_id": document_id,
                "evidence_role": role,
                "resolves": bool(
                    citation.get("chunk_id") is not None
                    and citation.get("material_id") is not None
                    and citation.get("source_available", True)
                ),
                "claim_support_status": (
                    "KNOWN_UNSUPPORTED" if role == "UNSUPPORTED" else "REVIEW_REQUIRED"
                ),
            }
        )
    unsupported_ok = all(item["evidence_role"] != "UNSUPPORTED" for item in citation_rows)
    overall = (
        validity
        and uniqueness
        and forbidden_ok
        and required_ok
        and minimum_ok
        and unsupported_ok
        and (not contract.get("citation_required") or coverage["document_pass"])
    )
    return {
        "citation_count": len(citations),
        "validity_pass": validity,
        "unique_source_labels_pass": uniqueness,
        "forbidden_citations_pass": forbidden_ok,
        "citation_presence_pass": required_ok,
        "minimum_distinct_required_documents": contract.get("minimum_distinct_required_documents", 0),
        "distinct_required_documents_cited": distinct_required_docs,
        "minimum_distinct_required_documents_pass": minimum_ok,
        "unsupported_document_citation_pass": unsupported_ok,
        "required_group_coverage": coverage,
        "semantic_support_status": "REVIEW_REQUIRED" if citations else "NOT_APPLICABLE",
        "citations": citation_rows,
        "machine_contract_pass": overall,
    }


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _breakdown(case_rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in case_rows:
        buckets[str(row["case_metadata"].get(key, "unknown"))].append(row)
    return {
        name: {
            "case_count": len(items),
            "candidate_document_group_recall": _rate(
                sum(item["retrieval_metrics"]["candidate"]["document_pass"] for item in items), len(items)
            ),
            "selected_document_group_recall": _rate(
                sum(item["retrieval_metrics"]["selected"]["document_pass"] for item in items), len(items)
            ),
            "answerability_accuracy": _rate(
                sum(item["answerability_metrics"]["pass"] for item in items), len(items)
            ),
            "citation_machine_contract_rate": _rate(
                sum(item["citation_metrics"]["machine_contract_pass"] for item in items), len(items)
            ),
        }
        for name, items in sorted(buckets.items())
    }


def compute(raw: dict[str, Any]) -> dict[str, Any]:
    case_rows = []
    claim_rows = []
    review_queue = []
    failures = []
    for record in raw["cases"]:
        case = record["gold_case"]
        response = record.get("response") or {}
        assistant = response.get("assistant_message") or {}
        answer = assistant.get("content") or ""
        answerable = bool(assistant.get("answerable"))
        citations = record.get("citations", [])
        candidates = record.get("diagnostic", {}).get("candidates", [])
        selected = record.get("retrieval", {}).get("selected_sources", [])
        candidate_coverage = group_coverage(case.get("evidence_groups", []), candidates)
        selected_coverage = group_coverage(case.get("evidence_groups", []), selected)
        citation_metrics = citation_evaluation(case, citations)
        expected_answerable = bool(case["answerable"])
        answerability_pass = answerable == expected_answerable
        claims = [evaluate_claim(item, answer, answerable, len(citations)) for item in case["claims"]]
        claim_rows.extend({"case_id": case["case_id"], **item} for item in claims)
        semantic_claims = [item for item in case["claims"] if item["evaluation_mode"] == "SEMANTIC_REVIEW"]
        if semantic_claims:
            review_queue.append(
                {
                    "case_run_id": record["case_run_id"],
                    "case_id": case["case_id"],
                    "question": case["question"],
                    "expected_answerable": expected_answerable,
                    "model_answerable": answerable,
                    "normalized_answer": answer,
                    "selected_context": selected,
                    "citations": citations,
                    "semantic_claims": semantic_claims,
                    "review_status": "PENDING_HUMAN_SEMANTIC_REVIEW",
                }
            )
        signals = []
        if not candidate_coverage["document_pass"]:
            signals.append("required_document_group_absent_from_diagnostic_candidates")
        if not selected_coverage["document_pass"]:
            signals.append("required_document_group_absent_from_selected_context")
        if expected_answerable != answerable:
            signals.append("answerability_mismatch")
        if any(item["machine_pass"] is False for item in claims):
            signals.append("deterministic_claim_mismatch")
        if semantic_claims:
            signals.append("semantic_review_required")
        if not citation_metrics["machine_contract_pass"]:
            signals.append("citation_machine_contract_mismatch")
        if record.get("execution_status") != "COMPLETED":
            signals.append("execution_not_completed")
        if signals:
            failures.append(
                {
                    "case_run_id": record["case_run_id"],
                    "case_id": case["case_id"],
                    "preliminary_signals": signals,
                    "root_cause_classification": None,
                    "classification_status": "DEFERRED_TO_FAILURE_ANALYSIS",
                    "diagnostic_candidates": candidates,
                    "selected_context": selected,
                    "response": response,
                }
            )
        row = {
            "sequence": record["sequence"],
            "case_run_id": record["case_run_id"],
            "case_id": case["case_id"],
            "execution_status": record.get("execution_status"),
            "case_metadata": {
                key: case.get(key)
                for key in ("tier", "case_type", "primary_topic", "difficulty", "query_language", "answerable")
            },
            "retrieval_metrics": {"candidate": candidate_coverage, "selected": selected_coverage},
            "claim_metrics": claims,
            "citation_metrics": citation_metrics,
            "answerability_metrics": {
                "expected": expected_answerable,
                "actual": answerable,
                "pass": answerability_pass,
                "refusal_reason": assistant.get("refusal_reason"),
            },
            "latency_metrics": record.get("latency", {}),
            "token_usage": record.get("generation", {}).get("aggregate_usage", {}),
            "preliminary_failure_signals": signals,
        }
        case_rows.append(row)

    n = len(case_rows)
    exact_claims = [item for item in claim_rows if item["evaluation_mode"] != "SEMANTIC_REVIEW"]
    semantic_claims = [item for item in claim_rows if item["evaluation_mode"] == "SEMANTIC_REVIEW"]
    latencies = [
        float(row["latency_metrics"].get("ask_http_ms", 0))
        for row in case_rows
        if row["latency_metrics"].get("ask_http_ms") is not None
    ]
    input_tokens = [row["token_usage"].get("input_tokens") or 0 for row in case_rows]
    output_tokens = [row["token_usage"].get("output_tokens") or 0 for row in case_rows]
    generation_latencies = [
        float(row["latency_metrics"].get("generation_observed_ms", 0))
        for row in case_rows
        if row["latency_metrics"].get("generation_observed_ms") is not None
    ]
    retrieval_metrics = {
        "case_count": n,
        "candidate_document_group_pass_count": sum(row["retrieval_metrics"]["candidate"]["document_pass"] for row in case_rows),
        "candidate_document_group_pass_rate": _rate(sum(row["retrieval_metrics"]["candidate"]["document_pass"] for row in case_rows), n),
        "candidate_anchor_group_pass_count": sum(row["retrieval_metrics"]["candidate"]["anchor_pass"] for row in case_rows),
        "candidate_anchor_group_pass_rate": _rate(sum(row["retrieval_metrics"]["candidate"]["anchor_pass"] for row in case_rows), n),
        "selected_document_group_pass_count": sum(row["retrieval_metrics"]["selected"]["document_pass"] for row in case_rows),
        "selected_document_group_pass_rate": _rate(sum(row["retrieval_metrics"]["selected"]["document_pass"] for row in case_rows), n),
        "selected_anchor_group_pass_count": sum(row["retrieval_metrics"]["selected"]["anchor_pass"] for row in case_rows),
        "selected_anchor_group_pass_rate": _rate(sum(row["retrieval_metrics"]["selected"]["anchor_pass"] for row in case_rows), n),
        "anchor_metrics_label": "diagnostic_runtime_chunk_mapping",
    }
    claim_metrics = {
        "claim_count": len(claim_rows),
        "by_evaluation_mode": dict(Counter(item["evaluation_mode"] for item in claim_rows)),
        "deterministic_claim_count": len(exact_claims),
        "deterministic_pass_count": sum(item["machine_pass"] is True for item in exact_claims),
        "deterministic_pass_rate": _rate(sum(item["machine_pass"] is True for item in exact_claims), len(exact_claims)),
        "semantic_review_claim_count": len(semantic_claims),
        "semantic_review_status": "REVIEW_REQUIRED",
        "semantic_machine_pass_rate": None,
        "rows": claim_rows,
    }
    citation_metrics = {
        "case_count": n,
        "machine_contract_pass_count": sum(row["citation_metrics"]["machine_contract_pass"] for row in case_rows),
        "machine_contract_pass_rate": _rate(sum(row["citation_metrics"]["machine_contract_pass"] for row in case_rows), n),
        "validity_pass_count": sum(row["citation_metrics"]["validity_pass"] for row in case_rows),
        "unsupported_document_citation_pass_count": sum(
            row["citation_metrics"]["unsupported_document_citation_pass"] for row in case_rows
        ),
        "required_group_document_coverage_pass_count": sum(row["citation_metrics"]["required_group_coverage"]["document_pass"] for row in case_rows),
        "semantic_support_status": "REVIEW_REQUIRED",
    }
    answerability_metrics = {
        "case_count": n,
        "accuracy_count": sum(row["answerability_metrics"]["pass"] for row in case_rows),
        "accuracy": _rate(sum(row["answerability_metrics"]["pass"] for row in case_rows), n),
        "unanswerable_case_count": sum(not row["answerability_metrics"]["expected"] for row in case_rows),
        "unanswerable_correct_refusal_count": sum(
            not row["answerability_metrics"]["expected"] and not row["answerability_metrics"]["actual"]
            for row in case_rows
        ),
        "answerable_case_count": sum(row["answerability_metrics"]["expected"] for row in case_rows),
        "answerable_response_count": sum(
            row["answerability_metrics"]["expected"] and row["answerability_metrics"]["actual"]
            for row in case_rows
        ),
    }
    latency_metrics = {
        "case_count": len(latencies),
        "ask_http_ms": {
            "mean": round(mean(latencies), 2) if latencies else None,
            "median": round(median(latencies), 2) if latencies else None,
            "p90": percentile(latencies, 0.90),
            "p95": percentile(latencies, 0.95),
            "max": round(max(latencies), 2) if latencies else None,
        },
        "generation_observed_ms": {
            "mean": round(mean(generation_latencies), 2) if generation_latencies else None,
            "median": round(median(generation_latencies), 2) if generation_latencies else None,
            "p95": percentile(generation_latencies, 0.95),
            "max": round(max(generation_latencies), 2) if generation_latencies else None,
        },
        "tokens": {
            "input_total": sum(input_tokens),
            "output_total": sum(output_tokens),
            "total": sum(input_tokens) + sum(output_tokens),
            "input_mean_per_case": round(mean(input_tokens), 2) if input_tokens else None,
            "input_p50": percentile([float(item) for item in input_tokens], 0.50),
            "input_p95": percentile([float(item) for item in input_tokens], 0.95),
            "output_mean_per_case": round(mean(output_tokens), 2) if output_tokens else None,
            "output_p50": percentile([float(item) for item in output_tokens], 0.50),
            "output_p95": percentile([float(item) for item in output_tokens], 0.95),
        },
    }
    breakdowns = {
        key: _breakdown(case_rows, key)
        for key in ("tier", "case_type", "primary_topic", "difficulty", "query_language")
    }
    return {
        "case_results": case_rows,
        "retrieval_metrics": retrieval_metrics,
        "claim_metrics": claim_metrics,
        "citation_metrics": citation_metrics,
        "answerability_metrics": answerability_metrics,
        "latency_metrics": latency_metrics,
        "breakdowns": breakdowns,
        "semantic_review_queue": {
            "semantic_claim_count": len(semantic_claims),
            "case_count": len(review_queue),
            "status": "PENDING_HUMAN_SEMANTIC_REVIEW",
            "items": review_queue,
        },
        "failure_traces": {
            "failure_signal_case_count": len(failures),
            "root_cause_classification_performed": False,
            "items": failures,
        },
    }


def render_summary(raw: dict[str, Any], metrics: dict[str, Any]) -> str:
    r = metrics["retrieval_metrics"]
    c = metrics["claim_metrics"]
    ci = metrics["citation_metrics"]
    a = metrics["answerability_metrics"]
    l = metrics["latency_metrics"]
    return f"""# LearnPilot RAG Real-world Dense-only Baseline V1 — Run Summary

- Run ID: `{raw['run_id']}`
- Completed cases: `{sum(item.get('execution_status') == 'COMPLETED' for item in raw['cases'])}/72`
- Candidate required-document group pass: `{r['candidate_document_group_pass_count']}/{r['case_count']}`
- Selected-context required-document group pass: `{r['selected_document_group_pass_count']}/{r['case_count']}`
- Selected-context diagnostic anchor group pass: `{r['selected_anchor_group_pass_count']}/{r['case_count']}`
- Deterministic claim pass: `{c['deterministic_pass_count']}/{c['deterministic_claim_count']}`
- Semantic claims: `{c['semantic_review_claim_count']}` (`REVIEW_REQUIRED`; no lexical proxy used)
- Citation machine-contract pass: `{ci['machine_contract_pass_count']}/{ci['case_count']}`
- Answerability accuracy: `{a['accuracy_count']}/{a['case_count']}`
- Ask latency p50 / p95: `{l['ask_http_ms']['median']} ms / {l['ask_http_ms']['p95']} ms`
- Total tokens: `{l['tokens']['total']}`

These results are the frozen AS-IS dense-only baseline. Failure traces contain preliminary
signals only; no root-cause classification or optimization is included.
"""


def build_artifacts(raw_path: Path, output_dir: Path) -> dict[str, Any]:
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    metrics = compute(raw)
    write_json(output_dir / "retrieval_metrics.json", metrics["retrieval_metrics"])
    write_json(output_dir / "claim_metrics.json", metrics["claim_metrics"])
    write_json(output_dir / "citation_metrics.json", metrics["citation_metrics"])
    write_json(output_dir / "answerability_metrics.json", metrics["answerability_metrics"])
    write_json(output_dir / "latency_metrics.json", metrics["latency_metrics"])
    write_json(output_dir / "case_results.json", {"cases": metrics["case_results"], "breakdowns": metrics["breakdowns"]})
    write_json(output_dir / "failure_traces.json", metrics["failure_traces"])
    write_json(output_dir / "semantic_review_queue.json", metrics["semantic_review_queue"])
    write_json(
        output_dir / "baseline_summary.json",
        {
            "run_id": raw["run_id"],
            "case_execution": {
                "expected": 72,
                "completed": sum(item.get("execution_status") == "COMPLETED" for item in raw["cases"]),
                "unique_case_run_ids": len({item["case_run_id"] for item in raw["cases"]}),
            },
            "retrieval": metrics["retrieval_metrics"],
            "claims": {key: value for key, value in metrics["claim_metrics"].items() if key != "rows"},
            "citations": metrics["citation_metrics"],
            "answerability": metrics["answerability_metrics"],
            "latency_and_tokens": metrics["latency_metrics"],
            "breakdowns": metrics["breakdowns"],
            "errors": {
                "case_error_count": sum(
                    bool(item.get("retry_and_error_summary", {}).get("error_count"))
                    for item in raw["cases"]
                ),
                "event_error_count": sum(
                    item.get("retry_and_error_summary", {}).get("error_count", 0)
                    for item in raw["cases"]
                ),
                "provider_retry_count": sum(
                    item.get("retry_and_error_summary", {}).get("provider_retries", 0)
                    for item in raw["cases"]
                ),
                "repair_case_count": sum(
                    bool(item.get("retry_and_error_summary", {}).get("repair_attempted"))
                    for item in raw["cases"]
                ),
                "fallback_case_count": sum(
                    bool((item.get("response") or {}).get("model", {}).get("fallback_used"))
                    for item in raw["cases"]
                ),
            },
        },
    )
    (output_dir / "baseline_summary.md").write_text(render_summary(raw, metrics), encoding="utf-8")
    return metrics


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("raw_results", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    build_artifacts(args.raw_results, args.output_dir or args.raw_results.parent)
