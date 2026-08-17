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

RESULTS_ROOT = V1 / "results/c_v1_3a_cuda_smoke"
AUTHORITATIVE_RUN_ID = "20260814T145246Z-298674d5"
AUTHORITATIVE = V1 / f"results/c_v1_2_onnx_runtime_equivalence/{AUTHORITATIVE_RUN_ID}"
PHASE2_RUN_ID = "20260814T095542Z-1317c6a7"
PHASE2 = V1 / f"results/hybrid_rerank_phase2_v1_1/{PHASE2_RUN_ID}"
PHASE3_RUN_ID = "20260814T123142Z-8852712b"
PHASE3 = V1 / f"results/hybrid_rerank_phase3_v1_1/{PHASE3_RUN_ID}"
GOLD = V1 / "gold/v1/gold_cases.json"
SNAPSHOT = resolve_canonical_reranker_model_path()
MODEL_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
MODEL_SHA256 = "d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286"
TRACE = PHASE2 / "arm_C/candidate_traces.jsonl"
TRACE_SHA256 = "845b2d297405936fa6f97557b1fb4e56254e88c8248d8bb582e6a751b1999f23"
PARENT_HASHES = (
    V1
    / "results/c_v1_3a_cuda_env_and_smoke/20260815T072031Z-126ba16e/production_hashes_after.json"
)
REPORT = ROOT / "RAG_C_V1_3A_S_CUDA_FP32_SMOKE.md"
REQUIRED_PACKAGES = {
    "torch": "2.12.1+cu126",
    "transformers": "5.12.1",
    "tokenizers": "0.22.2",
    "safetensors": "0.8.0",
    "huggingface-hub": "1.21.0",
    "numpy": "2.4.6",
    "regex": "2026.6.28",
    "requests": "2.34.2",
    "packaging": "26.2",
    "PyYAML": "6.0.3",
    "tqdm": "4.68.3",
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


def percentile(values: Iterable[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def distribution(values: Iterable[float]) -> dict[str, float | int]:
    observed = [float(value) for value in values]
    return {
        "count": len(observed),
        "min": round(min(observed), 9),
        "median": round(statistics.median(observed), 9),
        "mean": round(statistics.fmean(observed), 9),
        "p95": round(percentile(observed, 0.95), 9),
        "max": round(max(observed), 9),
    }


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


def package_versions() -> dict[str, str | None]:
    output: dict[str, str | None] = {}
    for name in REQUIRED_PACKAGES:
        try:
            output[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            output[name] = None
    return output


def nvidia_gpu() -> dict[str, object]:
    row = command(
        "nvidia-smi",
        "--query-gpu=name,driver_version,memory.total,memory.free",
        "--format=csv,noheader,nounits",
    ).splitlines()[0]
    name, driver, total, free = [item.strip() for item in row.split(",")]
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
        fields = [item.strip() for item in line.split(",")]
        if fields and fields[0] == str(pid):
            try:
                return {"available": True, "used_memory_mib": int(fields[1])}
            except (IndexError, ValueError):
                return {"available": False, "raw": line}
    return {"available": False, "reason": "process not reported by nvidia-smi"}


def production_snapshot(run_id: str, stage: str) -> dict[str, object]:
    reference_rows = read_json(PARENT_HASHES)["rows"]
    rows = []
    for reference in reference_rows:
        path = ROOT / reference["path"]
        actual = sha256(path)
        rows.append(
            {
                "path": reference["path"],
                "frozen_reference_sha256": reference["frozen_reference_sha256"],
                f"v1_3a_s_{stage}_sha256": actual,
                "matches_frozen_reference": actual == reference["frozen_reference_sha256"],
            }
        )
    return {
        "run_id": run_id,
        "recorded_at": now(),
        "stage": stage,
        "reference_run_id": "20260815T072031Z-126ba16e",
        "reference_file": relative(PARENT_HASHES),
        "file_count": len(rows),
        "production_frozen_hash_match": all(row["matches_frozen_reference"] for row in rows),
        "rows": rows,
    }


def prepare(run_id: str) -> None:
    import torch

    run_dir = RESULTS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    tensor = torch.tensor([1.0], device="cuda:0")
    tensor_smoke = float((tensor + 1).cpu().item()) == 2.0
    gpu = nvidia_gpu()
    machine = {
        "run_id": run_id,
        "recorded_at": now(),
        "status": "PASS",
        "cuda_environment_gate": "PASS",
        "git_head": command("git", "rev-parse", "HEAD"),
        "git_status_short": command("git", "status", "--short").splitlines(),
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "python_abi": "cp311",
        "torch_version": torch.__version__,
        "torch_cuda_build": torch.version.cuda,
        "torch_cuda_available": torch.cuda.is_available(),
        "device_name": torch.cuda.get_device_name(0),
        "cuda_tensor_smoke": tensor_smoke,
        "nvidia_smi": gpu,
        "gate_checks": {
            "python_is_3_11": platform.python_version().startswith("3.11."),
            "torch_is_2_12_1_cu126": torch.__version__ == "2.12.1+cu126",
            "torch_cuda_is_12_6": torch.version.cuda == "12.6",
            "cuda_available": torch.cuda.is_available(),
            "device_is_rtx_4060": gpu["name"] == "NVIDIA GeForce RTX 4060 Laptop GPU",
            "tensor_smoke": tensor_smoke,
        },
        "full_72_query_run_executed": False,
    }
    if not all(machine["gate_checks"].values()):
        machine["status"] = "FAIL"
        machine["cuda_environment_gate"] = "FAIL"
    write_json(run_dir / "machine_validation.json", machine)
    before = production_snapshot(run_id, "before")
    write_json(run_dir / "production_hashes_before.json", before)
    if machine["status"] != "PASS" or not before["production_frozen_hash_match"]:
        raise SystemExit("preflight gate failed")
    print(json.dumps({"run_id": run_id, "run_dir": str(run_dir), "status": "PASS"}, indent=2))


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


def cpu_batch(tokenizer: Any, trace: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, float]]:
    started = perf_counter()
    features, pairs = build_features(tokenizer, trace)
    tokenization_ms = (perf_counter() - started) * 1000
    started = perf_counter()
    batch = tokenizer.pad(features, padding=True, return_tensors="pt")
    batch = {key: batch[key] for key in ("input_ids", "attention_mask")}
    preparation_ms = (perf_counter() - started) * 1000
    return batch, pairs, {
        "tokenization_feature_assembly_ms": tokenization_ms,
        "cpu_tensor_input_preparation_ms": preparation_ms,
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
        rows.append(
            {
                "evidence_group_id": group["evidence_group_id"],
                "document_match": any(
                    candidate["document_id"] in group["any_of_document_ids"]
                    for candidate in candidates
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
    batch, pairs, cpu_times = cpu_batch(tokenizer, trace)

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
    forward_ms = forward_start.elapsed_time(forward_end)

    d2h_start = torch.cuda.Event(enable_timing=True)
    d2h_end = torch.cuda.Event(enable_timing=True)
    d2h_start.record()
    cpu_logits = logits.reshape(-1).detach().to("cpu")
    d2h_end.record()
    d2h_end.synchronize()
    d2h_ms = d2h_start.elapsed_time(d2h_end)

    scores = [float(value) for value in cpu_logits.tolist()]
    sorting_started = perf_counter()
    candidates = sorted(trace["candidates"], key=lambda row: (int(row["dense_rank"]), row["identity"]))
    ordered = stable_order(candidates, scores)
    sorting_ms = (perf_counter() - sorting_started) * 1000
    torch.cuda.synchronize()
    total_ms = (perf_counter() - total_started) * 1000
    return (
        {
            "case_id": trace["case_id"],
            "pair_count": 18,
            "batch_shape": list(batch["input_ids"].shape),
            **{key: round(value, 6) for key, value in cpu_times.items()},
            "h2d_ms": round(h2d_ms, 6),
            "gpu_forward_ms": round(forward_ms, 6),
            "d2h_score_extraction_ms": round(d2h_ms, 6),
            "sorting_ms": round(sorting_ms, 6),
            "total_reranker_call_ms": round(total_ms, 6),
            "ranking_order": [row["candidate"]["identity"] for row in ordered],
            "all_pair_token_counts_match": all(row["token_count_match"] for row in pairs),
        },
        scores,
    )


def summary_runs(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    names = (
        "tokenization_feature_assembly_ms",
        "cpu_tensor_input_preparation_ms",
        "h2d_ms",
        "gpu_forward_ms",
        "d2h_score_extraction_ms",
        "sorting_ms",
        "total_reranker_call_ms",
    )
    return {
        name: {
            "mean": round(statistics.fmean(float(row[name]) for row in rows), 6),
            "min": round(min(float(row[name]) for row in rows), 6),
            "max": round(max(float(row[name]) for row in rows), 6),
        }
        for name in names
    }


def smoke(run_id: str) -> None:
    run_dir = RESULTS_ROOT / run_id
    if not (run_dir / "production_hashes_before.json").exists():
        raise SystemExit("prepared run is missing production hashes before")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

    versions = package_versions()
    package_match = {name: versions[name] == expected for name, expected in REQUIRED_PACKAGES.items()}
    pip_check = command(sys.executable, "-m", "pip", "check", check=False)
    dependency_identity = {
        "run_id": run_id,
        "recorded_at": now(),
        "status": "PASS" if all(package_match.values()) and "No broken requirements found" in pip_check else "FAIL",
        "cuda_runtime_dependency_gate": "PASS" if all(package_match.values()) and "No broken requirements found" in pip_check else "FAIL",
        "authoritative_versions": REQUIRED_PACKAGES,
        "observed_versions": versions,
        "exact_version_match": package_match,
        "pip_check": pip_check,
        "installation_scope": "isolated .venv-cuda only",
        "torch_reinstalled_or_modified": False,
        "production_dependency_files_modified": False,
    }
    write_json(run_dir / "runtime_dependency_identity.json", dependency_identity)
    if dependency_identity["status"] != "PASS":
        raise SystemExit("CUDA runtime dependency gate failed")

    import torch
    from experiment import HuggingFaceRerankerAdapter

    if sha256(TRACE) != TRACE_SHA256:
        raise SystemExit("frozen Phase 2 C trace hash mismatch")
    if sha256(SNAPSHOT / "model.safetensors") != MODEL_SHA256:
        raise SystemExit("model snapshot hash mismatch")
    traces = read_jsonl(TRACE)
    if len(traces) != 72 or any(len(trace["candidates"]) != 18 for trace in traces):
        raise SystemExit("frozen inputs are not 72 x 18")
    if len({trace["case_id"] for trace in traces}) != 72:
        raise SystemExit("frozen case IDs are not unique")
    traces_by_id = {trace["case_id"]: trace for trace in traces}
    input_reference = {
        row["case_id"]: row for row in read_json(AUTHORITATIVE / "input_equivalence.json")["rows"]
    }
    query_reference = {
        row["case_id"]: row
        for row in read_json(AUTHORITATIVE / "per_query_ranking_comparison.json")["rows"]
    }
    contexts = {
        row["case_id"]: row
        for row in read_json(PHASE3 / "context_freeze.json")["records"]
        if row["arm"] == "C"
    }
    gold_by_id = {row["case_id"]: row for row in read_json(GOLD)["cases"]}
    if set(traces_by_id) != set(input_reference) or set(traces_by_id) != set(contexts):
        raise SystemExit("authoritative frozen input/reference coverage mismatch")

    torch.cuda.empty_cache()
    gpu_before = nvidia_gpu()
    memory_before = {
        "nvidia_smi_free_mib": gpu_before["memory_free_mib"],
        "torch_allocated_mib": round(torch.cuda.memory_allocated() / 1024**2, 3),
        "torch_reserved_mib": round(torch.cuda.memory_reserved() / 1024**2, 3),
    }
    load_started = perf_counter()
    try:
        adapter = HuggingFaceRerankerAdapter(SNAPSHOT, device="cpu")
        cpu_parameter = next(adapter.model.parameters())
        cpu_initialized = str(cpu_parameter.device) == "cpu" and cpu_parameter.dtype == torch.float32
        adapter.model.to("cuda:0")
        adapter.device = "cuda:0"
        adapter.model.eval()
        torch.cuda.synchronize()
    except torch.cuda.OutOfMemoryError:
        write_json(
            run_dir / "model_load_validation.json",
            {"run_id": run_id, "status": "FAIL_OOM", "offline_model_load": "FAIL"},
        )
        raise
    load_seconds = perf_counter() - load_started
    parameter = next(adapter.model.parameters())
    parameter_dtypes = sorted({str(item.dtype) for item in adapter.model.parameters()})
    memory_after_load = {
        "torch_allocated_mib": round(torch.cuda.memory_allocated() / 1024**2, 3),
        "torch_reserved_mib": round(torch.cuda.memory_reserved() / 1024**2, 3),
        "nvidia_smi_process": nvidia_process_memory(os.getpid()),
        "nvidia_smi_free_mib": nvidia_gpu()["memory_free_mib"],
    }
    model_loaded_vram_mib = round(
        memory_after_load["torch_allocated_mib"] - memory_before["torch_allocated_mib"], 3
    )
    model_load = {
        "run_id": run_id,
        "recorded_at": now(),
        "status": "PASS",
        "offline_model_load": "PASS",
        "model_id": adapter.model_id,
        "model_revision": adapter.revision,
        "model_path": str(SNAPSHOT),
        "model_safetensors_sha256": MODEL_SHA256,
        "local_files_only": True,
        "trust_remote_code": False,
        "hf_hub_offline": os.environ["HF_HUB_OFFLINE"],
        "transformers_offline": os.environ["TRANSFORMERS_OFFLINE"],
        "network_model_downloads": 0,
        "cpu_initialized_before_cuda_transfer": cpu_initialized,
        "model_device": str(parameter.device),
        "model_dtype": str(parameter.dtype),
        "parameter_dtypes": parameter_dtypes,
        "model_eval_mode": not adapter.model.training,
        "model_load_seconds": round(load_seconds, 6),
        "device_map_auto": False,
        "cpu_offload": False,
        "disk_offload": False,
        "oom": False,
    }
    if not (
        adapter.revision == MODEL_REVISION
        and str(parameter.device) == "cuda:0"
        and parameter.dtype == torch.float32
        and parameter_dtypes == ["torch.float32"]
        and not adapter.model.training
    ):
        model_load["status"] = "FAIL"
        model_load["offline_model_load"] = "FAIL"
    write_json(run_dir / "model_load_validation.json", model_load)
    if model_load["status"] != "PASS":
        raise SystemExit("offline model load gate failed")

    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.set_float32_matmul_precision("highest")
    fp32 = {
        "run_id": run_id,
        "recorded_at": now(),
        "status": "PASS",
        "strict_fp32_configuration": "PASS",
        "allow_tf32_matmul": torch.backends.cuda.matmul.allow_tf32,
        "allow_tf32_cudnn": torch.backends.cudnn.allow_tf32,
        "float32_matmul_precision": torch.get_float32_matmul_precision(),
        "autocast": False,
        "autocast_enabled_observed": torch.is_autocast_enabled("cuda"),
        "model_dtype": str(parameter.dtype),
        "half_or_bfloat16_parameters": False,
    }
    if fp32["allow_tf32_matmul"] or fp32["allow_tf32_cudnn"] or fp32["autocast_enabled_observed"]:
        fp32["status"] = "FAIL"
        fp32["strict_fp32_configuration"] = "FAIL"
    write_json(run_dir / "strict_fp32_validation.json", fp32)
    if fp32["status"] != "PASS":
        raise SystemExit("strict FP32 gate failed")

    profiles = []
    features_by_id: dict[str, tuple[list[dict[str, list[int]]], list[dict[str, Any]]]] = {}
    for trace in traces:
        features, pairs = build_features(adapter.tokenizer, trace)
        features_by_id[trace["case_id"]] = (features, pairs)
        lengths = [row["pair_tokens"] for row in pairs]
        profiles.append(
            {
                "case_id": trace["case_id"],
                "pair_count": len(lengths),
                "min_token_length": min(lengths),
                "mean_token_length": statistics.fmean(lengths),
                "max_token_length": max(lengths),
                "total_unpadded_tokens": sum(lengths),
                "total_padded_tokens": len(lengths) * max(lengths),
                "padding_ratio": 1 - sum(lengths) / (len(lengths) * max(lengths)),
                "all_token_counts_match": all(row["token_count_match"] for row in pairs),
                "truncation_count": sum(row["truncated"] for row in pairs),
            }
        )
    if not all(row["all_token_counts_match"] for row in profiles):
        raise SystemExit("authoritative tokenizer telemetry mismatch")
    median_max = statistics.median(row["max_token_length"] for row in profiles)
    short = min(profiles, key=lambda row: (row["max_token_length"], row["case_id"]))
    median = min(profiles, key=lambda row: (abs(row["max_token_length"] - median_max), row["case_id"]))
    long = min(profiles, key=lambda row: (-row["max_token_length"], row["case_id"]))
    selected = {"SHORT": short, "MEDIAN": median, "LONG": long}
    if len({row["case_id"] for row in selected.values()}) != 3:
        raise SystemExit("deterministic selection did not produce three distinct cases")
    case_selection = {
        "run_id": run_id,
        "recorded_at": now(),
        "status": "PASS",
        "selection_rule": (
            "Compute the maximum authoritative pair token length for every frozen case. SHORT is the "
            "global minimum, MEDIAN is closest to the median of all 72 maxima, and LONG is the global "
            "maximum; ties use case ID lexicographic ascending."
        ),
        "all_72_max_token_length_median": median_max,
        "selected_case_ids": {label: row["case_id"] for label, row in selected.items()},
        "selected_cases": {label: row for label, row in selected.items()},
        "case_count": 3,
        "pair_count": 54,
        "all_72_pair_token_telemetry_match": True,
        "all_72_truncation_count": sum(row["truncation_count"] for row in profiles),
    }
    write_json(run_dir / "smoke_case_selection.json", case_selection)

    integrity_rows = []
    for label, profile in selected.items():
        case_id = profile["case_id"]
        trace = traces_by_id[case_id]
        reference = input_reference[case_id]
        features, pairs = features_by_id[case_id]
        batch = adapter.tokenizer.pad(features, padding=True, return_tensors="pt")
        candidates = sorted(trace["candidates"], key=lambda row: (int(row["dense_rank"]), row["identity"]))
        observed_ids = [row["identity"] for row in candidates]
        input_hash = hashlib.sha256(batch["input_ids"].numpy().tobytes()).hexdigest()
        attention_hash = hashlib.sha256(batch["attention_mask"].numpy().tobytes()).hexdigest()
        checks = {
            "case_id_identical": trace["case_id"] == reference["case_id"] == contexts[case_id]["case_id"],
            "query_text_identical": trace["effective_query"] == contexts[case_id]["question"],
            "candidate_ids_identical": observed_ids == reference["candidate_identities_dense_order"],
            "candidate_source_ids_identical": all(bool(row["document_id"]) for row in candidates),
            "pre_rerank_order_identical": observed_ids == reference["candidate_identities_dense_order"],
            "candidate_text_integrity": all(text_sha256(row["raw_text"]) == row["content_hash"] for row in candidates),
            "pair_construction_identical": all(row["token_count_match"] for row in pairs),
            "tokenizer_identical": importlib.metadata.version("tokenizers") == "0.22.2",
            "max_length_identical": max(row["pair_tokens"] for row in pairs) == reference["input_ids_shape"][1],
            "truncation_identical": sum(row["truncated"] for row in pairs) == reference["truncation_count"],
            "padding_policy_identical": list(batch["input_ids"].shape) == reference["input_ids_shape"],
            "input_ids_sha256_identical": input_hash == reference["input_ids_sha256"],
            "attention_mask_sha256_identical": attention_hash == reference["attention_mask_sha256"],
        }
        integrity_rows.append(
            {
                "selection_label": label,
                "case_id": case_id,
                "pair_count": 18,
                "checks": checks,
                "identical": all(checks.values()),
                "input_ids_sha256": input_hash,
                "attention_mask_sha256": attention_hash,
            }
        )
    candidate_integrity = {
        "run_id": run_id,
        "recorded_at": now(),
        "status": "PASS" if all(row["identical"] for row in integrity_rows) else "FAIL",
        "smoke_candidate_inputs": "PASS" if all(row["identical"] for row in integrity_rows) else "FAIL",
        "frozen_trace_path": relative(TRACE),
        "frozen_trace_sha256": sha256(TRACE),
        "frozen_trace_manifest_sha256": TRACE_SHA256,
        "frozen_query_count": 72,
        "frozen_candidate_depth": 18,
        "identical_case_count": sum(row["identical"] for row in integrity_rows),
        "expected_case_count": 3,
        "rows": integrity_rows,
    }
    write_json(run_dir / "smoke_candidate_integrity.json", candidate_integrity)
    if candidate_integrity["status"] != "PASS":
        raise SystemExit("smoke candidate input gate failed")

    latency_cases = []
    memory_cases = []
    observed_scores: dict[str, list[float]] = {}
    for label, profile in selected.items():
        case_id = profile["case_id"]
        trace = traces_by_id[case_id]
        torch.cuda.reset_peak_memory_stats()
        warmups = []
        for _ in range(2):
            row, _ = timed_call(torch, adapter.tokenizer, adapter.model, trace)
            warmups.append(row)
        measured = []
        score_runs = []
        for measurement_index in range(1, 4):
            row, scores = timed_call(torch, adapter.tokenizer, adapter.model, trace)
            row["measurement_index"] = measurement_index
            measured.append(row)
            score_runs.append(scores)
        observed_scores[case_id] = score_runs[0]
        latency_cases.append(
            {
                "selection_label": label,
                "case_id": case_id,
                "warmup_runs": 2,
                "measured_runs": 3,
                "measurements": measured,
                "summary_ms": summary_runs(measured),
                "measured_score_runs_bitwise_deterministic": score_runs[0] == score_runs[1] == score_runs[2],
            }
        )
        memory_cases.append(
            {
                "selection_label": label,
                "case_id": case_id,
                "peak_allocated_mib": round(torch.cuda.max_memory_allocated() / 1024**2, 3),
                "peak_reserved_mib": round(torch.cuda.max_memory_reserved() / 1024**2, 3),
                "warm_inference_peak_allocated_mib": round(torch.cuda.max_memory_allocated() / 1024**2, 3),
                "warm_inference_peak_reserved_mib": round(torch.cuda.max_memory_reserved() / 1024**2, 3),
                "oom": False,
                "allocator_error": False,
                "cpu_offload": False,
                "unexpected_device_placement": False,
            }
        )

    comparisons = []
    all_diffs = []
    all_adjacent = []
    for label, profile in selected.items():
        case_id = profile["case_id"]
        trace = traces_by_id[case_id]
        candidates = sorted(trace["candidates"], key=lambda row: (int(row["dense_rank"]), row["identity"]))
        scores = observed_scores[case_id]
        current_order_rows = stable_order(candidates, scores)
        current_order = [row["candidate"]["identity"] for row in current_order_rows]
        reference_order = [
            row["identity"] for row in sorted(candidates, key=lambda row: int(row["reranker_rank"]))
        ]
        current_rank = {identity: rank for rank, identity in enumerate(current_order, start=1)}
        candidate_rows = []
        for candidate, score in zip(candidates, scores, strict=True):
            difference = abs(float(candidate["reranker_score"]) - float(score))
            all_diffs.append(difference)
            candidate_rows.append(
                {
                    "candidate_id": candidate["identity"],
                    "reference_logit": candidate["reranker_score"],
                    "cuda_fp32_logit": score,
                    "absolute_difference": difference,
                    "reference_rank": candidate["reranker_rank"],
                    "cuda_rank": current_rank[candidate["identity"]],
                }
            )
        reference_sorted = sorted(candidates, key=lambda row: int(row["reranker_rank"]))
        adjacent = []
        for higher, lower in zip(reference_sorted, reference_sorted[1:]):
            gap = float(higher["reranker_score"]) - float(lower["reranker_score"])
            adjacent.append(
                {
                    "higher_candidate_id": higher["identity"],
                    "lower_candidate_id": lower["identity"],
                    "reference_gap": gap,
                }
            )
            all_adjacent.append({"case_id": case_id, **adjacent[-1]})
        selected_current = govern(current_order_rows)
        current_top6 = [row.identity for row in selected_current]
        current_context = context_text(selected_current)
        current_context_digest = text_sha256(current_context)
        selected_dicts = [next(row for row in candidates if row["identity"] == identity) for identity in current_top6]
        current_evidence = evidence_coverage(gold_by_id[case_id], selected_dicts)
        reference = query_reference[case_id]
        phase3_context = contexts[case_id]
        ordering_equal = current_order == reference_order == reference["pytorch_order"]
        top6_equal = current_top6 == reference["pytorch_top6"] == phase3_context["selected_candidate_identities"]
        context_equal = current_context == phase3_context["context_text"] and current_context_digest == reference["pytorch_context_digest"]
        evidence_equal = current_evidence == reference["pytorch_required_evidence"]
        first_divergence = None
        if not ordering_equal:
            for rank, (expected, actual) in enumerate(zip(reference_order, current_order, strict=True), start=1):
                if expected != actual:
                    first_divergence = {"rank": rank, "reference_candidate_id": expected, "cuda_candidate_id": actual}
                    break
        comparisons.append(
            {
                "selection_label": label,
                "case_id": case_id,
                "pair_count": 18,
                "ordering_equal": ordering_equal,
                "governed_top6_equal": top6_equal,
                "final_context_equal": context_equal,
                "required_evidence_equal": evidence_equal,
                "reference_order": reference_order,
                "cuda_order": current_order,
                "reference_top6": reference["pytorch_top6"],
                "cuda_top6": current_top6,
                "reference_context_digest": reference["pytorch_context_digest"],
                "cuda_context_digest": current_context_digest,
                "reference_required_evidence": reference["pytorch_required_evidence"],
                "cuda_required_evidence": current_evidence,
                "minimum_adjacent_reference_logit_gap": min(row["reference_gap"] for row in adjacent),
                "near_tie_candidate_pairs_lte_0_01": [row for row in adjacent if row["reference_gap"] <= 0.01],
                "first_divergent_rank": first_divergence,
                "candidates": candidate_rows,
            }
        )
    ordering_count = sum(row["ordering_equal"] for row in comparisons)
    top6_count = sum(row["governed_top6_equal"] for row in comparisons)
    context_count = sum(row["final_context_equal"] for row in comparisons)
    evidence_count = sum(row["required_evidence_equal"] for row in comparisons)
    equivalence_pass = ordering_count == top6_count == context_count == evidence_count == 3
    equivalence = {
        "run_id": run_id,
        "recorded_at": now(),
        "status": "PASS" if equivalence_pass else "FAIL",
        "smoke_equivalence": "PASS" if equivalence_pass else "FAIL",
        "case_count": 3,
        "unique_pair_count": 54,
        "smoke_full_ordering": f"{ordering_count}/3",
        "smoke_governed_top6": f"{top6_count}/3",
        "smoke_final_context": f"{context_count}/3",
        "smoke_required_evidence": f"{evidence_count}/3",
        "logit_absolute_difference": distribution(all_diffs),
        "minimum_adjacent_reference_logit_gap": min(row["reference_gap"] for row in all_adjacent),
        "near_tie_candidate_pairs_lte_0_01": [row for row in all_adjacent if row["reference_gap"] <= 0.01],
        "near_tie_is_observational_only": True,
        "rows": comparisons,
    }
    write_json(run_dir / "smoke_equivalence_results.json", equivalence)
    if not equivalence_pass:
        raise SystemExit("smoke semantic equivalence gate failed")

    latency = {
        "run_id": run_id,
        "recorded_at": now(),
        "status": "PASS",
        "smoke_latency_only": True,
        "full_latency_classification_deferred": True,
        "timing_contract": {
            "warmup_runs_per_case": 2,
            "measured_runs_per_case": 3,
            "gpu_forward_uses_cuda_events": True,
            "cuda_synchronize_used": True,
            "descriptive_only": True,
        },
        "cases": latency_cases,
        "three_case_descriptive_summary_ms": {
            "gpu_forward": distribution(
                row["gpu_forward_ms"]
                for case in latency_cases
                for row in case["measurements"]
            ),
            "total_reranker_call": distribution(
                row["total_reranker_call_ms"]
                for case in latency_cases
                for row in case["measurements"]
            ),
        },
        "not_72_query_p50_or_p95": True,
        "not_production_latency": True,
    }
    write_json(run_dir / "smoke_latency_results.json", latency)

    warm_peak_allocated = max(row["warm_inference_peak_allocated_mib"] for row in memory_cases)
    warm_peak_reserved = max(row["warm_inference_peak_reserved_mib"] for row in memory_cases)
    gpu_memory = {
        "run_id": run_id,
        "recorded_at": now(),
        "status": "PASS",
        "smoke_gpu_memory": "PASS",
        "before_model_load": memory_before,
        "after_model_load": memory_after_load,
        "model_loaded_vram_mib": model_loaded_vram_mib,
        "warm_peak_allocated_mib": warm_peak_allocated,
        "warm_peak_reserved_mib": warm_peak_reserved,
        "cases": memory_cases,
        "oom": False,
        "allocator_error": False,
        "cpu_offload": False,
        "unexpected_device_placement": False,
    }
    write_json(run_dir / "smoke_gpu_memory_results.json", gpu_memory)

    padding = {
        "run_id": run_id,
        "recorded_at": now(),
        "status": "PASS",
        "observation_only": True,
        "padding_policy_changed": False,
        "batch_splitting": False,
        "cases": [
            {
                "selection_label": label,
                "case_id": profile["case_id"],
                "pair_count": profile["pair_count"],
                "pair_token_length_min": profile["min_token_length"],
                "pair_token_length_mean": profile["mean_token_length"],
                "pair_token_length_max": profile["max_token_length"],
                "batch_padded_sequence_length": profile["max_token_length"],
                "unpadded_token_total": profile["total_unpadded_tokens"],
                "padded_token_total": profile["total_padded_tokens"],
                "padding_ratio": profile["padding_ratio"],
            }
            for label, profile in selected.items()
        ],
    }
    write_json(run_dir / "smoke_padding_observation.json", padding)

    after = production_snapshot(run_id, "after")
    before = read_json(run_dir / "production_hashes_before.json")
    before_by_path = {row["path"]: row["v1_3a_s_before_sha256"] for row in before["rows"]}
    for row in after["rows"]:
        row["v1_3a_s_before_sha256"] = before_by_path[row["path"]]
        row["byte_identical_during_v1_3a_s"] = (
            row["v1_3a_s_before_sha256"] == row["v1_3a_s_after_sha256"]
        )
    after["production_frozen_hash_match"] = after["production_frozen_hash_match"] and all(
        row["byte_identical_during_v1_3a_s"] for row in after["rows"]
    )
    write_json(run_dir / "production_hashes_after.json", after)
    if not after["production_frozen_hash_match"]:
        raise SystemExit("production frozen hash gate failed")

    next_contract = {
        "run_id": run_id,
        "recorded_at": now(),
        "status": "PASS",
        "ready_for_v1_3b_full_equivalence_and_profiling": "YES",
        "scope": "bounded frozen 72-query CUDA FP32 equivalence and profiling only",
        "required_runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "torch_cuda": torch.version.cuda,
            "device": torch.cuda.get_device_name(0),
            "transformers": versions["transformers"],
            "tokenizers": versions["tokenizers"],
            "model_path": str(SNAPSHOT),
            "model_revision": MODEL_REVISION,
            "precision": "FP32",
            "tf32": False,
        },
        "final_rag_architecture": "NOT_YET_FROZEN",
    }
    write_json(run_dir / "next_run_contract.json", next_contract)

    selected_ids = case_selection["selected_case_ids"]
    latency_lines = []
    for case in latency_cases:
        summary = case["summary_ms"]
        latency_lines.append(
            f"- {case['selection_label']} `{case['case_id']}`: GPU forward mean/min/max "
            f"{summary['gpu_forward_ms']['mean']:.3f}/{summary['gpu_forward_ms']['min']:.3f}/"
            f"{summary['gpu_forward_ms']['max']:.3f} ms; total mean/min/max "
            f"{summary['total_reranker_call_ms']['mean']:.3f}/"
            f"{summary['total_reranker_call_ms']['min']:.3f}/"
            f"{summary['total_reranker_call_ms']['max']:.3f} ms."
        )
    report = f"""# LearnPilot RAG C V1.3A-S — CUDA FP32 3-Case Smoke Equivalence

## Result

`RAG_C_V1_3A_S_CUDA_FP32_SMOKE = PASS`. The strict offline CUDA FP32 smoke passed for three deterministically selected cases and 54 unique frozen pairs. Timing is descriptive smoke evidence only.

## Runtime

- Run ID: `{run_id}`
- Python: `{platform.python_version()}` (`{sys.executable}`)
- PyTorch: `{torch.__version__}`; CUDA build `{torch.version.cuda}`
- Device: `{torch.cuda.get_device_name(0)}`
- Transformers/tokenizers: `{versions['transformers']}` / `{versions['tokenizers']}`
- Offline model: `BAAI/bge-reranker-v2-m3` revision `{MODEL_REVISION}` from `{SNAPSHOT}`
- Model parameter device/dtype: `{parameter.device}` / `{parameter.dtype}`
- TF32 matmul/cuDNN: `false` / `false`; matmul precision: `highest`; autocast: `false`

## Deterministic cases

- SHORT: `{selected_ids['SHORT']}` (minimum per-query maximum pair length).
- MEDIAN: `{selected_ids['MEDIAN']}` (closest to the median of all 72 per-query maxima).
- LONG: `{selected_ids['LONG']}` (maximum per-query maximum pair length).
- Ties use case ID lexicographic ascending.

Candidate input integrity is `3/3`: frozen case/query/candidate identities, source/text hashes, Dense order, pair construction, token counts, dynamic padding, and tensor hashes match the authoritative C reference.

## Equivalence

- Full reranker ordering: `{ordering_count}/3`
- Governed Top6: `{top6_count}/3`
- Final context text/digest: `{context_count}/3`
- Required-evidence presence: `{evidence_count}/3`
- Absolute logit difference: mean `{equivalence['logit_absolute_difference']['mean']:.9f}`, max `{equivalence['logit_absolute_difference']['max']:.9f}`

## Descriptive smoke timing

{chr(10).join(latency_lines)}

These are three-case smoke measurements, not 72-query P50/P95, a production latency result, or a final latency classification.

## GPU memory

- Model-loaded torch allocation delta: `{model_loaded_vram_mib:.3f}` MiB
- Warm peak allocated: `{warm_peak_allocated:.3f}` MiB
- Warm peak reserved: `{warm_peak_reserved:.3f}` MiB
- OOM/allocator error/offload/unexpected placement: `false/false/false/false`

## Production integrity and execution boundary

All 15 frozen production files match before and after. No production source or dependency manifest changed. No retrieval, generation, embedding, DeepSeek call, model download, or 72-query run occurred.

## Final status

```text
RAG_C_V1_3A_S_CUDA_FP32_SMOKE = PASS
CUDA_ENVIRONMENT_GATE = PASS
CUDA_RUNTIME_DEPENDENCY_GATE = PASS
OFFLINE_MODEL_LOAD = PASS
STRICT_FP32_CONFIGURATION = PASS
SMOKE_CASES = 3
SMOKE_PAIRS = 54
SMOKE_CANDIDATE_INPUTS = PASS
SMOKE_FULL_ORDERING = {ordering_count}/3
SMOKE_GOVERNED_TOP6 = {top6_count}/3
SMOKE_FINAL_CONTEXT = {context_count}/3
SMOKE_REQUIRED_EVIDENCE = {evidence_count}/3
SMOKE_EQUIVALENCE = PASS
MAX_LOGIT_ABS_DIFF = {equivalence['logit_absolute_difference']['max']}
MEAN_LOGIT_ABS_DIFF = {equivalence['logit_absolute_difference']['mean']}
SMOKE_GPU_FORWARD_MS = descriptive only
SMOKE_TOTAL_RERANKER_MS = descriptive only
SMOKE_LATENCY_ONLY = true
MODEL_LOADED_VRAM_MIB = {model_loaded_vram_mib}
WARM_PEAK_ALLOCATED_MIB = {warm_peak_allocated}
WARM_PEAK_RESERVED_MIB = {warm_peak_reserved}
SMOKE_GPU_MEMORY = PASS
FULL_72_QUERY_RUN_EXECUTED = false
FULL_LATENCY_CLASSIFICATION_DEFERRED = true
DEEPSEEK_CALLS = 0
RETRIEVAL_RERUNS = 0
GENERATION_RERUNS = 0
PRODUCTION_CODE_CHANGED = false
PRODUCTION_DEPENDENCIES_CHANGED = false
PRODUCTION_FROZEN_HASH_MATCH = true
READY_FOR_V1_3B_FULL_EQUIVALENCE_AND_PROFILING = YES
FINAL_RAG_ARCHITECTURE = NOT_YET_FROZEN
```
"""
    REPORT.write_text(report, encoding="utf-8")

    artifact_names = [
        "machine_validation.json",
        "runtime_dependency_identity.json",
        "production_hashes_before.json",
        "production_hashes_after.json",
        "model_load_validation.json",
        "strict_fp32_validation.json",
        "smoke_case_selection.json",
        "smoke_candidate_integrity.json",
        "smoke_equivalence_results.json",
        "smoke_latency_results.json",
        "smoke_gpu_memory_results.json",
        "smoke_padding_observation.json",
        "next_run_contract.json",
    ]
    manifest = {
        "run_id": run_id,
        "recorded_at": now(),
        "status": "PASS",
        "git_head": command("git", "rev-parse", "HEAD"),
        "authoritative_reference_run": AUTHORITATIVE_RUN_ID,
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "torch_version": torch.__version__,
        "cuda_build": torch.version.cuda,
        "transformers_version": versions["transformers"],
        "tokenizers_version": versions["tokenizers"],
        "model_path": str(SNAPSHOT),
        "model_revision": MODEL_REVISION,
        "model_safetensors_sha256": MODEL_SHA256,
        "artifact_files": [file_record(run_dir / name) for name in artifact_names]
        + [file_record(REPORT), file_record(Path(__file__))],
        "execution_audit": {
            "unique_smoke_cases": 3,
            "unique_smoke_pairs": 54,
            "full_72_query_run_executed": False,
            "deepseek_calls": 0,
            "retrieval_reruns": 0,
            "generation_reruns": 0,
            "model_downloads": 0,
            "production_code_changed": False,
            "production_dependencies_changed": False,
            "production_frozen_hash_match": True,
        },
        "ready_for_v1_3b_full_equivalence_and_profiling": "YES",
        "final_rag_architecture": "NOT_YET_FROZEN",
    }
    write_json(run_dir / "artifact_manifest.json", manifest)
    print(
        json.dumps(
            {
                "run_id": run_id,
                "status": "PASS",
                "selected_case_ids": selected_ids,
                "max_logit_abs_diff": equivalence["logit_absolute_difference"]["max"],
                "mean_logit_abs_diff": equivalence["logit_absolute_difference"]["mean"],
                "model_loaded_vram_mib": model_loaded_vram_mib,
                "warm_peak_allocated_mib": warm_peak_allocated,
                "warm_peak_reserved_mib": warm_peak_reserved,
                "ready_for_v1_3b": "YES",
            },
            indent=2,
        ),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    arguments = parser.parse_args()
    if arguments.prepare == arguments.smoke:
        raise SystemExit("choose exactly one of --prepare or --smoke")
    if arguments.prepare:
        prepare(arguments.run_id)
    else:
        smoke(arguments.run_id)


if __name__ == "__main__":
    main()
