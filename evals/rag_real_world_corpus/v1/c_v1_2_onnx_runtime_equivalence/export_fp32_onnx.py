from __future__ import annotations

import ctypes
import hashlib
import json
import sys
from ctypes import wintypes
from pathlib import Path
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
V1 = ROOT / "evals/rag_real_world_corpus/v1"
sys.path.insert(0, str(V1))

from canonical_model_path import resolve_canonical_reranker_model_path  # noqa: E402

RESULTS_ROOT = V1 / "results/c_v1_2_onnx_runtime_equivalence"
LOCAL_SITE = ROOT / ".tmp/c_v1_2_onnx_runtime/site-packages"
SNAPSHOT = resolve_canonical_reranker_model_path()
PHASE2 = V1 / "results/hybrid_rerank_phase2_v1_1/20260814T095542Z-1317c6a7"
MODEL_SHA = "d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286"

sys.path.insert(0, str(LOCAL_SITE))
sys.path.insert(0, str(V1 / "hybrid_rerank_phase2_v1_1"))


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


def sample_batch(tokenizer: Any) -> tuple[Any, Any, dict[str, Any]]:
    from experiment import build_xlm_roberta_pair_feature, enforce_pair_token_budget

    traces = read_jsonl(PHASE2 / "arm_C/candidate_traces.jsonl")
    trace = next(row for row in traces if row["case_id"] == "rw-gold-v1-semantic-context-order")
    features = []
    computed_tokens = []
    candidates = sorted(trace["candidates"], key=lambda row: int(row["dense_rank"]))
    for candidate in candidates:
        query_ids = tokenizer.encode(trace["effective_query"], add_special_tokens=False)
        chunk_ids = tokenizer.encode(candidate["raw_text"], add_special_tokens=False)
        pair = enforce_pair_token_budget(
            query_ids,
            chunk_ids,
            special_token_count=tokenizer.num_special_tokens_to_add(pair=True),
        )
        if pair.truncated or pair.total_tokens != candidate["reranker_input_tokens"]:
            raise SystemExit("sample input is not identical to frozen Phase 2 telemetry")
        features.append(build_xlm_roberta_pair_feature(tokenizer, pair))
        computed_tokens.append(pair.total_tokens)
    batch = tokenizer.pad(features, padding=True, return_tensors="pt")
    return batch["input_ids"], batch["attention_mask"], {
        "case_id": trace["case_id"],
        "candidate_identities_dense_order": [row["identity"] for row in candidates],
        "input_tokens": computed_tokens,
        "input_ids_shape": list(batch["input_ids"].shape),
        "input_ids_sha256": hashlib.sha256(batch["input_ids"].numpy().tobytes()).hexdigest(),
        "attention_mask_sha256": hashlib.sha256(
            batch["attention_mask"].numpy().tobytes()
        ).hexdigest(),
    }


def main() -> None:
    latest = read_json(RESULTS_ROOT / "latest_run.json")
    if latest["status"] != "PREFLIGHT_PASS_EXPORT_PENDING":
        raise SystemExit("latest run is not awaiting export")
    run_dir = ROOT / latest["run_directory"]
    model_dir = run_dir / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    if any(model_dir.iterdir()):
        raise SystemExit("export target directory is not empty")
    onnx_path = model_dir / "bge-reranker-v2-m3-fp32.onnx"

    import onnx
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    class LogitsOnly(torch.nn.Module):
        def __init__(self, model: Any):
            super().__init__()
            self.model = model

        def forward(self, input_ids: Any, attention_mask: Any) -> Any:
            return self.model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                return_dict=True,
            ).logits

    memory_baseline = memory_snapshot()
    load_started = perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(
        str(SNAPSHOT), local_files_only=True, trust_remote_code=False
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        str(SNAPSHOT), local_files_only=True, trust_remote_code=False
    )
    model.to("cpu")
    model.eval()
    wrapper = LogitsOnly(model).eval()
    load_seconds = perf_counter() - load_started
    memory_after_pytorch_load = memory_snapshot()
    input_ids, attention_mask, sample = sample_batch(tokenizer)

    export_started = perf_counter()
    with torch.inference_mode():
        torch.onnx.export(
            wrapper,
            (input_ids, attention_mask),
            str(onnx_path),
            input_names=["input_ids", "attention_mask"],
            output_names=["logits"],
            opset_version=17,
            dynamo=False,
            external_data=True,
            dynamic_axes={
                "input_ids": {0: "batch", 1: "sequence"},
                "attention_mask": {0: "batch", 1: "sequence"},
                "logits": {0: "batch"},
            },
            do_constant_folding=True,
        )
    export_seconds = perf_counter() - export_started
    memory_after_export = memory_snapshot()

    graph = onnx.load(str(onnx_path), load_external_data=False)
    opsets = {item.domain or "ai.onnx": item.version for item in graph.opset_import}
    input_contract = [
        {
            "name": item.name,
            "element_type": item.type.tensor_type.elem_type,
            "dimensions": [
                dim.dim_param if dim.dim_param else dim.dim_value
                for dim in item.type.tensor_type.shape.dim
            ],
        }
        for item in graph.graph.input
    ]
    output_contract = [
        {
            "name": item.name,
            "element_type": item.type.tensor_type.elem_type,
            "dimensions": [
                dim.dim_param if dim.dim_param else dim.dim_value
                for dim in item.type.tensor_type.shape.dim
            ],
        }
        for item in graph.graph.output
    ]
    initializer_types: dict[str, int] = {}
    external_initializer_count = 0
    for item in graph.graph.initializer:
        key = str(item.data_type)
        initializer_types[key] = initializer_types.get(key, 0) + 1
        external_initializer_count += int(item.data_location == onnx.TensorProto.EXTERNAL)
    files = []
    for path in sorted(model_dir.iterdir()):
        if path.is_file():
            files.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "sha256": sha256(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    if sha256(SNAPSHOT / "model.safetensors") != MODEL_SHA:
        raise SystemExit("source snapshot changed during export")

    export_manifest = {
        "design_version": "V1.1",
        "c_v1_2_run_id": latest["c_v1_2_run_id"],
        "status": "PASS",
        "source": {
            "model_id": "BAAI/bge-reranker-v2-m3",
            "revision": SNAPSHOT.name,
            "model_safetensors_sha256": MODEL_SHA,
            "model_safetensors_size_bytes": (SNAPSHOT / "model.safetensors").stat().st_size,
            "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
            "parameter_dtype": str(next(model.parameters()).dtype),
            "model_eval_mode": not model.training,
            "grad_enabled_during_export": False,
        },
        "export": {
            "tool": "torch.onnx.export",
            "torch_version": torch.__version__,
            "legacy_exporter_dynamo": False,
            "opset_requested": 17,
            "opsets_observed": opsets,
            "external_data_requested": True,
            "constant_folding": True,
            "export_seconds": round(export_seconds, 6),
            "input_contract": input_contract,
            "output_contract": output_contract,
            "initializer_data_type_counts": initializer_types,
            "external_initializer_count": external_initializer_count,
            "node_count": len(graph.graph.node),
        },
        "sample_input": sample,
        "artifact_files": files,
        "source_snapshot_unchanged_after_export": True,
        "model_load_seconds": round(load_seconds, 6),
        "memory": {
            "baseline_before_pytorch_model_load": memory_baseline,
            "after_pytorch_model_load": memory_after_pytorch_load,
            "after_export": memory_after_export,
            "pytorch_inference_peak": {
                "reliable": False,
                "reason": "not isolated from exporter tracing; no extra reference-logit regeneration was performed",
            },
        },
        "model_hub_calls": 0,
        "model_downloads": 0,
    }
    write_json(run_dir / "model_export_manifest.json", export_manifest)
    runtime = read_json(run_dir / "runtime_manifest.json")
    runtime.update(
        {
            "status": "EXPORT_PASS_EQUIVALENCE_PENDING",
            "export_artifact_files": files,
            "observed_onnx_input_contract": input_contract,
            "observed_onnx_output_contract": output_contract,
        }
    )
    write_json(run_dir / "runtime_manifest.json", runtime)
    state = read_json(run_dir / "run_state.json")
    state["status"] = "EXPORT_PASS_EQUIVALENCE_PENDING"
    write_json(run_dir / "run_state.json", state)
    latest["status"] = "EXPORT_PASS_EQUIVALENCE_PENDING"
    write_json(RESULTS_ROOT / "latest_run.json", latest)
    print(
        json.dumps(
            {
                "status": "PASS",
                "run_id": latest["c_v1_2_run_id"],
                "export_seconds": round(export_seconds, 3),
                "model_files": files,
                "opsets": opsets,
                "input_contract": input_contract,
                "output_contract": output_contract,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
