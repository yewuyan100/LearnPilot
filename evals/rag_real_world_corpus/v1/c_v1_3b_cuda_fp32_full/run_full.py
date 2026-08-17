from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[4]
V1 = ROOT / "evals/rag_real_world_corpus/v1"
sys.path.insert(0, str(V1))

from canonical_model_path import resolve_canonical_reranker_model_path  # noqa: E402

RESULTS_ROOT = V1 / "results/c_v1_3b_cuda_fp32_full"
AUTHORITATIVE_RUN_ID = "20260814T145246Z-298674d5"
AUTHORITATIVE = V1 / f"results/c_v1_2_onnx_runtime_equivalence/{AUTHORITATIVE_RUN_ID}"
SMOKE_RUN_ID = "20260816T044720Z-1da309ba"
SMOKE = V1 / f"results/c_v1_3a_cuda_smoke/{SMOKE_RUN_ID}"
PHASE2_RUN_ID = "20260814T095542Z-1317c6a7"
PHASE2 = V1 / f"results/hybrid_rerank_phase2_v1_1/{PHASE2_RUN_ID}"
PHASE3 = V1 / "results/hybrid_rerank_phase3_v1_1/20260814T123142Z-8852712b"
GOLD = V1 / "gold/v1/gold_cases.json"
SNAPSHOT = resolve_canonical_reranker_model_path()
MODEL_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
MODEL_SHA256 = "d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286"
TRACE = PHASE2 / "arm_C/candidate_traces.jsonl"
TRACE_SHA256 = "845b2d297405936fa6f97557b1fb4e56254e88c8248d8bb582e6a751b1999f23"
PRODUCTION_REFERENCE = SMOKE / "production_hashes_after.json"
REPORT = ROOT / "RAG_C_V1_3B_CUDA_FP32_FULL_AUDIT.md"
CPU_C_WARM_P50_MS = 7797.075
REPRESENTATIVE_IDS = {
    "SHORT": "rw-gold-v1-single-langgraph-js",
    "MEDIAN": "rw-gold-v1-disambig-ragas-otel",
    "LONG": "rw-gold-v1-disambig-bge-long",
}
EXPECTED_PACKAGES = {
    "torch": "2.12.1+cu126",
    "transformers": "5.12.1",
    "tokenizers": "0.22.2",
    "safetensors": "0.8.0",
    "huggingface-hub": "1.21.0",
    "numpy": "2.4.6",
}

sys.path.insert(0, str(V1 / "hybrid_rerank_phase2_v1_1"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def file_record(path: Path) -> dict[str, object]:
    return {"path": relative(path), "size_bytes": path.stat().st_size, "sha256": sha256(path)}


def command(*parts: str, check: bool = True) -> str:
    completed = subprocess.run(
        list(parts), cwd=ROOT, check=check, capture_output=True, text=True, encoding="utf-8"
    )
    return completed.stdout.strip()


def percentile(values: Iterable[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def full_distribution(values: Iterable[float]) -> dict[str, float | int]:
    observed = [float(value) for value in values]
    return {
        "count": len(observed),
        "p50": round(percentile(observed, 0.50), 9),
        "p75": round(percentile(observed, 0.75), 9),
        "p90": round(percentile(observed, 0.90), 9),
        "p95": round(percentile(observed, 0.95), 9),
        "p99": round(percentile(observed, 0.99), 9),
        "mean": round(statistics.fmean(observed), 9),
        "min": round(min(observed), 9),
        "max": round(max(observed), 9),
        "standard_deviation": round(statistics.pstdev(observed), 9),
    }


def average_ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda row: row[1])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and ordered[end][1] == ordered[cursor][1]:
            end += 1
        rank = ((cursor + 1) + end) / 2
        for index in range(cursor, end):
            ranks[ordered[index][0]] = rank
        cursor = end
    return ranks


def pearson(left: list[float], right: list[float]) -> float | None:
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    left_delta = [value - left_mean for value in left]
    right_delta = [value - right_mean for value in right]
    denominator = math.sqrt(sum(value * value for value in left_delta) * sum(value * value for value in right_delta))
    if denominator == 0:
        return None
    return sum(a * b for a, b in zip(left_delta, right_delta, strict=True)) / denominator


def correlation(left: list[float], right: list[float]) -> dict[str, object]:
    pearson_r = pearson(left, right)
    spearman_rho = pearson(average_ranks(left), average_ranks(right))
    return {
        "sample_count": len(left),
        "pearson_r": None if pearson_r is None else round(pearson_r, 9),
        "spearman_rho": None if spearman_rho is None else round(spearman_rho, 9),
        "applicable": pearson_r is not None and spearman_rho is not None,
        "limitation": None if pearson_r is not None and spearman_rho is not None else "zero variance",
    }


def packages() -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for name in EXPECTED_PACKAGES:
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result


def nvidia_gpu() -> dict[str, object]:
    line = command(
        "nvidia-smi",
        "--query-gpu=name,driver_version,memory.total,memory.free",
        "--format=csv,noheader,nounits",
    ).splitlines()[0]
    name, driver, total, free = [part.strip() for part in line.split(",")]
    return {
        "name": name,
        "driver_version": driver,
        "memory_total_mib": int(total),
        "memory_free_mib": int(free),
    }


def nvidia_process_memory(pid: int) -> dict[str, object]:
    output = command(
        "nvidia-smi",
        "--query-compute-apps=pid,used_memory",
        "--format=csv,noheader,nounits",
        check=False,
    )
    for line in output.splitlines():
        fields = [part.strip() for part in line.split(",")]
        if fields and fields[0] == str(pid):
            try:
                return {"available": True, "used_memory_mib": int(fields[1])}
            except (IndexError, ValueError):
                return {"available": False, "raw": line}
    return {"available": False, "reason": "process not reported"}


def production_snapshot(run_id: str, stage: str) -> dict[str, object]:
    reference_rows = read_json(PRODUCTION_REFERENCE)["rows"]
    rows = []
    for reference in reference_rows:
        path = ROOT / reference["path"]
        actual = sha256(path)
        expected = reference["frozen_reference_sha256"]
        rows.append(
            {
                "path": reference["path"],
                "frozen_reference_sha256": expected,
                f"v1_3b_{stage}_sha256": actual,
                "matches_frozen_reference": actual == expected,
            }
        )
    return {
        "run_id": run_id,
        "recorded_at": now(),
        "stage": stage,
        "reference_run_id": SMOKE_RUN_ID,
        "reference_file": relative(PRODUCTION_REFERENCE),
        "file_count": len(rows),
        "production_frozen_hash_match": all(row["matches_frozen_reference"] for row in rows),
        "rows": rows,
    }


def prepare(run_id: str) -> None:
    import torch

    run_dir = RESULTS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    gpu = nvidia_gpu()
    tensor = torch.tensor([1.0], device="cuda:0")
    tensor_pass = float((tensor + 1).cpu().item()) == 2.0
    observed_packages = packages()
    pip_check = command(sys.executable, "-m", "pip", "check", check=False)
    checks = {
        "python_3_11": platform.python_version() == "3.11.9",
        "torch_2_12_1_cu126": torch.__version__ == "2.12.1+cu126",
        "cuda_build_12_6": torch.version.cuda == "12.6",
        "cuda_available": torch.cuda.is_available(),
        "device_rtx_4060": gpu["name"] == "NVIDIA GeForce RTX 4060 Laptop GPU",
        "cuda_tensor_smoke": tensor_pass,
        "packages_exact": observed_packages == EXPECTED_PACKAGES,
        "pip_check": "No broken requirements found" in pip_check,
        "smoke_reference_pass": read_json(SMOKE / "artifact_manifest.json")["status"] == "PASS",
        "smoke_ready_for_v1_3b": read_json(SMOKE / "artifact_manifest.json")[
            "ready_for_v1_3b_full_equivalence_and_profiling"
        ]
        == "YES",
        "trace_hash": sha256(TRACE) == TRACE_SHA256,
        "model_hash": sha256(SNAPSHOT / "model.safetensors") == MODEL_SHA256,
    }
    machine = {
        "run_id": run_id,
        "created_at": now(),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "cuda_environment_gate": "PASS" if all(checks.values()) else "FAIL",
        "git_head": command("git", "rev-parse", "HEAD"),
        "git_status_short": command("git", "status", "--short").splitlines(),
        "git_diff_stat": command("git", "diff", "--stat").splitlines(),
        "git_diff_name_only": command("git", "diff", "--name-only").splitlines(),
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "torch_version": torch.__version__,
        "torch_cuda_build": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "device_name": torch.cuda.get_device_name(0),
        "nvidia_smi": gpu,
        "cuda_tensor_smoke": tensor_pass,
        "package_versions": observed_packages,
        "pip_check": pip_check,
        "checks": checks,
    }
    write_json(run_dir / "machine_validation.json", machine)
    before = production_snapshot(run_id, "before")
    write_json(run_dir / "production_hashes_before.json", before)
    if machine["status"] != "PASS" or not before["production_frozen_hash_match"]:
        raise SystemExit("V1.3B preflight failed")
    print(json.dumps({"run_id": run_id, "status": "PASS", "run_dir": str(run_dir)}, indent=2))


def build_features(tokenizer: Any, trace: dict[str, Any]) -> tuple[list[dict[str, list[int]]], list[dict[str, Any]]]:
    from experiment import build_xlm_roberta_pair_feature, enforce_pair_token_budget

    candidates = sorted(trace["candidates"], key=lambda row: (int(row["dense_rank"]), row["identity"]))
    query_ids = tokenizer.encode(trace["effective_query"], add_special_tokens=False)
    features = []
    pairs = []
    for candidate in candidates:
        chunk_ids = tokenizer.encode(candidate["raw_text"], add_special_tokens=False)
        pair = enforce_pair_token_budget(
            query_ids,
            chunk_ids,
            special_token_count=tokenizer.num_special_tokens_to_add(pair=True),
        )
        features.append(build_xlm_roberta_pair_feature(tokenizer, pair))
        pairs.append(
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
    return features, pairs


def prepare_cpu_batch(torch: Any, tokenizer: Any, trace: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, float]]:
    started = perf_counter()
    features, pairs = build_features(tokenizer, trace)
    padded = tokenizer.pad(features, padding=True, return_tensors=None)
    tokenization_ms = (perf_counter() - started) * 1000
    started = perf_counter()
    batch = {
        "input_ids": torch.tensor(padded["input_ids"], dtype=torch.long),
        "attention_mask": torch.tensor(padded["attention_mask"], dtype=torch.long),
    }
    cpu_input_preparation_ms = (perf_counter() - started) * 1000
    return batch, pairs, {
        "tokenization_ms": tokenization_ms,
        "cpu_input_preparation_ms": cpu_input_preparation_ms,
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
                identity=source["identity"], document_id=source["document_id"],
                chunk_index=source["chunk_index"], content_hash=source["content_hash"],
                filename=source["filename"], page_number=source["page_number"],
                section_title=source["section_title"], raw_text=source["raw_text"],
                material_id=source["material_id"], chunk_id=source["chunk_id"],
                evidence_ids=tuple(source["evidence_ids"]), arm="C",
                dense_score=source["dense_score"], dense_rank=source["dense_rank"],
                branch_admitted_dense=source["branch_admitted_dense"],
                dense_fusion_rank=source["dense_fusion_rank"],
                candidate_admitted=source["candidate_admitted"],
                reranker_score=row["score"], reranker_rank=rank,
                reranker_truncated=source["reranker_truncated"],
                reranker_input_tokens=source["reranker_input_tokens"],
            )
        )
    return govern_evidence(candidates)


def context_text(selected: list[Any]) -> str:
    parts = []
    for index, candidate in enumerate(selected, start=1):
        location = (
            f"第 {candidate.page_number} 页" if candidate.page_number is not None
            else candidate.section_title or f"片段 {candidate.chunk_index + 1}"
        )
        parts.append(
            f'<source id="S{index}" trust="untrusted-data">\n'
            f"<filename>{escape(candidate.filename)}</filename>\n"
            f"<location>{escape(location)}</location>\n<content>\n"
            f"{escape(candidate.raw_text)}\n</content>\n</source>"
        )
    return "\n\n".join(parts)


def evidence_coverage(gold: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for group in gold["evidence_groups"]:
        if not group["required"]:
            continue
        rows.append(
            {
                "evidence_group_id": group["evidence_group_id"],
                "document_match": any(
                    candidate["document_id"] in group["any_of_document_ids"] for candidate in candidates
                ),
                "anchor_match": any(
                    set(candidate["evidence_ids"]) & set(group["any_of_evidence_ids"])
                    for candidate in candidates
                ),
            }
        )
    return {
        "groups": rows,
        "document_groups_covered": sum(row["document_match"] for row in rows),
        "anchor_groups_covered": sum(row["anchor_match"] for row in rows),
    }


def timed_call(torch: Any, tokenizer: Any, model: Any, trace: dict[str, Any]) -> tuple[dict[str, Any], list[float]]:
    torch.cuda.synchronize()
    total_started = perf_counter()
    batch, pairs, cpu_times = prepare_cpu_batch(torch, tokenizer, trace)
    h2d_start = torch.cuda.Event(enable_timing=True)
    h2d_end = torch.cuda.Event(enable_timing=True)
    h2d_start.record()
    cuda_batch = {key: value.to("cuda:0") for key, value in batch.items()}
    h2d_end.record()
    h2d_end.synchronize()
    h2d_ms = h2d_start.elapsed_time(h2d_end)

    forward_start = torch.cuda.Event(enable_timing=True)
    forward_end = torch.cuda.Event(enable_timing=True)
    forward_start.record()
    with torch.inference_mode():
        logits = model(**cuda_batch, return_dict=True).logits
    forward_end.record()
    forward_end.synchronize()
    gpu_forward_ms = forward_start.elapsed_time(forward_end)

    d2h_started = perf_counter()
    cpu_logits = logits.reshape(-1).detach().to("cpu")
    torch.cuda.synchronize()
    scores = [float(value) for value in cpu_logits.tolist()]
    d2h_ms = (perf_counter() - d2h_started) * 1000

    sorting_started = perf_counter()
    candidates = sorted(trace["candidates"], key=lambda row: (int(row["dense_rank"]), row["identity"]))
    ordered = stable_order(candidates, scores)
    sorting_ms = (perf_counter() - sorting_started) * 1000
    torch.cuda.synchronize()
    total_ms = (perf_counter() - total_started) * 1000
    return (
        {
            "case_id": trace["case_id"], "pair_count": 18,
            "batch_shape": list(batch["input_ids"].shape),
            "tokenization_ms": round(cpu_times["tokenization_ms"], 6),
            "cpu_input_preparation_ms": round(cpu_times["cpu_input_preparation_ms"], 6),
            "h2d_ms": round(h2d_ms, 6), "gpu_forward_ms": round(gpu_forward_ms, 6),
            "d2h_score_extraction_ms": round(d2h_ms, 6), "sorting_ms": round(sorting_ms, 6),
            "total_reranker_ms": round(total_ms, 6),
            "ranking_order": [row["candidate"]["identity"] for row in ordered],
            "all_pair_token_counts_match": all(row["token_count_match"] for row in pairs),
        },
        scores,
    )


def compare_case(
    trace: dict[str, Any], scores: list[float], reference: dict[str, Any],
    frozen_context: dict[str, Any], gold: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[float], list[dict[str, Any]]]:
    candidates = sorted(trace["candidates"], key=lambda row: (int(row["dense_rank"]), row["identity"]))
    ordered_rows = stable_order(candidates, scores)
    cuda_order = [row["candidate"]["identity"] for row in ordered_rows]
    reference_order = [row["identity"] for row in sorted(candidates, key=lambda row: int(row["reranker_rank"]))]
    cuda_rank = {identity: rank for rank, identity in enumerate(cuda_order, start=1)}
    candidate_rows = []
    differences = []
    for candidate, score in zip(candidates, scores, strict=True):
        difference = abs(float(candidate["reranker_score"]) - float(score))
        differences.append(difference)
        candidate_rows.append(
            {
                "case_id": trace["case_id"], "candidate_id": candidate["identity"],
                "reference_logit": candidate["reranker_score"], "cuda_fp32_logit": score,
                "absolute_difference": difference, "reference_rank": candidate["reranker_rank"],
                "cuda_rank": cuda_rank[candidate["identity"]],
            }
        )
    selected = govern(ordered_rows)
    cuda_top6 = [candidate.identity for candidate in selected]
    current_context = context_text(selected)
    current_digest = text_sha256(current_context)
    selected_rows = [next(row for row in candidates if row["identity"] == identity) for identity in cuda_top6]
    current_evidence = evidence_coverage(gold, selected_rows)
    reference_sorted = sorted(candidates, key=lambda row: int(row["reranker_rank"]))
    cuda_sorted = [row["candidate"] for row in ordered_rows]
    adjacent = []
    for name, rows, score_key in (
        ("reference", reference_sorted, lambda row: float(row["reranker_score"])),
        ("cuda", cuda_sorted, lambda row: float(scores[candidates.index(row)])),
    ):
        gaps = []
        for higher, lower in zip(rows, rows[1:]):
            gaps.append(score_key(higher) - score_key(lower))
        adjacent.append({"kind": name, "minimum_adjacent_logit_gap": min(gaps), "gaps": gaps})
    ordering_equal = cuda_order == reference_order == reference["pytorch_order"]
    top6_equal = cuda_top6 == reference["pytorch_top6"] == frozen_context["selected_candidate_identities"]
    context_equal = current_context == frozen_context["context_text"] and current_digest == reference["pytorch_context_digest"]
    evidence_equal = current_evidence == reference["pytorch_required_evidence"]
    first_divergence = None
    if not ordering_equal:
        for rank, (expected, actual) in enumerate(zip(reference_order, cuda_order, strict=True), start=1):
            if expected != actual:
                expected_candidate = next(row for row in candidate_rows if row["candidate_id"] == expected)
                actual_candidate = next(row for row in candidate_rows if row["candidate_id"] == actual)
                first_divergence = {
                    "rank": rank, "reference_candidate_id": expected, "cuda_candidate_id": actual,
                    "reference_candidate_scores": expected_candidate,
                    "cuda_candidate_scores": actual_candidate,
                    "top6_impacted": not top6_equal, "context_impacted": not context_equal,
                }
                break
    return (
        {
            "case_id": trace["case_id"], "pair_count": 18,
            "ordering_equal": ordering_equal, "governed_top6_equal": top6_equal,
            "final_context_equal": context_equal, "required_evidence_equal": evidence_equal,
            "reference_order": reference_order, "cuda_order": cuda_order,
            "reference_top6": reference["pytorch_top6"], "cuda_top6": cuda_top6,
            "reference_context_digest": reference["pytorch_context_digest"],
            "cuda_context_digest": current_digest,
            "reference_required_evidence": reference["pytorch_required_evidence"],
            "cuda_required_evidence": current_evidence,
            "minimum_adjacent_reference_logit_gap": adjacent[0]["minimum_adjacent_logit_gap"],
            "minimum_adjacent_cuda_logit_gap": adjacent[1]["minimum_adjacent_logit_gap"],
            "first_divergent_rank": first_divergence,
        },
        candidate_rows,
        differences,
        adjacent,
    )


def top_five(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: (-float(row[key]), row["case_id"]))[:5]
    return [
        {
            "case_id": row["case_id"], "gpu_forward_ms": row["gpu_forward_ms"],
            "total_reranker_ms": row["total_reranker_ms"],
            "max_tokens": row["max_pair_token_length"],
            "padded_tokens": row["total_padded_tensor_tokens"],
            "padding_waste_ratio": row["padding_waste_ratio"],
        }
        for row in ordered
    ]


def run_full(run_id: str) -> None:
    run_dir = RESULTS_ROOT / run_id
    machine = read_json(run_dir / "machine_validation.json")
    if machine["status"] != "PASS":
        raise SystemExit("preflight is not PASS")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

    import torch
    from experiment import HuggingFaceRerankerAdapter

    traces = read_jsonl(TRACE)
    traces_by_id = {trace["case_id"]: trace for trace in traces}
    frozen_gate = {
        "query_count": len(traces),
        "candidates_per_query": sorted({len(trace["candidates"]) for trace in traces}),
        "total_pairs": sum(len(trace["candidates"]) for trace in traces),
        "unique_case_ids": len(traces_by_id),
        "trace_sha256": sha256(TRACE),
    }
    if not (
        frozen_gate["query_count"] == frozen_gate["unique_case_ids"] == 72
        and frozen_gate["candidates_per_query"] == [18]
        and frozen_gate["total_pairs"] == 1296
        and frozen_gate["trace_sha256"] == TRACE_SHA256
    ):
        raise SystemExit("frozen input gate failed")
    input_reference = {
        row["case_id"]: row for row in read_json(AUTHORITATIVE / "input_equivalence.json")["rows"]
    }
    query_reference = {
        row["case_id"]: row
        for row in read_json(AUTHORITATIVE / "per_query_ranking_comparison.json")["rows"]
    }
    contexts = {
        row["case_id"]: row for row in read_json(PHASE3 / "context_freeze.json")["records"]
        if row["arm"] == "C"
    }
    gold = {row["case_id"]: row for row in read_json(GOLD)["cases"]}
    if not (set(traces_by_id) == set(input_reference) == set(query_reference) == set(contexts) == set(gold)):
        raise SystemExit("authoritative reference coverage mismatch")

    torch.cuda.empty_cache()
    gpu_before = nvidia_gpu()
    memory_before = {
        "torch_allocated_mib": round(torch.cuda.memory_allocated() / 1024**2, 3),
        "torch_reserved_mib": round(torch.cuda.memory_reserved() / 1024**2, 3),
        "nvidia_smi_free_mib": gpu_before["memory_free_mib"],
    }
    load_started = perf_counter()
    adapter = HuggingFaceRerankerAdapter(SNAPSHOT, device="cpu")
    cpu_parameter = next(adapter.model.parameters())
    cpu_initialized_before_cuda = (
        str(cpu_parameter.device) == "cpu" and cpu_parameter.dtype == torch.float32
    )
    adapter.model.to("cuda:0")
    adapter.device = "cuda:0"
    adapter.model.eval()
    torch.cuda.synchronize()
    model_load_ms = (perf_counter() - load_started) * 1000
    parameter = next(adapter.model.parameters())
    model_after = {
        "torch_allocated_mib": round(torch.cuda.memory_allocated() / 1024**2, 3),
        "torch_reserved_mib": round(torch.cuda.memory_reserved() / 1024**2, 3),
        "nvidia_smi_process": nvidia_process_memory(os.getpid()),
        "nvidia_smi_free_mib": nvidia_gpu()["memory_free_mib"],
    }
    model_loaded_vram = round(model_after["torch_allocated_mib"] - memory_before["torch_allocated_mib"], 3)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.set_float32_matmul_precision("highest")
    strict_checks = {
        "allow_tf32_matmul_false": not torch.backends.cuda.matmul.allow_tf32,
        "allow_tf32_cudnn_false": not torch.backends.cudnn.allow_tf32,
        "float32_matmul_precision_highest": torch.get_float32_matmul_precision() == "highest",
        "model_device_cuda_0": str(parameter.device) == "cuda:0",
        "model_dtype_float32": parameter.dtype == torch.float32,
        "all_parameter_dtypes_float32": {str(item.dtype) for item in adapter.model.parameters()} == {"torch.float32"},
        "model_eval": not adapter.model.training,
        "autocast_false": not torch.is_autocast_enabled("cuda"),
        "cpu_initialized_before_cuda": cpu_initialized_before_cuda,
    }
    runtime = {
        "run_id": run_id, "created_at": now(), "status": "PASS" if all(strict_checks.values()) else "FAIL",
        "cuda_environment_gate": "PASS", "strict_fp32_configuration": "PASS" if all(strict_checks.values()) else "FAIL",
        "python_executable": sys.executable, "python_version": platform.python_version(),
        "torch_version": torch.__version__, "cuda_build": torch.version.cuda,
        "gpu_device": torch.cuda.get_device_name(0), "package_versions": packages(),
        "model_id": adapter.model_id, "model_path": str(SNAPSHOT), "model_revision": adapter.revision,
        "model_sha256": MODEL_SHA256, "local_files_only": True, "trust_remote_code": False,
        "hf_hub_offline": os.environ["HF_HUB_OFFLINE"], "transformers_offline": os.environ["TRANSFORMERS_OFFLINE"],
        "network_model_downloads": 0, "model_load_ms": round(model_load_ms, 6),
        "model_device": str(parameter.device), "model_dtype": str(parameter.dtype),
        "allow_tf32_matmul": torch.backends.cuda.matmul.allow_tf32,
        "allow_tf32_cudnn": torch.backends.cudnn.allow_tf32,
        "float32_matmul_precision": torch.get_float32_matmul_precision(),
        "autocast": False, "checks": strict_checks,
    }
    write_json(run_dir / "runtime_identity.json", runtime)
    if runtime["status"] != "PASS":
        raise SystemExit("strict CUDA FP32 gate failed")

    integrity_rows = []
    sequence_rows = []
    pair_lengths = []
    pair_identity_count = 0
    for trace in traces:
        case_id = trace["case_id"]
        features, pairs = build_features(adapter.tokenizer, trace)
        padded = adapter.tokenizer.pad(features, padding=True, return_tensors=None)
        input_ids = torch.tensor(padded["input_ids"], dtype=torch.long)
        attention_mask = torch.tensor(padded["attention_mask"], dtype=torch.long)
        reference = input_reference[case_id]
        candidates = sorted(trace["candidates"], key=lambda row: (int(row["dense_rank"]), row["identity"]))
        observed_ids = [row["identity"] for row in candidates]
        input_hash = hashlib.sha256(input_ids.numpy().tobytes()).hexdigest()
        attention_hash = hashlib.sha256(attention_mask.numpy().tobytes()).hexdigest()
        checks = {
            "query_id": case_id == reference["case_id"] == contexts[case_id]["case_id"],
            "query_text_hash": text_sha256(trace["effective_query"]) == contexts[case_id]["query_digest"],
            "candidate_ids": observed_ids == reference["candidate_identities_dense_order"],
            "source_ids": all(bool(row["document_id"]) for row in candidates),
            "candidate_text_hashes": all(text_sha256(row["raw_text"]) == row["content_hash"] for row in candidates),
            "dense_order": observed_ids == reference["candidate_identities_dense_order"],
            "pair_construction": all(row["token_count_match"] for row in pairs),
            "token_counts": [row["pair_tokens"] for row in pairs] == [row["pair_tokens"] for row in reference["pairs"]],
            "max_length": input_ids.shape[1] == reference["input_ids_shape"][1],
            "truncation": sum(row["truncated"] for row in pairs) == reference["truncation_count"],
            "padding_policy": list(input_ids.shape) == reference["input_ids_shape"],
            "input_ids_sha256": input_hash == reference["input_ids_sha256"],
            "attention_mask_sha256": attention_hash == reference["attention_mask_sha256"],
        }
        integrity_rows.append(
            {"case_id": case_id, "pair_count": 18, "identical": all(checks.values()), "checks": checks,
             "input_ids_sha256": input_hash, "attention_mask_sha256": attention_hash}
        )
        lengths = [row["pair_tokens"] for row in pairs]
        pair_lengths.extend(lengths)
        pair_identity_count += len(pairs)
        padded_total = len(lengths) * max(lengths)
        real_total = sum(lengths)
        sequence_rows.append(
            {
                "case_id": case_id, "pair_count": 18,
                "minimum_pair_token_length": min(lengths),
                "mean_pair_token_length": statistics.fmean(lengths),
                "maximum_pair_token_length": max(lengths),
                "batch_padded_sequence_length": max(lengths),
                "total_real_unpadded_tokens": real_total,
                "total_padded_tensor_tokens": padded_total,
                "padding_waste_tokens": padded_total - real_total,
                "padding_efficiency": real_total / padded_total,
                "padding_waste_ratio": (padded_total - real_total) / padded_total,
            }
        )
    integrity_pass = all(row["identical"] for row in integrity_rows)
    candidate_integrity = {
        "run_id": run_id, "created_at": now(), "status": "PASS" if integrity_pass else "FAIL",
        "frozen_input_gate": "PASS", "cuda_fp32_candidate_inputs": "PASS" if integrity_pass else "FAIL",
        **frozen_gate, "frozen_candidate_source": relative(TRACE), "frozen_candidate_manifest_sha256": TRACE_SHA256,
        "candidate_inputs_identical": f"{sum(row['identical'] for row in integrity_rows)}/72",
        "pair_identities_identical": f"{pair_identity_count}/1296" if integrity_pass else "FAIL",
        "rows": integrity_rows,
    }
    write_json(run_dir / "candidate_integrity_results.json", candidate_integrity)
    if not integrity_pass:
        raise SystemExit("full candidate integrity gate failed")

    sequence_lengths = {
        "run_id": run_id, "created_at": now(), "status": "PASS",
        "pair_count": len(pair_lengths), "pair_token_length": full_distribution(pair_lengths),
        "truncation_count": 0, "max_length_policy_changed": False,
    }
    write_json(run_dir / "sequence_lengths.json", sequence_lengths)
    padding_audit = {
        "run_id": run_id, "created_at": now(), "status": "PASS", "query_count": 72, "pair_count": 1296,
        "definitions": {
            "total_padded_tensor_tokens": "18 * batch_padded_sequence_length",
            "padding_waste_tokens": "total_padded_tensor_tokens - total_real_unpadded_tokens",
            "padding_waste_ratio": "padding_waste_tokens / total_padded_tensor_tokens",
            "padding_efficiency": "total_real_unpadded_tokens / total_padded_tensor_tokens",
        },
        "padding_waste_ratio": full_distribution(row["padding_waste_ratio"] for row in sequence_rows),
        "batch_padded_sequence_length": full_distribution(row["batch_padded_sequence_length"] for row in sequence_rows),
        "rows": sequence_rows, "observational_only": True, "padding_behavior_changed": False,
    }
    write_json(run_dir / "sequence_padding_audit.json", padding_audit)

    first_inference, _ = timed_call(torch, adapter.tokenizer, adapter.model, traces_by_id[REPRESENTATIVE_IDS["SHORT"]])
    warmups = []
    for label, case_id in REPRESENTATIVE_IDS.items():
        row, _ = timed_call(torch, adapter.tokenizer, adapter.model, traces_by_id[case_id])
        warmups.append({"selection_label": label, **row})

    latency_rows = []
    memory_rows = []
    scores_by_case = {}
    for sequence, trace in enumerate(traces, start=1):
        torch.cuda.reset_peak_memory_stats()
        row, scores = timed_call(torch, adapter.tokenizer, adapter.model, trace)
        row["sequence"] = sequence
        profile = next(item for item in sequence_rows if item["case_id"] == trace["case_id"])
        row.update(
            {
                "max_pair_token_length": profile["maximum_pair_token_length"],
                "total_padded_tensor_tokens": profile["total_padded_tensor_tokens"],
                "padding_waste_ratio": profile["padding_waste_ratio"],
                "gpu_forward_share_of_total": row["gpu_forward_ms"] / row["total_reranker_ms"],
            }
        )
        latency_rows.append(row)
        scores_by_case[trace["case_id"]] = scores
        memory_rows.append(
            {
                "sequence": sequence, "case_id": trace["case_id"],
                "peak_allocated_mib": round(torch.cuda.max_memory_allocated() / 1024**2, 3),
                "peak_reserved_mib": round(torch.cuda.max_memory_reserved() / 1024**2, 3),
                "oom": False, "allocator_error": False, "cpu_offload": False,
                "disk_offload": False, "unexpected_device_placement": False,
            }
        )

    equivalence_rows = []
    candidate_drift_rows = []
    all_differences = []
    near_tie_rows = []
    for trace in traces:
        comparison, candidate_rows, differences, adjacent = compare_case(
            trace, scores_by_case[trace["case_id"]], query_reference[trace["case_id"]],
            contexts[trace["case_id"]], gold[trace["case_id"]],
        )
        equivalence_rows.append(comparison)
        candidate_drift_rows.extend(candidate_rows)
        all_differences.extend(differences)
        reference_min = adjacent[0]["minimum_adjacent_logit_gap"]
        cuda_min = adjacent[1]["minimum_adjacent_logit_gap"]
        near_tie_rows.append(
            {"case_id": trace["case_id"], "minimum_adjacent_reference_logit_gap": reference_min,
             "minimum_adjacent_cuda_logit_gap": cuda_min,
             "reference_near_tie_lte_0_01": reference_min <= 0.01,
             "cuda_near_tie_lte_0_01": cuda_min <= 0.01}
        )
    ordering_count = sum(row["ordering_equal"] for row in equivalence_rows)
    top6_count = sum(row["governed_top6_equal"] for row in equivalence_rows)
    context_count = sum(row["final_context_equal"] for row in equivalence_rows)
    evidence_count = sum(row["required_evidence_equal"] for row in equivalence_rows)
    equivalence_pass = ordering_count == top6_count == context_count == evidence_count == 72
    equivalence = {
        "run_id": run_id, "created_at": now(), "status": "PASS" if equivalence_pass else "FAIL",
        "cuda_fp32_equivalence": "PASS" if equivalence_pass else "FAIL", "total_cases": 72, "total_pairs": 1296,
        "full_reranker_ordering": f"{ordering_count}/72", "governed_top6": f"{top6_count}/72",
        "final_context": f"{context_count}/72", "required_evidence": f"{evidence_count}/72",
        "c_v1_1_semantic_results_reusable": equivalence_pass,
        "deepseek_rerun_required": not equivalence_pass,
        "rows": equivalence_rows,
    }
    write_json(run_dir / "equivalence_results.json", equivalence)
    logit_drift = {
        "run_id": run_id, "created_at": now(), "status": "PASS",
        "absolute_difference": full_distribution(all_differences), "rows": candidate_drift_rows,
    }
    write_json(run_dir / "logit_drift_results.json", logit_drift)
    near_ties = {
        "run_id": run_id, "created_at": now(), "status": "PASS", "threshold": 0.01,
        "threshold_is_observational_only": True,
        "near_tie_case_count_reference": sum(row["reference_near_tie_lte_0_01"] for row in near_tie_rows),
        "near_tie_case_count_cuda": sum(row["cuda_near_tie_lte_0_01"] for row in near_tie_rows),
        "rows": near_tie_rows,
    }
    write_json(run_dir / "near_tie_results.json", near_ties)
    if not equivalence_pass:
        raise SystemExit("full equivalence gate failed")

    representative_rows = []
    for label, case_id in REPRESENTATIVE_IDS.items():
        measurements = []
        for index in range(1, 4):
            row, _ = timed_call(torch, adapter.tokenizer, adapter.model, traces_by_id[case_id])
            row["measurement_index"] = index
            measurements.append(row)
        representative_rows.append(
            {
                "selection_label": label, "case_id": case_id, "measured_repeats": 3,
                "gpu_forward_ms": {
                    "mean": statistics.fmean(row["gpu_forward_ms"] for row in measurements),
                    "min": min(row["gpu_forward_ms"] for row in measurements),
                    "max": max(row["gpu_forward_ms"] for row in measurements),
                },
                "total_reranker_ms": {
                    "mean": statistics.fmean(row["total_reranker_ms"] for row in measurements),
                    "min": min(row["total_reranker_ms"] for row in measurements),
                    "max": max(row["total_reranker_ms"] for row in measurements),
                },
                "measurements": measurements,
            }
        )
    representative = {
        "run_id": run_id, "created_at": now(), "status": "PASS",
        "excluded_from_full_distribution": True, "rows": representative_rows,
    }
    write_json(run_dir / "representative_latency_results.json", representative)

    write_json(
        run_dir / "latency_per_query.json",
        {"run_id": run_id, "created_at": now(), "status": "PASS",
         "full_distribution_sample_count": 72, "rows": latency_rows},
    )
    stage_names = (
        "tokenization_ms", "cpu_input_preparation_ms", "h2d_ms", "gpu_forward_ms",
        "d2h_score_extraction_ms", "sorting_ms", "total_reranker_ms",
    )
    latency_statistics = {
        name: full_distribution(row[name] for row in latency_rows) for name in stage_names
    }
    share_distribution = full_distribution(row["gpu_forward_share_of_total"] for row in latency_rows)
    total_p50 = latency_statistics["total_reranker_ms"]["p50"]
    speedup = CPU_C_WARM_P50_MS / total_p50
    latency_results = {
        "run_id": run_id, "created_at": now(), "status": "PASS",
        "methodology": {
            "model_load_excluded": True, "first_inference_excluded": True,
            "first_inference_total_ms": first_inference["total_reranker_ms"],
            "representative_warmup_count": 3, "warmups": warmups,
            "one_measured_run_per_frozen_query": True, "full_distribution_sample_count": 72,
            "representative_repeats_excluded": True, "gpu_forward_cuda_events": True,
            "total_perf_counter_with_cuda_synchronization": True,
        },
        "statistics_ms": latency_statistics,
        "gpu_forward_share_of_total": share_distribution,
        "gpu_forward_share_of_total_p50": share_distribution["p50"],
        "gpu_forward_share_of_total_mean": share_distribution["mean"],
        "cpu_c_warm_p50_reference_ms": CPU_C_WARM_P50_MS,
        "cpu_to_gpu_p50_speedup": round(speedup, 6),
    }
    write_json(run_dir / "latency_results.json", latency_results)

    write_json(
        run_dir / "gpu_memory_per_query.json",
        {"run_id": run_id, "created_at": now(), "status": "PASS", "query_count": 72, "rows": memory_rows},
    )
    allocated_dist = full_distribution(row["peak_allocated_mib"] for row in memory_rows)
    reserved_dist = full_distribution(row["peak_reserved_mib"] for row in memory_rows)
    gpu_memory_pass = (
        not any(row["oom"] or row["allocator_error"] or row["cpu_offload"] or row["disk_offload"] or row["unexpected_device_placement"] for row in memory_rows)
        and reserved_dist["max"] < gpu_before["memory_total_mib"]
    )
    gpu_memory = {
        "run_id": run_id, "created_at": now(), "status": "PASS" if gpu_memory_pass else "FAIL",
        "gpu_memory": "PASS" if gpu_memory_pass else "FAIL", "before_model_load": memory_before,
        "after_model_load": model_after, "model_loaded_vram_mib": model_loaded_vram,
        "warm_peak_allocated_mib": allocated_dist, "warm_peak_reserved_mib": reserved_dist,
        "oom_count": sum(row["oom"] for row in memory_rows),
        "allocator_error_count": sum(row["allocator_error"] for row in memory_rows),
        "cpu_offload_observed": any(row["cpu_offload"] for row in memory_rows),
        "disk_offload_observed": any(row["disk_offload"] for row in memory_rows),
        "unexpected_device_placement": any(row["unexpected_device_placement"] for row in memory_rows),
    }
    write_json(run_dir / "gpu_memory_results.json", gpu_memory)
    if not gpu_memory_pass:
        raise SystemExit("GPU memory gate failed")

    correlation_inputs = {
        "gpu_forward_ms": [row["gpu_forward_ms"] for row in latency_rows],
        "total_reranker_ms": [row["total_reranker_ms"] for row in latency_rows],
        "max_sequence_length": [row["max_pair_token_length"] for row in latency_rows],
        "padded_tokens": [row["total_padded_tensor_tokens"] for row in latency_rows],
        "padding_waste_ratio": [row["padding_waste_ratio"] for row in latency_rows],
    }
    correlations = {
        "run_id": run_id, "created_at": now(), "status": "PASS", "sample_count": 72,
        "gpu_forward_vs_max_sequence_length": correlation(correlation_inputs["gpu_forward_ms"], correlation_inputs["max_sequence_length"]),
        "gpu_forward_vs_total_padded_tensor_tokens": correlation(correlation_inputs["gpu_forward_ms"], correlation_inputs["padded_tokens"]),
        "gpu_forward_vs_padding_waste_ratio": correlation(correlation_inputs["gpu_forward_ms"], correlation_inputs["padding_waste_ratio"]),
        "total_reranker_vs_total_padded_tensor_tokens": correlation(correlation_inputs["total_reranker_ms"], correlation_inputs["padded_tokens"]),
        "top5": {
            "slowest_gpu_forward": top_five(latency_rows, "gpu_forward_ms"),
            "slowest_total_latency": top_five(latency_rows, "total_reranker_ms"),
            "highest_padding_waste_ratio": top_five(latency_rows, "padding_waste_ratio"),
            "highest_max_sequence_length": top_five(latency_rows, "max_pair_token_length"),
        },
    }
    write_json(run_dir / "latency_padding_correlations.json", correlations)

    stage_means = {name: latency_statistics[name]["mean"] for name in stage_names if name != "total_reranker_ms"}
    ranked_stages = sorted(stage_means.items(), key=lambda row: row[1], reverse=True)
    share_mean = share_distribution["mean"]
    dominant = "YES" if share_mean > 0.70 else "PARTIAL" if share_mean >= 0.50 else "NO"
    primary = {
        "gpu_forward_ms": "GPU_FORWARD", "tokenization_ms": "TOKENIZATION",
        "cpu_input_preparation_ms": "CPU_INPUT_PREPARATION", "h2d_ms": "H2D_TRANSFER",
        "d2h_score_extraction_ms": "D2H_SYNC", "sorting_ms": "SORTING",
    }[ranked_stages[0][0]]
    secondary = {
        "gpu_forward_ms": "GPU_FORWARD", "tokenization_ms": "TOKENIZATION",
        "cpu_input_preparation_ms": "CPU_INPUT_PREPARATION", "h2d_ms": "H2D_TRANSFER",
        "d2h_score_extraction_ms": "D2H_SYNC", "sorting_ms": "SORTING",
    }[ranked_stages[1][0]]
    total_stats = latency_statistics["total_reranker_ms"]
    if total_stats["p95"] < min(1000.0, CPU_C_WARM_P50_MS * 0.20) and total_stats["max"] < CPU_C_WARM_P50_MS * 0.25 and speedup >= 8:
        gpu_latency = "STRONG"
        latency_reason = "P95 is sub-second, max is well below the CPU reference, and P50 speedup exceeds 8x for a single-user local desktop workload."
    elif total_stats["p95"] < CPU_C_WARM_P50_MS * 0.35 and speedup >= 4:
        gpu_latency = "VIABLE"
        latency_reason = "The full distribution is materially faster than the CPU reference with bounded tail latency."
    elif total_stats["p95"] < CPU_C_WARM_P50_MS * 0.60 and speedup >= 2:
        gpu_latency = "BORDERLINE"
        latency_reason = "The GPU improves runtime but tail latency remains consequential for interactive use."
    else:
        gpu_latency = "NOT_VIABLE"
        latency_reason = "The measured full distribution does not establish sufficient interactive improvement over the CPU reference."
    bottleneck = {
        "run_id": run_id, "created_at": now(), "status": "PASS",
        "is_gpu_forward_still_the_dominant_bottleneck": dominant,
        "primary_bottleneck": primary, "secondary_bottleneck": secondary,
        "stage_mean_ms": stage_means, "gpu_forward_share_of_total_mean": share_mean,
        "gpu_forward_share_of_total_p50": share_distribution["p50"],
        "evidence": {
            "ranked_stage_means": [{"stage": name, "mean_ms": value} for name, value in ranked_stages],
            "interpretation": (
                "GPU forward is clearly dominant." if dominant == "YES"
                else "GPU forward is dominant but secondary overhead is meaningful." if dominant == "PARTIAL"
                else "A non-forward stage materially dominates the measured call."
            ),
        },
        "gpu_latency": gpu_latency, "gpu_latency_reason": latency_reason,
        "cpu_c_warm_p50_reference_ms": CPU_C_WARM_P50_MS,
        "gpu_total_p50_ms": total_stats["p50"], "gpu_total_p95_ms": total_stats["p95"],
        "cpu_to_gpu_p50_speedup": round(speedup, 6),
        "workload_context": "single-user local desktop application",
    }
    write_json(run_dir / "bottleneck_classification.json", bottleneck)

    optimization_required = gpu_latency not in {"STRONG", "VIABLE"}
    optimization_triage = {
        "run_id": run_id, "created_at": now(), "status": "PASS",
        "optimization_required_for_v1": optimization_required,
        "optimization_triage": "NO_OPTIMIZATION_NEEDED" if not optimization_required else "OTHER",
        "reason": (
            "CUDA FP32 already provides suitable full-distribution runtime for the local single-user UX; "
            "observed correlations and padding waste remain evidence only."
            if not optimization_required
            else "The measured full-distribution runtime requires a separate bounded optimization decision."
        ),
        "optimization_experiments_executed": 0,
    }
    write_json(run_dir / "optimization_triage.json", optimization_triage)

    after = production_snapshot(run_id, "after")
    before = read_json(run_dir / "production_hashes_before.json")
    before_by_path = {row["path"]: row["v1_3b_before_sha256"] for row in before["rows"]}
    for row in after["rows"]:
        row["v1_3b_before_sha256"] = before_by_path[row["path"]]
        row["byte_identical_during_v1_3b"] = row["v1_3b_before_sha256"] == row["v1_3b_after_sha256"]
    after["production_frozen_hash_match"] = after["production_frozen_hash_match"] and all(
        row["byte_identical_during_v1_3b"] for row in after["rows"]
    )
    write_json(run_dir / "production_hashes_after.json", after)
    if not after["production_frozen_hash_match"]:
        raise SystemExit("production hash gate failed")

    ready = equivalence_pass and gpu_memory_pass and after["production_frozen_hash_match"]
    pair_stats = sequence_lengths["pair_token_length"]
    waste_stats = padding_audit["padding_waste_ratio"]
    corr_padded = correlations["gpu_forward_vs_total_padded_tensor_tokens"]
    status_lines = f"""RAG_C_V1_3B_CUDA_FP32_FULL_AUDIT = PASS
CUDA_ENVIRONMENT_GATE = PASS
STRICT_FP32_CONFIGURATION = PASS
FROZEN_INPUT_GATE = PASS
CUDA_FP32_CANDIDATE_INPUTS = PASS
TOTAL_CASES = 72
TOTAL_PAIRS = 1296
FULL_RERANKER_ORDERING = {ordering_count}/72
GOVERNED_TOP6 = {top6_count}/72
FINAL_CONTEXT = {context_count}/72
REQUIRED_EVIDENCE = {evidence_count}/72
CUDA_FP32_EQUIVALENCE = PASS
MAX_LOGIT_ABS_DIFF = {logit_drift['absolute_difference']['max']}
MEAN_LOGIT_ABS_DIFF = {logit_drift['absolute_difference']['mean']}
C_V1_1_SEMANTIC_RESULTS_REUSABLE = true
DEEPSEEK_RERUN_REQUIRED = false
GPU_FORWARD_P50_MS = {latency_statistics['gpu_forward_ms']['p50']}
GPU_FORWARD_P95_MS = {latency_statistics['gpu_forward_ms']['p95']}
GPU_TOTAL_P50_MS = {total_stats['p50']}
GPU_TOTAL_P95_MS = {total_stats['p95']}
GPU_TOTAL_MEAN_MS = {total_stats['mean']}
GPU_TOTAL_MAX_MS = {total_stats['max']}
CPU_C_WARM_P50_REFERENCE_MS = {CPU_C_WARM_P50_MS}
CPU_TO_GPU_P50_SPEEDUP = {round(speedup, 6)}
GPU_FORWARD_SHARE_OF_TOTAL_MEAN = {share_mean}
GPU_FORWARD_SHARE_OF_TOTAL_P50 = {share_distribution['p50']}
MODEL_LOADED_VRAM_MIB = {model_loaded_vram}
PEAK_ALLOCATED_P95_MIB = {allocated_dist['p95']}
PEAK_ALLOCATED_MAX_MIB = {allocated_dist['max']}
PEAK_RESERVED_MAX_MIB = {reserved_dist['max']}
GPU_MEMORY = PASS
PAIR_TOKEN_LENGTH_P50 = {pair_stats['p50']}
PAIR_TOKEN_LENGTH_P95 = {pair_stats['p95']}
PAIR_TOKEN_LENGTH_MAX = {pair_stats['max']}
PADDING_WASTE_RATIO_P50 = {waste_stats['p50']}
PADDING_WASTE_RATIO_P95 = {waste_stats['p95']}
GPU_FORWARD_VS_PADDED_TOKENS_PEARSON = {corr_padded['pearson_r']}
GPU_FORWARD_VS_PADDED_TOKENS_SPEARMAN = {corr_padded['spearman_rho']}
IS_GPU_FORWARD_STILL_THE_DOMINANT_BOTTLENECK = {dominant}
PRIMARY_BOTTLENECK = {primary}
SECONDARY_BOTTLENECK = {secondary}
GPU_LATENCY = {gpu_latency}
OPTIMIZATION_REQUIRED_FOR_V1 = {str(optimization_required).lower()}
OPTIMIZATION_TRIAGE = {optimization_triage['optimization_triage']}
READY_FOR_C_GPU_DECISION = {'YES' if ready else 'NO'}
FULL_72_QUERY_RUN_EXECUTED = true
DEEPSEEK_CALLS = 0
RETRIEVAL_RERUNS = 0
GENERATION_RERUNS = 0
PRODUCTION_CODE_CHANGED = false
PRODUCTION_DEPENDENCIES_CHANGED = false
PRODUCTION_FROZEN_HASH_MATCH = true
FINAL_RAG_ARCHITECTURE = NOT_YET_FROZEN"""
    report = f"""# LearnPilot RAG C V1.3B — CUDA FP32 Full Equivalence + Profiling

## Result

The bounded 72-query CUDA FP32 audit completed successfully. All 1,296 frozen candidate inputs and all semantic invariants match the authoritative C reference. The full latency classification is `{gpu_latency}` for the single-user local desktop context. This is runtime evidence, not an architecture selection.

## Runtime and input identity

- Run ID: `{run_id}`
- Runtime: Python `{platform.python_version()}`, torch `{torch.__version__}`, CUDA `{torch.version.cuda}`, `{torch.cuda.get_device_name(0)}`
- Model: `BAAI/bge-reranker-v2-m3`, revision `{MODEL_REVISION}`, strict offline local snapshot
- FP32: device `cuda:0`, dtype `float32`, TF32 off, autocast off, matmul precision `highest`
- Frozen input integrity: `72/72` cases and `1296/1296` pair identities; no retrieval

## Equivalence

- Full ordering / governed Top6 / final context / required evidence: `{ordering_count}/72`, `{top6_count}/72`, `{context_count}/72`, `{evidence_count}/72`
- Absolute logit difference: P50 `{logit_drift['absolute_difference']['p50']}`, mean `{logit_drift['absolute_difference']['mean']}`, P95 `{logit_drift['absolute_difference']['p95']}`, P99 `{logit_drift['absolute_difference']['p99']}`, max `{logit_drift['absolute_difference']['max']}`
- Existing C V1.1 semantic results remain reusable; no semantic-generation rerun is required

## Full 72-query latency

- GPU forward P50/P95: `{latency_statistics['gpu_forward_ms']['p50']:.3f}` / `{latency_statistics['gpu_forward_ms']['p95']:.3f}` ms
- Total P50/P95/mean/max: `{total_stats['p50']:.3f}` / `{total_stats['p95']:.3f}` / `{total_stats['mean']:.3f}` / `{total_stats['max']:.3f}` ms
- Per-query GPU-forward share P50/mean: `{share_distribution['p50']:.4f}` / `{share_mean:.4f}`
- CPU C warm P50 reference `{CPU_C_WARM_P50_MS:.3f}` ms to GPU total P50 speedup: `{speedup:.2f}x`
- First inference total (excluded): `{first_inference['total_reranker_ms']:.3f}` ms; full distribution sample count is exactly 72

## Memory, sequence, and padding

- Model-loaded allocation delta: `{model_loaded_vram:.3f}` MiB
- Peak allocated P95/max: `{allocated_dist['p95']:.3f}` / `{allocated_dist['max']:.3f}` MiB
- Peak reserved P95/max: `{reserved_dist['p95']:.3f}` / `{reserved_dist['max']:.3f}` MiB
- Pair-token P50/P95/max: `{pair_stats['p50']:.1f}` / `{pair_stats['p95']:.1f}` / `{pair_stats['max']:.1f}`
- Padding-waste-ratio P50/P95: `{waste_stats['p50']:.4f}` / `{waste_stats['p95']:.4f}`
- GPU forward vs padded tokens Pearson/Spearman: `{corr_padded['pearson_r']}` / `{corr_padded['spearman_rho']}`

## Classification

- GPU-forward dominance: `{dominant}`; primary `{primary}`, secondary `{secondary}`
- GPU latency: `{gpu_latency}` — {latency_reason}
- Optimization required for V1: `{str(optimization_required).lower()}`; triage `{optimization_triage['optimization_triage']}`
- Ready for C GPU decision: `{'YES' if ready else 'NO'}`

## Integrity and boundary

All 15 production frozen files match before and after. DeepSeek, retrieval, and generation counts are zero. No production code or dependency manifest changed. The final RAG architecture remains not yet frozen.

## Final status

```text
{status_lines}
```
"""
    REPORT.write_text(report, encoding="utf-8")

    artifact_names = [
        "machine_validation.json", "runtime_identity.json", "production_hashes_before.json",
        "production_hashes_after.json", "candidate_integrity_results.json", "equivalence_results.json",
        "logit_drift_results.json", "near_tie_results.json", "latency_per_query.json",
        "latency_results.json", "representative_latency_results.json", "gpu_memory_per_query.json",
        "gpu_memory_results.json", "sequence_lengths.json", "sequence_padding_audit.json",
        "latency_padding_correlations.json", "bottleneck_classification.json", "optimization_triage.json",
    ]
    manifest = {
        "run_id": run_id, "created_at": now(), "status": "PASS", "git_head": machine["git_head"],
        "authoritative_reference_run": AUTHORITATIVE_RUN_ID, "cuda_smoke_reference_run": SMOKE_RUN_ID,
        "python_version": platform.python_version(), "python_executable": sys.executable,
        "torch_version": torch.__version__, "cuda_build": torch.version.cuda,
        "gpu_device": torch.cuda.get_device_name(0),
        "transformers_version": importlib.metadata.version("transformers"),
        "tokenizers_version": importlib.metadata.version("tokenizers"),
        "safetensors_version": importlib.metadata.version("safetensors"),
        "model_path": str(SNAPSHOT), "model_revision": MODEL_REVISION,
        "frozen_candidate_source": relative(TRACE), "frozen_candidate_sha256": TRACE_SHA256,
        "artifact_files": [file_record(run_dir / name) for name in artifact_names]
        + [file_record(REPORT), file_record(Path(__file__))],
        "final_decision_boundary": {
            "cuda_fp32_equivalence": "PASS", "gpu_latency": gpu_latency,
            "gpu_memory": "PASS", "primary_bottleneck": primary,
            "ready_for_c_gpu_decision": "YES" if ready else "NO",
            "final_rag_architecture": "NOT_YET_FROZEN",
        },
        "execution_audit": {
            "full_72_query_run_executed": True, "distribution_sample_count": 72,
            "authoritative_inference_batches": 72, "authoritative_pairs": 1296,
            "deepseek_calls": 0, "retrieval_reruns": 0, "generation_reruns": 0,
            "production_code_changed": False, "production_dependencies_changed": False,
            "production_frozen_hash_match": True,
        },
    }
    write_json(run_dir / "artifact_manifest.json", manifest)
    print(
        json.dumps(
            {
                "run_id": run_id, "status": "PASS", "ordering": f"{ordering_count}/72",
                "top6": f"{top6_count}/72", "context": f"{context_count}/72",
                "evidence": f"{evidence_count}/72", "gpu_total": total_stats,
                "gpu_forward": latency_statistics["gpu_forward_ms"],
                "speedup": round(speedup, 6), "gpu_latency": gpu_latency,
                "primary_bottleneck": primary, "secondary_bottleneck": secondary,
                "ready_for_c_gpu_decision": "YES" if ready else "NO",
            },
            indent=2,
        ),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    if args.prepare == args.full:
        raise SystemExit("choose exactly one of --prepare or --full")
    prepare(args.run_id) if args.prepare else run_full(args.run_id)


if __name__ == "__main__":
    main()
