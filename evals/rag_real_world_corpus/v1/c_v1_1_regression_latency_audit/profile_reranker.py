from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import statistics
import sys
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[4]
V1 = ROOT / "evals/rag_real_world_corpus/v1"
sys.path.insert(0, str(V1))

from canonical_model_path import resolve_canonical_reranker_model_path  # noqa: E402

RESULTS_ROOT = V1 / "results/c_v1_1_regression_latency_audit"
PHASE2_RUN_ID = "20260814T095542Z-1317c6a7"
PHASE2 = V1 / f"results/hybrid_rerank_phase2_v1_1/{PHASE2_RUN_ID}"
SNAPSHOT = resolve_canonical_reranker_model_path()
MODEL_SHA = "d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286"
REPRESENTATIVE_CASE_IDS = (
    "rw-gold-v1-semantic-context-order",
    "rw-gold-v1-disambig-fastapi-async-deps",
)

sys.path.insert(0, str(V1 / "hybrid_rerank_phase2_v1_1"))
from experiment import (  # noqa: E402
    HuggingFaceRerankerAdapter,
    build_xlm_roberta_pair_feature,
    enforce_pair_token_budget,
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


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
        "mean": round(statistics.fmean(observed), 6),
        "p50": round(float(percentile(observed, 0.50)), 6),
        "p95": round(float(percentile(observed, 0.95)), 6),
        "max": round(max(observed), 6),
    }


def profile_once(adapter: Any, trace: dict[str, Any], *, phase: str, index: int) -> dict[str, Any]:
    import torch

    candidates = sorted(trace["candidates"], key=lambda row: int(row["dense_rank"]))
    query = trace["effective_query"]
    total_started = perf_counter()
    tokenization_ms = 0.0
    feature_assembly_ms = 0.0
    features = []
    pairs = []
    for candidate in candidates:
        started = perf_counter()
        query_ids = adapter.tokenizer.encode(query, add_special_tokens=False)
        chunk_ids = adapter.tokenizer.encode(candidate["raw_text"], add_special_tokens=False)
        tokenization_ms += (perf_counter() - started) * 1000.0

        started = perf_counter()
        pair = enforce_pair_token_budget(
            query_ids,
            chunk_ids,
            special_token_count=adapter.tokenizer.num_special_tokens_to_add(pair=True),
        )
        features.append(build_xlm_roberta_pair_feature(adapter.tokenizer, pair))
        pairs.append(pair)
        feature_assembly_ms += (perf_counter() - started) * 1000.0

    started = perf_counter()
    batch = adapter.tokenizer.pad(features, padding=True, return_tensors="pt")
    batch = {key: value.to(adapter.device) for key, value in batch.items()}
    tensor_preparation_ms = (perf_counter() - started) * 1000.0

    grad_enabled_inside = None
    started = perf_counter()
    with torch.inference_mode():
        grad_enabled_inside = torch.is_grad_enabled()
        logits = adapter.model(**batch, return_dict=True).logits
    forward_ms = (perf_counter() - started) * 1000.0

    started = perf_counter()
    raw = logits.reshape(-1).detach().cpu().tolist()
    scored = list(zip(candidates, raw, strict=True))
    ordered = sorted(
        scored,
        key=lambda item: (-float(item[1]), int(item[0]["dense_rank"]), item[0]["identity"]),
    )
    ordered_identities = [candidate["identity"] for candidate, _ in ordered]
    postprocessing_ms = (perf_counter() - started) * 1000.0
    total_ms = (perf_counter() - total_started) * 1000.0
    component_sum = (
        tokenization_ms
        + feature_assembly_ms
        + tensor_preparation_ms
        + forward_ms
        + postprocessing_ms
    )
    frozen_order = [
        row["identity"] for row in sorted(candidates, key=lambda row: int(row["reranker_rank"]))
    ]
    frozen_scores = {row["identity"]: float(row["reranker_score"]) for row in candidates}
    observed_scores = {row["identity"]: float(score) for row, score in scored}
    differences = {
        identity: abs(observed_scores[identity] - frozen_scores[identity])
        for identity in frozen_scores
    }
    return {
        "phase": phase,
        "measurement_index": index,
        "case_id": trace["case_id"],
        "pair_count": len(candidates),
        "batch_shape": list(batch["input_ids"].shape),
        "tokenization_ms": round(tokenization_ms, 6),
        "feature_assembly_ms": round(feature_assembly_ms, 6),
        "tensor_preparation_ms": round(tensor_preparation_ms, 6),
        "forward_ms": round(forward_ms, 6),
        "score_extraction_sorting_ms": round(postprocessing_ms, 6),
        "other_timer_residual_ms": round(max(0.0, total_ms - component_sum), 6),
        "total_reranker_call_ms": round(total_ms, 6),
        "ranking_order_matches_frozen_phase2": ordered_identities == frozen_order,
        "all_scores_bitwise_equal_to_frozen_phase2": all(value == 0.0 for value in differences.values()),
        "max_absolute_score_difference": max(differences.values()),
        "inference_mode_grad_enabled_inside": grad_enabled_inside,
        "model_training_inside": adapter.model.training,
        "pair_truncation_count": sum(pair.truncated for pair in pairs),
    }


def token_length_profile(adapter: Any, traces: list[dict[str, Any]]) -> dict[str, Any]:
    query_lengths: list[int] = []
    chunk_lengths: list[int] = []
    pair_lengths: list[int] = []
    padding_lengths: list[int] = []
    padded_slots = 0
    actual_slots = 0
    padded_attention_cells = 0
    actual_attention_cells = 0
    cap_count = 0
    truncation_count = 0
    telemetry_mismatches = []
    per_query = []
    for trace in traces:
        query_ids = adapter.tokenizer.encode(trace["effective_query"], add_special_tokens=False)
        query_lengths.append(len(query_ids))
        local_pairs = []
        local_chunks = []
        candidates = sorted(trace["candidates"], key=lambda row: int(row["dense_rank"]))
        for candidate in candidates:
            chunk_ids = adapter.tokenizer.encode(candidate["raw_text"], add_special_tokens=False)
            pair = enforce_pair_token_budget(
                query_ids,
                chunk_ids,
                special_token_count=adapter.tokenizer.num_special_tokens_to_add(pair=True),
            )
            local_chunks.append(len(chunk_ids))
            local_pairs.append(pair.total_tokens)
            chunk_lengths.append(len(chunk_ids))
            pair_lengths.append(pair.total_tokens)
            cap_count += pair.total_tokens == 1024
            truncation_count += pair.truncated
            if pair.total_tokens != candidate["reranker_input_tokens"]:
                telemetry_mismatches.append(
                    {
                        "case_id": trace["case_id"],
                        "identity": candidate["identity"],
                        "computed": pair.total_tokens,
                        "frozen": candidate["reranker_input_tokens"],
                    }
                )
        padding_length = max(local_pairs)
        padding_lengths.append(padding_length)
        padded_slots += len(local_pairs) * padding_length
        actual_slots += sum(local_pairs)
        padded_attention_cells += len(local_pairs) * padding_length * padding_length
        actual_attention_cells += sum(length * length for length in local_pairs)
        per_query.append(
            {
                "case_id": trace["case_id"],
                "query_token_length": len(query_ids),
                "candidate_chunk_token_length": distribution(local_chunks),
                "pair_token_length": distribution(local_pairs),
                "actual_padding_length": padding_length,
                "padding_token_slot_fraction": round(
                    1.0 - sum(local_pairs) / (len(local_pairs) * padding_length), 9
                ),
                "attention_quadratic_padding_upper_bound_fraction": round(
                    1.0
                    - sum(length * length for length in local_pairs)
                    / (len(local_pairs) * padding_length * padding_length),
                    9,
                ),
            }
        )
    if telemetry_mismatches:
        raise SystemExit(f"token telemetry differs from Phase 2: {telemetry_mismatches[:3]}")
    return {
        "scope": "all 72 frozen Phase 2 C queries and 1,296 query/chunk pairs",
        "query_count": len(traces),
        "pair_count": len(pair_lengths),
        "query_token_length": distribution(query_lengths),
        "candidate_chunk_token_length": distribution(chunk_lengths),
        "pair_token_length": distribution(pair_lengths),
        "actual_padding_length_per_query": distribution(padding_lengths),
        "aggregate_padding_token_slot_fraction": round(1.0 - actual_slots / padded_slots, 9),
        "aggregate_attention_quadratic_padding_upper_bound_fraction": round(
            1.0 - actual_attention_cells / padded_attention_cells, 9
        ),
        "padding_estimate_caveat": (
            "Token-slot fraction is exact for padded inputs; the quadratic figure is an attention-cell upper-bound, "
            "not a percentage of total model FLOPs."
        ),
        "pairs_reaching_1024_cap": cap_count,
        "truncation_count": truncation_count,
        "frozen_phase2_input_token_telemetry_match": True,
        "most_chunks_substantially_below_cap": percentile(
            [float(value) for value in chunk_lengths], 0.95
        ) < 1024 * 0.5,
        "per_query": per_query,
    }


def main() -> None:
    latest = read_json(RESULTS_ROOT / "latest_run.json")
    if latest["status"] != "EVIDENCE_BUILT_PROFILING_PENDING":
        raise SystemExit("latest audit run is not waiting for profiling")
    run_dir = ROOT / latest["run_directory"]
    model_path = SNAPSHOT / "model.safetensors"
    if not SNAPSHOT.is_dir() or sha256(model_path) != MODEL_SHA:
        raise SystemExit("exact frozen local model snapshot is unavailable or changed")

    import torch

    runtime_before = {
        "logical_cpu_count": os.cpu_count(),
        "physical_cpu_count": None,
        "physical_cpu_count_limitation": "not reliably available in this restricted process",
        "processor_architecture": platform.machine(),
        "processor_identifier": platform.processor(),
        "torch_num_threads": torch.get_num_threads(),
        "torch_num_interop_threads": torch.get_num_interop_threads(),
        "cuda_available": torch.cuda.is_available(),
        "grad_enabled_process_default": torch.is_grad_enabled(),
    }
    traces = read_jsonl(PHASE2 / "arm_C/candidate_traces.jsonl")
    traces_by_id = {trace["case_id"]: trace for trace in traces}

    adapter = HuggingFaceRerankerAdapter(SNAPSHOT, device="cpu")
    first_parameter = next(adapter.model.parameters())
    model_runtime = {
        "model_id": adapter.model_id,
        "revision": adapter.revision,
        "snapshot_path": str(SNAPSHOT),
        "local_files_only": True,
        "automatic_downloads": 0,
        "device": str(first_parameter.device),
        "dtype": str(first_parameter.dtype),
        "model_eval_mode": not adapter.model.training,
        "model_load_seconds_diagnostic": round(adapter.load_seconds, 6),
        "model_load_excluded_from_query_latency": True,
    }
    lengths = token_length_profile(adapter, traces)

    measurements = []
    measurements.append(
        profile_once(
            adapter,
            traces_by_id[REPRESENTATIVE_CASE_IDS[0]],
            phase="first_inference_after_model_load",
            index=1,
        )
    )
    warm_sequence = (
        REPRESENTATIVE_CASE_IDS[1],
        REPRESENTATIVE_CASE_IDS[0],
        REPRESENTATIVE_CASE_IDS[1],
        REPRESENTATIVE_CASE_IDS[0],
    )
    for index, case_id in enumerate(warm_sequence, start=1):
        measurements.append(
            profile_once(
                adapter,
                traces_by_id[case_id],
                phase="warm_repeated_inference",
                index=index,
            )
        )
    if not all(row["ranking_order_matches_frozen_phase2"] for row in measurements):
        raise SystemExit("diagnostic reranker ranking differs from frozen Phase 2")

    warm = [row for row in measurements if row["phase"] == "warm_repeated_inference"]
    component_names = (
        "tokenization_ms",
        "feature_assembly_ms",
        "tensor_preparation_ms",
        "forward_ms",
        "score_extraction_sorting_ms",
        "other_timer_residual_ms",
        "total_reranker_call_ms",
    )
    warm_summary = {
        name: distribution(row[name] for row in warm) for name in component_names
    }
    bottleneck_components = sorted(
        (
            (name, warm_summary[name]["p50"])
            for name in component_names
            if name not in {"total_reranker_call_ms", "other_timer_residual_ms"}
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    output = {
        "design_version": "V1.1",
        "ablation_design_sha256": latest["ablation_design_sha256"],
        "phase2_run_id": PHASE2_RUN_ID,
        "phase3_run_id": latest["phase3_run_id"],
        "phase4_run_id": latest["phase4_run_id"],
        "audit_run_id": latest["audit_run_id"],
        "profiling_scope": (
            "exact cached model/revision and frozen Phase 2 C query/chunk pairs; no retrieval, generation, "
            "semantic experiment, external request, or historical artifact write"
        ),
        "runtime": runtime_before,
        "model_runtime": model_runtime,
        "representative_case_ids": list(REPRESENTATIVE_CASE_IDS),
        "measurements": measurements,
        "warm_summary_ms": warm_summary,
        "primary_latency_bottleneck": bottleneck_components[0][0],
        "secondary_latency_bottleneck": bottleneck_components[1][0],
        "forward_fraction_of_warm_p50": round(
            warm_summary["forward_ms"]["p50"]
            / warm_summary["total_reranker_call_ms"]["p50"],
            9,
        ),
        "thread_comparison": {
            "performed": False,
            "reason": (
                "A thread sweep was not justified: the frozen process already uses 8 intra-op threads on "
                "16 logical CPUs, and the audit forbids parameter selection/tuning."
            ),
            "global_configuration_changed": False,
        },
        "local_reranker_model_initializations": 1,
        "local_reranker_inference_calls": len(measurements),
        "local_reranker_pairs_scored": sum(row["pair_count"] for row in measurements),
        "external_requests": 0,
        "deepseek_calls": 0,
        "new_retrieval_runs": 0,
        "new_generation_runs": 0,
        "new_semantic_experiment_outputs": 0,
    }
    write_json(run_dir / "token_length_profile.json", {**output, "measurements": None, "token_lengths": lengths})
    write_json(run_dir / "reranker_microprofile.json", output)
    state = read_json(run_dir / "run_state.json")
    state.update(
        {
            "status": "PROFILING_COMPLETE_FINALIZATION_PENDING",
            "local_reranker_model_initializations": 1,
            "local_reranker_inference_calls": len(measurements),
            "local_reranker_pairs_scored": sum(row["pair_count"] for row in measurements),
            "external_calls": 0,
        }
    )
    write_json(run_dir / "run_state.json", state)
    latest["status"] = "PROFILING_COMPLETE_FINALIZATION_PENDING"
    write_json(RESULTS_ROOT / "latest_run.json", latest)
    print(
        json.dumps(
            {
                "status": "PASS",
                "run_id": latest["audit_run_id"],
                "model_load_seconds": model_runtime["model_load_seconds_diagnostic"],
                "first_inference_ms": measurements[0]["total_reranker_call_ms"],
                "warm_total_ms": warm_summary["total_reranker_call_ms"],
                "primary_bottleneck": output["primary_latency_bottleneck"],
                "ranking_matches": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
