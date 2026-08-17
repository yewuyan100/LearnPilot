from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import statistics
import sys
from ctypes import wintypes
from html import escape
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[4]
V1 = ROOT / "evals/rag_real_world_corpus/v1"
sys.path.insert(0, str(V1))

from canonical_model_path import resolve_canonical_reranker_model_path  # noqa: E402

RESULTS_ROOT = V1 / "results/c_v1_2_onnx_runtime_equivalence"
LOCAL_SITE = ROOT / ".tmp/c_v1_2_onnx_runtime/site-packages"
SNAPSHOT = resolve_canonical_reranker_model_path()
PHASE2 = V1 / "results/hybrid_rerank_phase2_v1_1/20260814T095542Z-1317c6a7"
PHASE3 = V1 / "results/hybrid_rerank_phase3_v1_1/20260814T123142Z-8852712b"
C_AUDIT = V1 / "results/c_v1_1_regression_latency_audit/20260814T142012Z-015c3ca0"
GOLD = V1 / "gold/v1/gold_cases.json"
PROFILE_CASE_IDS = (
    "rw-gold-v1-semantic-context-order",
    "rw-gold-v1-disambig-fastapi-async-deps",
)

sys.path.insert(0, str(LOCAL_SITE))
sys.path.insert(0, str(V1 / "hybrid_rerank_phase2_v1_1"))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def memory_snapshot() -> dict[str, Any]:
    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("page_fault_count", wintypes.DWORD),
            ("peak_working_set_size", ctypes.c_size_t),
            ("working_set_size", ctypes.c_size_t),
            ("quota_peak_paged_pool_usage", ctypes.c_size_t),
            ("quota_paged_pool_usage", ctypes.c_size_t),
            ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
            ("quota_non_paged_pool_usage", ctypes.c_size_t),
            ("pagefile_usage", ctypes.c_size_t),
            ("peak_pagefile_usage", ctypes.c_size_t),
            ("private_usage", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(Counters),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    ok = psapi.GetProcessMemoryInfo(
        kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    )
    if not ok:
        return {"reliable": False, "method": "GetProcessMemoryInfo_failed"}
    mb = lambda value: round(value / (1024 * 1024), 3)
    return {
        "reliable": True,
        "method": "Windows GetProcessMemoryInfo PROCESS_MEMORY_COUNTERS_EX",
        "working_set_mb": mb(counters.working_set_size),
        "peak_working_set_mb": mb(counters.peak_working_set_size),
        "private_usage_mb": mb(counters.private_usage),
    }


def percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower))


def distribution(values: Iterable[float]) -> dict[str, Any]:
    observed = [float(value) for value in values]
    if not observed:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "max": None}
    return {
        "count": len(observed),
        "mean": round(statistics.fmean(observed), 9),
        "p50": round(float(percentile(observed, 0.50)), 9),
        "p95": round(float(percentile(observed, 0.95)), 9),
        "max": round(max(observed), 9),
    }


def build_features(tokenizer: Any, trace: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from experiment import build_xlm_roberta_pair_feature, enforce_pair_token_budget

    candidates = sorted(trace["candidates"], key=lambda row: (int(row["dense_rank"]), row["identity"]))
    features = []
    pair_rows = []
    for candidate in candidates:
        query_ids = tokenizer.encode(trace["effective_query"], add_special_tokens=False)
        chunk_ids = tokenizer.encode(candidate["raw_text"], add_special_tokens=False)
        pair = enforce_pair_token_budget(
            query_ids,
            chunk_ids,
            special_token_count=tokenizer.num_special_tokens_to_add(pair=True),
        )
        features.append(build_xlm_roberta_pair_feature(tokenizer, pair))
        pair_rows.append(
            {
                "candidate_identity": candidate["identity"],
                "dense_rank": candidate["dense_rank"],
                "query_tokens": len(query_ids),
                "chunk_tokens": len(chunk_ids),
                "pair_tokens": pair.total_tokens,
                "frozen_pair_tokens": candidate["reranker_input_tokens"],
                "token_count_match": pair.total_tokens == candidate["reranker_input_tokens"],
                "truncated": pair.truncated,
            }
        )
    return features, {
        "case_id": trace["case_id"],
        "pair_count": len(pair_rows),
        "candidate_identities_dense_order": [row["identity"] for row in candidates],
        "pairs": pair_rows,
    }


def prepare_batch(tokenizer: Any, trace: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, float]]:
    started = perf_counter()
    features, audit = build_features(tokenizer, trace)
    tokenization_ms = (perf_counter() - started) * 1000.0
    started = perf_counter()
    batch = tokenizer.pad(features, padding=True, return_tensors="np")
    batch = {
        "input_ids": batch["input_ids"].astype("int64", copy=False),
        "attention_mask": batch["attention_mask"].astype("int64", copy=False),
    }
    preparation_ms = (perf_counter() - started) * 1000.0
    audit.update(
        {
            "input_ids_shape": list(batch["input_ids"].shape),
            "attention_mask_shape": list(batch["attention_mask"].shape),
            "input_ids_dtype": str(batch["input_ids"].dtype),
            "attention_mask_dtype": str(batch["attention_mask"].dtype),
            "input_ids_sha256": hashlib.sha256(batch["input_ids"].tobytes()).hexdigest(),
            "attention_mask_sha256": hashlib.sha256(
                batch["attention_mask"].tobytes()
            ).hexdigest(),
            "all_frozen_pair_token_counts_match": all(
                row["token_count_match"] for row in audit["pairs"]
            ),
            "truncation_count": sum(row["truncated"] for row in audit["pairs"]),
        }
    )
    return batch, audit, {
        "tokenization_feature_assembly_ms": tokenization_ms,
        "tensor_input_preparation_ms": preparation_ms,
    }


def stable_order(candidates: list[dict[str, Any]], scores: list[float]) -> list[dict[str, Any]]:
    return sorted(
        [
            {"candidate": candidate, "score": float(score)}
            for candidate, score in zip(candidates, scores, strict=True)
        ],
        key=lambda row: (
            -row["score"],
            int(row["candidate"]["dense_rank"]),
            row["candidate"]["identity"],
        ),
    )


def govern(ordered: list[dict[str, Any]]) -> list[Any]:
    from experiment import Candidate, govern_evidence

    candidates = []
    for rank, row in enumerate(ordered, start=1):
        source = row["candidate"]
        candidates.append(
            Candidate(
                identity=source["identity"],
                document_id=source["document_id"],
                chunk_index=source["chunk_index"],
                content_hash=source["content_hash"],
                filename=source["filename"],
                page_number=source["page_number"],
                section_title=source["section_title"],
                raw_text=source["raw_text"],
                material_id=source["material_id"],
                chunk_id=source["chunk_id"],
                evidence_ids=tuple(source["evidence_ids"]),
                arm="C",
                dense_score=source["dense_score"],
                dense_rank=source["dense_rank"],
                branch_admitted_dense=source["branch_admitted_dense"],
                dense_fusion_rank=source["dense_fusion_rank"],
                candidate_admitted=source["candidate_admitted"],
                reranker_score=row["score"],
                reranker_rank=rank,
                reranker_truncated=source["reranker_truncated"],
                reranker_input_tokens=source["reranker_input_tokens"],
            )
        )
    return govern_evidence(candidates)


def context_text(selected: list[Any]) -> str:
    parts = []
    for index, candidate in enumerate(selected, start=1):
        location = (
            f"第 {candidate.page_number} 页"
            if candidate.page_number is not None
            else candidate.section_title or f"片段 {candidate.chunk_index + 1}"
        )
        parts.append(
            f'<source id="S{index}" trust="untrusted-data">\n'
            f"<filename>{escape(candidate.filename)}</filename>\n"
            f"<location>{escape(location)}</location>\n"
            "<content>\n"
            f"{escape(candidate.raw_text)}\n"
            "</content>\n"
            "</source>"
        )
    return "\n\n".join(parts)


def evidence_coverage(gold: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for group in gold["evidence_groups"]:
        if not group["required"]:
            continue
        document_match = any(
            candidate["document_id"] in group["any_of_document_ids"] for candidate in candidates
        )
        anchor_match = any(
            set(candidate["evidence_ids"]) & set(group["any_of_evidence_ids"])
            for candidate in candidates
        )
        rows.append(
            {
                "evidence_group_id": group["evidence_group_id"],
                "document_match": document_match,
                "anchor_match": anchor_match,
            }
        )
    return {
        "groups": rows,
        "document_groups_covered": sum(row["document_match"] for row in rows),
        "anchor_groups_covered": sum(row["anchor_match"] for row in rows),
    }


def run_profile_call(
    session: Any,
    tokenizer: Any,
    trace: dict[str, Any],
    *,
    phase: str,
    index: int,
) -> tuple[dict[str, Any], list[float]]:
    total_started = perf_counter()
    batch, input_audit, preparation = prepare_batch(tokenizer, trace)
    started = perf_counter()
    output = session.run(["logits"], batch)[0]
    forward_ms = (perf_counter() - started) * 1000.0
    started = perf_counter()
    scores = output.reshape(-1).astype("float64").tolist()
    candidates = sorted(trace["candidates"], key=lambda row: (int(row["dense_rank"]), row["identity"]))
    order = stable_order(candidates, scores)
    extraction_ms = (perf_counter() - started) * 1000.0
    total_ms = (perf_counter() - total_started) * 1000.0
    component_sum = (
        preparation["tokenization_feature_assembly_ms"]
        + preparation["tensor_input_preparation_ms"]
        + forward_ms
        + extraction_ms
    )
    return (
        {
            "phase": phase,
            "index": index,
            "case_id": trace["case_id"],
            "pair_count": len(scores),
            "output_shape": list(output.shape),
            **{key: round(value, 6) for key, value in preparation.items()},
            "session_forward_ms": round(forward_ms, 6),
            "score_extraction_sorting_ms": round(extraction_ms, 6),
            "other_timer_residual_ms": round(max(0.0, total_ms - component_sum), 6),
            "total_reranker_call_ms": round(total_ms, 6),
            "ranking_order": [row["candidate"]["identity"] for row in order],
            "input_audit": input_audit,
        },
        scores,
    )


def near_tie_analysis(traces: list[dict[str, Any]]) -> dict[str, Any]:
    margins = []
    for trace in traces:
        ordered = sorted(trace["candidates"], key=lambda row: int(row["reranker_rank"]))
        for left, right in zip(ordered, ordered[1:]):
            margin = float(left["reranker_score"]) - float(right["reranker_score"])
            margins.append(
                {
                    "case_id": trace["case_id"],
                    "higher_identity": left["identity"],
                    "higher_rank": left["reranker_rank"],
                    "higher_score": left["reranker_score"],
                    "lower_identity": right["identity"],
                    "lower_rank": right["reranker_rank"],
                    "lower_score": right["reranker_score"],
                    "margin": margin,
                }
            )
    values = [row["margin"] for row in margins]
    minimum = min(margins, key=lambda row: row["margin"])
    epsilons = [0.000001, 0.00001, 0.0001, 0.001, 0.01]
    return {
        "adjacent_pair_count": len(margins),
        "minimum_adjacent_score_margin": minimum,
        "margin_distribution": {
            "p1": percentile(values, 0.01),
            "p5": percentile(values, 0.05),
            "p50": percentile(values, 0.50),
            "max": max(values),
        },
        "descriptive_near_tie_counts": {
            f"margin_lte_{epsilon:g}": sum(value <= epsilon for value in values)
            for epsilon in epsilons
        },
        "threshold_caveat": "descriptive epsilons only; no production threshold was created",
        "rows": margins,
    }


def main() -> None:
    latest = read_json(RESULTS_ROOT / "latest_run.json")
    if latest["status"] != "EXPORT_PASS_EQUIVALENCE_PENDING":
        raise SystemExit("latest run is not awaiting equivalence")
    run_dir = ROOT / latest["run_directory"]
    onnx_path = run_dir / "model/bge-reranker-v2-m3-fp32.onnx"
    traces = read_jsonl(PHASE2 / "arm_C/candidate_traces.jsonl")
    if len(traces) != 72 or sum(len(trace["candidates"]) for trace in traces) != 1296:
        raise SystemExit("frozen C trace coverage is not 72 x 18")
    traces_by_id = {trace["case_id"]: trace for trace in traces}
    contexts = {
        row["case_id"]: row
        for row in read_json(PHASE3 / "context_freeze.json")["records"]
        if row["arm"] == "C"
    }
    gold_by_id = {row["case_id"]: row for row in read_json(GOLD)["cases"]}

    memory_baseline = memory_snapshot()
    import numpy as np
    import onnxruntime as ort
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        str(SNAPSHOT), local_files_only=True, trust_remote_code=False
    )
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.intra_op_num_threads = 8
    options.inter_op_num_threads = 1
    options.enable_cpu_mem_arena = True
    options.enable_mem_pattern = True
    session_started = perf_counter()
    try:
        session = ort.InferenceSession(
            str(onnx_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
    except Exception as exc:
        blocker = {
            "status": "BLOCKED",
            "classification": "D. ONNX_FP32_RUNTIME_BLOCKED",
            "stage": "session_initialization",
            "exception_type": type(exc).__name__,
            "exception": str(exc),
            "external_calls": 0,
        }
        write_json(run_dir / "runtime_blocker.json", blocker)
        latest["status"] = "RUNTIME_BLOCKED_FINALIZATION_PENDING"
        write_json(RESULTS_ROOT / "latest_run.json", latest)
        print(json.dumps(blocker, indent=2))
        return
    session_load_seconds = perf_counter() - session_started
    memory_after_session_load = memory_snapshot()
    print(
        json.dumps(
            {"stage": "session_loaded", "session_load_seconds": round(session_load_seconds, 3)}
        ),
        flush=True,
    )

    checkpoint_path = run_dir / "equivalence_checkpoint.json"
    if checkpoint_path.exists():
        checkpoint = read_json(checkpoint_path)
        if checkpoint.get("run_id") != latest["c_v1_2_run_id"]:
            raise SystemExit("equivalence checkpoint belongs to a different run")
        session_load_seconds = checkpoint["representative_session_load_seconds"]
        memory_baseline = checkpoint["representative_memory_baseline"]
        memory_after_session_load = checkpoint["representative_memory_after_session_load"]
        profile_measurements = checkpoint["profile_measurements"]
        input_audits = checkpoint["input_audits"]
        pair_comparisons = checkpoint["pair_comparisons"]
        query_comparisons = checkpoint["query_comparisons"]
        full_latency = checkpoint["full_latency"]
        ordering_mismatches = checkpoint["ordering_mismatches"]
        governance_mismatches = checkpoint["governance_mismatches"]
        context_mismatches = checkpoint["context_mismatches"]
        required_evidence_regressions = checkpoint["required_evidence_regressions"]
        memory_samples = checkpoint["memory_samples"]
        print(
            json.dumps(
                {
                    "stage": "checkpoint_resumed",
                    "queries_complete": len(query_comparisons),
                    "queries_total": len(traces),
                }
            ),
            flush=True,
        )
    else:
        profile_measurements = []
        first, _ = run_profile_call(
            session,
            tokenizer,
            traces_by_id[PROFILE_CASE_IDS[0]],
            phase="first_inference_after_session_load",
            index=1,
        )
        profile_measurements.append(first)
        warm_sequence = (
            PROFILE_CASE_IDS[1],
            PROFILE_CASE_IDS[0],
            PROFILE_CASE_IDS[1],
            PROFILE_CASE_IDS[0],
        )
        for index, case_id in enumerate(warm_sequence, start=1):
            measurement, _ = run_profile_call(
                session,
                tokenizer,
                traces_by_id[case_id],
                phase="warm_repeated_inference",
                index=index,
            )
            profile_measurements.append(measurement)
        print(
            json.dumps(
                {
                    "stage": "profile_complete",
                    "first_total_ms": profile_measurements[0]["total_reranker_call_ms"],
                    "warm_calls": 4,
                }
            ),
            flush=True,
        )
        input_audits = []
        pair_comparisons = []
        query_comparisons = []
        full_latency = []
        ordering_mismatches = []
        governance_mismatches = []
        context_mismatches = []
        required_evidence_regressions = []
        memory_samples = [memory_baseline, memory_after_session_load]

    def save_checkpoint(*, complete: bool = False) -> None:
        write_json(
            checkpoint_path,
            {
                "run_id": latest["c_v1_2_run_id"],
                "complete": complete,
                "representative_session_load_seconds": session_load_seconds,
                "representative_memory_baseline": memory_baseline,
                "representative_memory_after_session_load": memory_after_session_load,
                "profile_measurements": profile_measurements,
                "input_audits": input_audits,
                "pair_comparisons": pair_comparisons,
                "query_comparisons": query_comparisons,
                "full_latency": full_latency,
                "ordering_mismatches": ordering_mismatches,
                "governance_mismatches": governance_mismatches,
                "context_mismatches": context_mismatches,
                "required_evidence_regressions": required_evidence_regressions,
                "memory_samples": memory_samples,
            },
        )

    if not checkpoint_path.exists():
        save_checkpoint()
    completed_case_ids = {row["case_id"] for row in query_comparisons}
    for trace in traces:
        if trace["case_id"] in completed_case_ids:
            continue
        measurement, scores = run_profile_call(
            session, tokenizer, trace, phase="full_72_query_equivalence", index=len(full_latency) + 1
        )
        input_audit = measurement.pop("input_audit")
        input_audits.append(input_audit)
        full_latency.append(measurement)
        memory_samples.append(memory_snapshot())
        candidates = sorted(trace["candidates"], key=lambda row: (int(row["dense_rank"]), row["identity"]))
        onnx_order_rows = stable_order(candidates, scores)
        onnx_order = [row["candidate"]["identity"] for row in onnx_order_rows]
        pytorch_order = [
            row["identity"] for row in sorted(candidates, key=lambda row: int(row["reranker_rank"]))
        ]
        onnx_rank = {identity: rank for rank, identity in enumerate(onnx_order, start=1)}
        for candidate, onnx_score in zip(candidates, scores, strict=True):
            pytorch_score = float(candidate["reranker_score"])
            absolute = abs(float(onnx_score) - pytorch_score)
            pair_comparisons.append(
                {
                    "case_id": trace["case_id"],
                    "candidate_identity": candidate["identity"],
                    "dense_rank": candidate["dense_rank"],
                    "pytorch_score": pytorch_score,
                    "onnx_score": float(onnx_score),
                    "absolute_difference": absolute,
                    "relative_difference": absolute / abs(pytorch_score)
                    if abs(pytorch_score) > 0.000001
                    else None,
                    "pytorch_rank": candidate["reranker_rank"],
                    "onnx_rank": onnx_rank[candidate["identity"]],
                    "rank_equal": candidate["reranker_rank"] == onnx_rank[candidate["identity"]],
                }
            )
        order_equal = onnx_order == pytorch_order
        if not order_equal:
            displaced = [
                row
                for row in pair_comparisons[-18:]
                if row["pytorch_rank"] != row["onnx_rank"]
            ]
            ordering_mismatches.append(
                {
                    "case_id": trace["case_id"],
                    "pytorch_order": pytorch_order,
                    "onnx_order": onnx_order,
                    "displaced_candidates": displaced,
                }
            )

        selected = govern(onnx_order_rows)
        selected_identities = [candidate.identity for candidate in selected]
        frozen_selected = list(trace["selected"])
        top6_equal = selected_identities == frozen_selected
        if not top6_equal:
            governance_mismatches.append(
                {
                    "case_id": trace["case_id"],
                    "pytorch_top6": frozen_selected,
                    "onnx_top6": selected_identities,
                }
            )
        built_context = context_text(selected)
        built_digest = text_sha256(built_context)
        frozen_context = contexts[trace["case_id"]]
        context_equal = (
            built_context == frozen_context["context_text"]
            and built_digest == frozen_context["context_digest"]
        )
        if not context_equal:
            context_mismatches.append(
                {
                    "case_id": trace["case_id"],
                    "pytorch_context_digest": frozen_context["context_digest"],
                    "onnx_context_digest": built_digest,
                }
            )
        frozen_selected_rows = [
            next(candidate for candidate in candidates if candidate["identity"] == identity)
            for identity in frozen_selected
        ]
        onnx_selected_rows = [candidate.to_dict() for candidate in selected]
        frozen_coverage = evidence_coverage(gold_by_id[trace["case_id"]], frozen_selected_rows)
        onnx_coverage = evidence_coverage(gold_by_id[trace["case_id"]], onnx_selected_rows)
        coverage_equal = frozen_coverage == onnx_coverage
        if not coverage_equal:
            required_evidence_regressions.append(
                {
                    "case_id": trace["case_id"],
                    "pytorch": frozen_coverage,
                    "onnx": onnx_coverage,
                }
            )
        query_comparisons.append(
            {
                "case_id": trace["case_id"],
                "pair_count": 18,
                "reranker_order_equal": order_equal,
                "pytorch_order": pytorch_order,
                "onnx_order": onnx_order,
                "governed_top6_equal": top6_equal,
                "pytorch_top6": frozen_selected,
                "onnx_top6": selected_identities,
                "context_equal": context_equal,
                "pytorch_context_digest": frozen_context["context_digest"],
                "onnx_context_digest": built_digest,
                "required_evidence_presence_equal": coverage_equal,
                "pytorch_required_evidence": frozen_coverage,
                "onnx_required_evidence": onnx_coverage,
            }
        )
        if len(full_latency) % 10 == 0 or len(full_latency) == len(traces):
            print(
                json.dumps(
                    {
                        "stage": "full_equivalence_progress",
                        "queries_complete": len(full_latency),
                        "queries_total": len(traces),
                    }
                ),
                flush=True,
            )
        if len(full_latency) % 5 == 0 or len(full_latency) == len(traces):
            save_checkpoint()

    near_ties = near_tie_analysis(traces)
    deterministic_case_id = near_ties["minimum_adjacent_score_margin"]["case_id"]
    deterministic_trace = traces_by_id[deterministic_case_id]
    deterministic_scores = []
    deterministic_orders = []
    for index in range(3):
        measurement, scores = run_profile_call(
            session,
            tokenizer,
            deterministic_trace,
            phase="near_tie_determinism_repeat",
            index=index + 1,
        )
        candidates = sorted(
            deterministic_trace["candidates"],
            key=lambda row: (int(row["dense_rank"]), row["identity"]),
        )
        deterministic_scores.append(scores)
        deterministic_orders.append(
            [row["candidate"]["identity"] for row in stable_order(candidates, scores)]
        )
        memory_samples.append(memory_snapshot())
    deterministic_bitwise = all(
        np.array_equal(np.array(deterministic_scores[0]), np.array(scores))
        for scores in deterministic_scores[1:]
    )
    deterministic_order = all(
        order == deterministic_orders[0] for order in deterministic_orders[1:]
    )
    save_checkpoint(complete=True)

    absolute_differences = [row["absolute_difference"] for row in pair_comparisons]
    relative_differences = [
        row["relative_difference"]
        for row in pair_comparisons
        if row["relative_difference"] is not None
    ]
    score_stats = {
        "pair_count": len(pair_comparisons),
        "absolute_difference": {
            **distribution(absolute_differences),
            "p99": percentile(absolute_differences, 0.99),
            "minimum": min(absolute_differences),
        },
        "relative_difference_where_abs_pytorch_gt_1e_6": {
            **distribution(relative_differences),
            "p99": percentile(relative_differences, 0.99),
            "minimum": min(relative_differences),
        },
        "maximum_difference_row": max(
            pair_comparisons, key=lambda row: row["absolute_difference"]
        ),
        "exact_score_count": sum(value == 0.0 for value in absolute_differences),
        "score_equality_is_secondary": True,
    }
    component_names = (
        "tokenization_feature_assembly_ms",
        "tensor_input_preparation_ms",
        "session_forward_ms",
        "score_extraction_sorting_ms",
        "other_timer_residual_ms",
        "total_reranker_call_ms",
    )
    warm = [row for row in profile_measurements if row["phase"] == "warm_repeated_inference"]
    onnx_warm_summary = {
        name: distribution(row[name] for row in warm) for name in component_names
    }
    onnx_full_summary = {
        name: distribution(row[name] for row in full_latency) for name in component_names
    }
    pytorch_audit = read_json(C_AUDIT / "reranker_microprofile.json")
    pytorch_warm = pytorch_audit["warm_summary_ms"]
    latency = {
        "session_load_seconds": round(session_load_seconds, 6),
        "first_inference": profile_measurements[0],
        "warm_methodology": (
            "one first inference after session load, then four alternating repeats over the same two "
            "frozen cases used by the C V1.1 PyTorch audit"
        ),
        "onnx_profile_measurements": profile_measurements,
        "onnx_warm_summary_ms": onnx_warm_summary,
        "onnx_full_72_query_summary_ms": onnx_full_summary,
        "pytorch_reference_source": (
            "C V1.1 audit 20260814T142012Z-015c3ca0; exact same machine, model, tokenizer, and two profile cases"
        ),
        "pytorch_model_load_seconds": pytorch_audit["model_runtime"]["model_load_seconds_diagnostic"],
        "pytorch_first_inference_ms": pytorch_audit["measurements"][0]["total_reranker_call_ms"],
        "pytorch_warm_summary_ms": pytorch_warm,
        "paired_representative_total_p50_speedup": round(
            pytorch_warm["total_reranker_call_ms"]["p50"]
            / onnx_warm_summary["total_reranker_call_ms"]["p50"],
            6,
        ),
        "paired_representative_forward_p50_speedup": round(
            pytorch_warm["forward_ms"]["p50"]
            / onnx_warm_summary["session_forward_ms"]["p50"],
            6,
        ),
        "historical_phase2_p50_ms": 8415.8549,
        "historical_phase2_to_onnx_full_p50_speedup": round(
            8415.8549 / onnx_full_summary["total_reranker_call_ms"]["p50"], 6
        ),
        "download_and_export_excluded": True,
    }
    reliable_memory = [row for row in memory_samples if row.get("reliable")]
    memory = {
        "method": "Windows GetProcessMemoryInfo PROCESS_MEMORY_COUNTERS_EX",
        "baseline_before_onnxruntime_import_and_session": memory_baseline,
        "after_onnx_session_load": memory_after_session_load,
        "after_all_inference": memory_snapshot(),
        "maximum_observed_working_set_mb": max(
            row["working_set_mb"] for row in reliable_memory
        )
        if reliable_memory
        else None,
        "maximum_observed_private_usage_mb": max(
            row["private_usage_mb"] for row in reliable_memory
        )
        if reliable_memory
        else None,
        "process_peak_working_set_mb_after_inference": memory_snapshot().get(
            "peak_working_set_mb"
        ),
        "sampling_caveat": (
            "working/private samples are taken after calls; process peak is OS-reported and includes session initialization"
        ),
    }
    input_equivalence = {
        "query_count": len(input_audits),
        "pair_count": sum(row["pair_count"] for row in input_audits),
        "candidate_depth": 18,
        "all_candidate_orders_match_frozen_dense_order": all(
            row["candidate_identities_dense_order"]
            == [
                candidate["identity"]
                for candidate in sorted(
                    traces_by_id[row["case_id"]]["candidates"],
                    key=lambda candidate: (int(candidate["dense_rank"]), candidate["identity"]),
                )
            ]
            for row in input_audits
        ),
        "all_frozen_pair_token_counts_match": all(
            row["all_frozen_pair_token_counts_match"] for row in input_audits
        ),
        "truncation_count": sum(row["truncation_count"] for row in input_audits),
        "input_names": [item.name for item in session.get_inputs()],
        "output_names": [item.name for item in session.get_outputs()],
        "rows": input_audits,
    }
    semantic = {
        "semantic_equivalence": "PASS"
        if not ordering_mismatches
        and not governance_mismatches
        and not context_mismatches
        and not required_evidence_regressions
        else "FAIL",
        "pair_count": len(pair_comparisons),
        "query_count": len(query_comparisons),
        "reranker_order_exact_count": sum(
            row["reranker_order_equal"] for row in query_comparisons
        ),
        "governed_top6_exact_count": sum(
            row["governed_top6_equal"] for row in query_comparisons
        ),
        "context_digest_exact_count": sum(row["context_equal"] for row in query_comparisons),
        "required_evidence_presence_exact_count": sum(
            row["required_evidence_presence_equal"] for row in query_comparisons
        ),
        "ordering_mismatches": ordering_mismatches,
        "governance_mismatches": governance_mismatches,
        "context_mismatches": context_mismatches,
        "required_evidence_regressions": required_evidence_regressions,
        "near_tie_determinism": {
            "case_id": deterministic_case_id,
            "repeat_count": 3,
            "scores_bitwise_deterministic": deterministic_bitwise,
            "orders_deterministic": deterministic_order,
            "tie_break_rule": "upstream Dense rank then stable identity",
        },
        "existing_c_v1_1_semantic_evaluation_remains_authoritative": (
            not ordering_mismatches and not governance_mismatches and not context_mismatches
        ),
    }
    write_json(run_dir / "input_equivalence.json", input_equivalence)
    write_json(
        run_dir / "per_pair_score_comparison.json",
        {"score_difference_statistics": score_stats, "rows": pair_comparisons},
    )
    write_json(
        run_dir / "per_query_ranking_comparison.json",
        {"summary": semantic, "rows": query_comparisons},
    )
    write_json(
        run_dir / "governance_context_comparison.json",
        {
            "governed_top6_exact_count": semantic["governed_top6_exact_count"],
            "context_digest_exact_count": semantic["context_digest_exact_count"],
            "required_evidence_presence_exact_count": semantic[
                "required_evidence_presence_exact_count"
            ],
            "governance_mismatches": governance_mismatches,
            "context_mismatches": context_mismatches,
            "required_evidence_regressions": required_evidence_regressions,
        },
    )
    write_json(run_dir / "near_tie_analysis.json", near_ties)
    write_json(run_dir / "latency_measurements.json", latency)
    write_json(run_dir / "memory_measurements.json", memory)
    write_json(run_dir / "semantic_equivalence.json", semantic)
    runtime = read_json(run_dir / "runtime_manifest.json")
    runtime.update(
        {
            "status": "EQUIVALENCE_COMPLETE_FINALIZATION_PENDING",
            "session_observed": {
                "providers": session.get_providers(),
                "provider_options": session.get_provider_options(),
                "inputs": [
                    {"name": item.name, "shape": item.shape, "type": item.type}
                    for item in session.get_inputs()
                ],
                "outputs": [
                    {"name": item.name, "shape": item.shape, "type": item.type}
                    for item in session.get_outputs()
                ],
                "logical_cpu_count": os.cpu_count(),
                "intra_op_num_threads": 8,
                "inter_op_num_threads": 1,
                "execution_mode": "ORT_SEQUENTIAL",
                "graph_optimization_level": "ORT_ENABLE_ALL",
            },
        }
    )
    write_json(run_dir / "runtime_manifest.json", runtime)
    state = read_json(run_dir / "run_state.json")
    state.update(
        {
            "status": "EQUIVALENCE_COMPLETE_FINALIZATION_PENDING",
            "semantic_equivalence": semantic["semantic_equivalence"],
            "successful_process_onnx_inference_calls": 5 + 72 + 3,
            "successful_process_onnx_pairs_scored": (5 + 72 + 3) * 18,
            "orchestration_timeout_attempts_before_checkpointing": 2,
            "checkpoint_initialization_failure_attempts": 1,
            "checkpoint_initialization_failure_onnx_inference_calls": 5,
            "first_timeout_onnx_inference_calls": "unavailable",
            "second_timeout_known_minimum_onnx_inference_calls": 65,
        }
    )
    write_json(run_dir / "run_state.json", state)
    latest["status"] = "EQUIVALENCE_COMPLETE_FINALIZATION_PENDING"
    write_json(RESULTS_ROOT / "latest_run.json", latest)
    print(
        json.dumps(
            {
                "status": "PASS",
                "semantic_equivalence": semantic["semantic_equivalence"],
                "reranker_order_exact": semantic["reranker_order_exact_count"],
                "top6_exact": semantic["governed_top6_exact_count"],
                "context_exact": semantic["context_digest_exact_count"],
                "maximum_absolute_score_difference": score_stats[
                    "absolute_difference"
                ]["max"],
                "session_load_seconds": latency["session_load_seconds"],
                "onnx_warm_total_p50_ms": onnx_warm_summary[
                    "total_reranker_call_ms"
                ]["p50"],
                "onnx_full_total_p50_ms": onnx_full_summary[
                    "total_reranker_call_ms"
                ]["p50"],
                "paired_speedup": latency["paired_representative_total_p50_speedup"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
