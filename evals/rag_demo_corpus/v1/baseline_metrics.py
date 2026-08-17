"""Pure, reproducible metric computation for LearnPilot RAG baseline runs."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from math import ceil
from pathlib import Path
import re
from statistics import mean, median
from typing import Any


CITATION_PATTERN = re.compile(r"\[(S\d+)\]")


def terms(text: str) -> set[str]:
    result = {
        item.lower()
        for item in re.findall(r"[A-Za-z][A-Za-z0-9_.-]+|\d+(?:\.\d+)?", text)
        if len(item) >= 2 or item.isdigit()
    }
    for sequence in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        result.update(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return result


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = ceil((len(ordered) - 1) * quantile)
    return round(ordered[index], 2)


def substantial_overlap(left: str, right: str) -> bool:
    first = " ".join(left.split())
    second = " ".join(right.split())
    if not first or not second:
        return False
    if first in second or second in first:
        return True
    max_width = min(240, len(first), len(second))
    return any(
        first[-width:] == second[:width] or second[-width:] == first[:width]
        for width in range(max_width, 59, -1)
    )


def reconstruct_context(
    search_results: list[dict[str, Any]],
    *,
    candidate_expansion: int,
    top_k: int,
    min_score: float,
    max_sources: int,
    max_chunk_chars: int,
    max_context_chars: int,
) -> dict[str, Any]:
    candidates = sorted(
        search_results[:candidate_expansion],
        key=lambda item: (
            -item["score"], item["material_id"], item["chunk_index"], item["chunk_id"]
        ),
    )
    above_threshold = [item for item in candidates if item["score"] >= min_score]
    unique: list[dict[str, Any]] = []
    for item in above_threshold:
        if any(
            prior["material_id"] == item["material_id"]
            and abs(prior["chunk_index"] - item["chunk_index"]) <= 1
            and substantial_overlap(prior["content"], item["content"])
            for prior in unique
        ):
            continue
        unique.append(item)
    per_material_cap = max(1, ceil(max_sources / 2))
    selected: list[dict[str, Any]] = []
    counts: Counter[int] = Counter()
    target = min(top_k, max_sources)
    for item in unique:
        if counts[item["material_id"]] >= per_material_cap:
            continue
        selected.append(item)
        counts[item["material_id"]] += 1
        if len(selected) >= target:
            break
    if len(selected) < target:
        for item in unique:
            if item in selected:
                continue
            selected.append(item)
            if len(selected) >= target:
                break
    final: list[dict[str, Any]] = []
    context_chars = 0
    for item in selected:
        content = item["content"][:max_chunk_chars]
        remaining = max_context_chars - context_chars
        if remaining <= 0:
            break
        content = content[:remaining]
        if not content.strip():
            continue
        final.append({**item, "context_content_chars": len(content)})
        context_chars += len(content)
    return {
        "candidate_sources": candidates,
        "above_threshold_sources": above_threshold,
        "deduplicated_sources": unique,
        "pre_budget_sources": selected,
        "selected_context_sources": final,
        "context_chars": context_chars,
    }


def document_ids(items: list[dict[str, Any]], filename_map: dict[str, str]) -> list[str]:
    return [
        filename_map[item["original_filename"]]
        for item in items
        if item.get("original_filename") in filename_map
    ]


def key_fact_result(facts: list[str], answer: str) -> list[dict[str, Any]]:
    answer_terms = terms(answer)
    results = []
    for fact in facts:
        fact_terms = terms(fact)
        score = len(fact_terms & answer_terms) / len(fact_terms) if fact_terms else 0.0
        results.append({"fact": fact, "coverage": round(score, 4), "covered": score >= 0.35})
    return results


def analyze_case(raw: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    case = raw["case"]
    expected = set(case["expected_document_ids"])
    filename_map = metadata["filename_to_document_id"]
    ask = raw["ask"]
    if ask["status_code"] != 200:
        return {
            "case_id": case["case_id"], "type": case["type"],
            "difficulty": case["difficulty"], "expected_answerable": case["answerable"],
            "executed": True, "http_ok": False, "passed": False,
            "failure_stage": "INFRASTRUCTURE", "latency_ms": ask["elapsed_ms"],
            "error": ask.get("response_text"),
        }
    body = ask["response_json"]
    assistant = body["assistant_message"]
    citations = assistant.get("citations", [])
    cited_docs = document_ids(citations, filename_map)
    inline = set(CITATION_PATTERN.findall(assistant.get("content", "")))
    declared = {item["source_label"] for item in citations}
    citation_valid = inline == declared and all(item.get("source_available") for item in citations)
    search_results = raw.get("diagnostic_search", {}).get("response_json", {}).get("results", [])
    reconstruction = reconstruct_context(
        search_results,
        candidate_expansion=metadata["rag_configuration"]["candidate_expansion"],
        top_k=metadata["rag_configuration"]["top_k"],
        min_score=metadata["rag_configuration"]["min_score"],
        max_sources=metadata["rag_configuration"]["max_sources"],
        max_chunk_chars=metadata["rag_configuration"]["max_chunk_chars"],
        max_context_chars=metadata["rag_configuration"]["max_context_chars"],
    )
    candidate_docs = document_ids(reconstruction["candidate_sources"], filename_map)
    threshold_docs = document_ids(reconstruction["above_threshold_sources"], filename_map)
    pre_budget_docs = document_ids(reconstruction["pre_budget_sources"], filename_map)
    context_docs = document_ids(reconstruction["selected_context_sources"], filename_map)
    top_k_docs = document_ids(
        search_results[: metadata["rag_configuration"]["top_k"]], filename_map
    )
    fact_results = key_fact_result(case["key_facts"], assistant.get("content", ""))
    fact_coverage = (
        mean(float(item["covered"]) for item in fact_results) if fact_results else 1.0
    )
    actual_answerable = assistant.get("answerable") is True
    answerability_correct = actual_answerable == case["answerable"]
    expected_citation_coverage = (
        len(expected & set(cited_docs)) / len(expected) if expected else 1.0
    )
    must_cite = set(case["citation_expectations"]["must_cite_document_ids"])
    missing_required_citation = not must_cite.issubset(cited_docs)
    unsupported_proxy = actual_answerable and (
        not citations or (bool(expected) and not (expected & set(cited_docs))) or not citation_valid
    )
    failure_stage = None
    if case["answerable"]:
        if not expected.issubset(threshold_docs):
            failure_stage = "RETRIEVAL_MISS"
        elif not expected.issubset(pre_budget_docs):
            failure_stage = "RANKING_OR_SELECTION"
        elif not expected.issubset(context_docs):
            failure_stage = "CONTEXT_BUDGET"
        elif not actual_answerable:
            failure_stage = "ANSWERABILITY"
        elif fact_coverage < 1.0:
            failure_stage = "GENERATION"
        elif not citation_valid or missing_required_citation:
            failure_stage = "CITATION"
    else:
        if actual_answerable:
            failure_stage = "ANSWERABILITY"
        elif citations:
            failure_stage = "CITATION"
    context_count_matches = len(reconstruction["selected_context_sources"]) == body["retrieval"]["source_count"]
    if not context_count_matches and failure_stage is None:
        failure_stage = "OTHER"
    passed = failure_stage is None and answerability_correct
    return {
        "case_id": case["case_id"], "type": case["type"],
        "difficulty": case["difficulty"], "expected_answerable": case["answerable"],
        "expected_document_ids": sorted(expected), "executed": True, "http_ok": True,
        "actual_answerable": actual_answerable, "answerability_correct": answerability_correct,
        "top_k_document_ids": top_k_docs,
        "candidate_document_ids": candidate_docs,
        "above_threshold_document_ids": threshold_docs,
        "pre_budget_document_ids": pre_budget_docs,
        "selected_context_document_ids": context_docs,
        "context_reconstruction_count_matches": context_count_matches,
        "cited_document_ids": cited_docs,
        "retrieval_hit_at_k": bool(expected & set(top_k_docs)) if expected else True,
        "retrieval_recall_at_k": len(expected & set(top_k_docs)) / len(expected) if expected else 1.0,
        "candidate_expected_recall": len(expected & set(threshold_docs)) / len(expected) if expected else 1.0,
        "context_expected_recall": len(expected & set(context_docs)) / len(expected) if expected else 1.0,
        "source_precision_at_k": len(expected & set(top_k_docs)) / len(set(top_k_docs)) if top_k_docs and expected else 1.0,
        "multi_document_coverage": expected.issubset(context_docs) if len(expected) > 1 else None,
        "key_fact_results": fact_results, "key_fact_coverage": fact_coverage,
        "citation_valid": citation_valid,
        "expected_document_citation_coverage": expected_citation_coverage,
        "missing_required_citation": missing_required_citation,
        "wrong_citation_count": len([item for item in cited_docs if item not in expected]),
        "citation_count": len(cited_docs),
        "unsupported_answer_proxy": unsupported_proxy,
        "fallback_used": body.get("model", {}).get("fallback_used", False),
        "refusal_reason": assistant.get("refusal_reason"),
        "latency_ms": ask["elapsed_ms"],
        "retrieval_latency_ms": body["retrieval"].get("duration_ms", 0),
        "answer_model_latency_ms": assistant.get("latency_ms") or 0,
        "passed": passed, "failure_stage": failure_stage,
        "answer": assistant.get("content", ""),
    }


def aggregate(items: list[dict[str, Any]], persistence: dict[str, Any] | None = None) -> dict[str, Any]:
    valid = [item for item in items if item["http_ok"]]
    answerable = [item for item in valid if item["expected_answerable"]]
    unanswerable = [item for item in valid if not item["expected_answerable"]]
    multi = [item for item in answerable if len(item.get("expected_document_ids", [])) > 1]
    citations_total = sum(item.get("citation_count", 0) for item in answerable)
    facts = [fact for item in answerable for fact in item.get("key_fact_results", [])]
    latencies = [item["latency_ms"] for item in items]
    by_type: dict[str, Any] = {}
    for case_type in sorted({item["type"] for item in items}):
        group = [item for item in items if item["type"] == case_type]
        by_type[case_type] = group_metrics(group)
    tokens = (persistence or {}).get("token_usage", {})
    return {
        "case_count": len(items), "executed_count": sum(item["executed"] for item in items),
        "pass_count": sum(item["passed"] for item in items),
        "pass_rate": mean(float(item["passed"]) for item in items),
        "retrieval": {
            "expected_document_hit_at_k": mean(float(item["retrieval_hit_at_k"]) for item in answerable) if answerable else 0.0,
            "expected_document_recall_at_k": mean(item["retrieval_recall_at_k"] for item in answerable) if answerable else 0.0,
            "candidate_expected_document_recall": mean(item["candidate_expected_recall"] for item in answerable) if answerable else 0.0,
            "selected_context_expected_document_recall": mean(item["context_expected_recall"] for item in answerable) if answerable else 0.0,
            "source_precision_at_k": mean(item["source_precision_at_k"] for item in answerable) if answerable else 0.0,
            "wrong_source_rate_at_k": 1 - (mean(item["source_precision_at_k"] for item in answerable) if answerable else 0.0),
            "multi_document_coverage": mean(float(item["multi_document_coverage"]) for item in multi) if multi else 0.0,
            "context_reconstruction_match_rate": mean(float(item["context_reconstruction_count_matches"]) for item in valid) if valid else 0.0,
        },
        "answer": {
            "answerable_success_rate": mean(float(item["actual_answerable"]) for item in answerable) if answerable else 0.0,
            "key_fact_coverage": mean(float(item["covered"]) for item in facts) if facts else 0.0,
            "unanswerable_refusal_accuracy": mean(float(not item["actual_answerable"]) for item in unanswerable) if unanswerable else 0.0,
            "unsupported_answer_proxy_rate": mean(float(item["unsupported_answer_proxy"]) for item in valid) if valid else 0.0,
        },
        "citation": {
            "citation_validity_rate": mean(float(item["citation_valid"]) for item in valid) if valid else 0.0,
            "expected_document_citation_coverage": mean(item["expected_document_citation_coverage"] for item in answerable) if answerable else 0.0,
            "wrong_document_citation_rate": sum(item["wrong_citation_count"] for item in answerable) / citations_total if citations_total else 0.0,
            "missing_citation_case_rate": mean(float(item["missing_required_citation"]) for item in answerable) if answerable else 0.0,
            "unanswerable_citation_case_rate": mean(float(bool(item["citation_count"])) for item in unanswerable) if unanswerable else 0.0,
        },
        "reliability": {
            "infrastructure_failure_rate": mean(float(not item["http_ok"]) for item in items),
            "generation_repair_failure_rate": mean(float(item.get("refusal_reason") == "grounded_answer_invalid") for item in valid) if valid else 0.0,
            "fallback_rate": mean(float(item.get("fallback_used", False)) for item in valid) if valid else 0.0,
            "latency_ms": {"average": round(mean(latencies), 2), "p50": round(median(latencies), 2), "p95": percentile(latencies, 0.95)},
            "token_usage": tokens,
            "cost": {"available": False, "reason": "Provider pricing is not exposed by the runtime; no cost estimate was fabricated."},
        },
        "failure_taxonomy": dict(sorted(Counter(item["failure_stage"] or "PASS" for item in items).items())),
        "by_type": by_type,
    }


def group_metrics(group: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [item for item in group if item["http_ok"]]
    return {
        "case_count": len(group),
        "pass_rate": mean(float(item["passed"]) for item in group),
        "answerability_accuracy": mean(float(item.get("answerability_correct", False)) for item in valid) if valid else 0.0,
        "retrieval_hit_at_k": mean(float(item.get("retrieval_hit_at_k", False)) for item in valid) if valid else 0.0,
        "context_expected_recall": mean(item.get("context_expected_recall", 0.0) for item in valid) if valid else 0.0,
        "citation_expected_coverage": mean(item.get("expected_document_citation_coverage", 0.0) for item in valid) if valid else 0.0,
        "key_fact_coverage": mean(item.get("key_fact_coverage", 0.0) for item in valid) if valid else 0.0,
        "latency_p50_ms": round(median(item["latency_ms"] for item in group), 2),
    }


def compute_run(raw_cases: list[dict[str, Any]], metadata: dict[str, Any], persistence: dict[str, Any] | None = None) -> dict[str, Any]:
    cases = [analyze_case(item, metadata) for item in raw_cases]
    aggregate_metrics = aggregate(cases, persistence)
    topics = metadata["document_topics"]
    by_topic: dict[str, Any] = {}
    for topic in sorted(set(topics.values()) | {"unanswerable"}):
        group = []
        for item, raw in zip(cases, raw_cases):
            expected = raw["case"]["expected_document_ids"]
            if (topic == "unanswerable" and not expected) or any(topics[doc] == topic for doc in expected):
                group.append(item)
        if group:
            by_topic[topic] = group_metrics(group)
    aggregate_metrics["by_topic"] = by_topic
    return {"aggregate": aggregate_metrics, "cases": cases}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def recompute(run_dir: Path) -> dict[str, Any]:
    raw = load_jsonl(run_dir / "raw_cases.jsonl")
    metadata = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
    persistence_path = run_dir / "persistence_audit.json"
    persistence = json.loads(persistence_path.read_text(encoding="utf-8")) if persistence_path.is_file() else None
    return compute_run(raw, metadata, persistence)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = recompute(args.run_dir)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
