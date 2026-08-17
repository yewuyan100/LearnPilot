from __future__ import annotations

import hashlib
import importlib.metadata
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
V1 = ROOT / "evals/rag_real_world_corpus/v1"
sys.path.insert(0, str(V1))

from canonical_model_path import resolve_canonical_reranker_model_path  # noqa: E402

RESULTS_ROOT = V1 / "results/c_v1_2_onnx_runtime_equivalence"
LOCAL_SITE = ROOT / ".tmp/c_v1_2_onnx_runtime/site-packages"
SNAPSHOT = resolve_canonical_reranker_model_path()

DESIGN_SHA = "442bedce1c43b27b3557b0055708342edd278e98bcac0c12a68c1390fe88f655"
PHASE2_RUN_ID = "20260814T095542Z-1317c6a7"
PHASE3_RUN_ID = "20260814T123142Z-8852712b"
PHASE4_RUN_ID = "20260814T131417Z-04dfc031"
C_AUDIT_RUN_ID = "20260814T142012Z-015c3ca0"
MANIFESTS = {
    "phase2": (
        V1 / f"results/hybrid_rerank_phase2_v1_1/{PHASE2_RUN_ID}/artifact_manifest.json",
        "69cca881f7192317f464c682b2e572a2d062f07975d28939d97488d6bb2f2c50",
    ),
    "phase3": (
        V1 / f"results/hybrid_rerank_phase3_v1_1/{PHASE3_RUN_ID}/artifact_manifest.json",
        "f160b6b8f11fd12d2c98a9fa94d72bc54e67b12296247989e2d7187f1e3d9dcc",
    ),
    "phase4": (
        V1 / f"results/hybrid_rerank_phase4_v1_1/{PHASE4_RUN_ID}/artifact_manifest.json",
        "d9ead14197b02540e798035bb140f842f30bcb3582efd4a730c536e23d8e9be2",
    ),
    "c_v1_1_audit": (
        V1 / f"results/c_v1_1_regression_latency_audit/{C_AUDIT_RUN_ID}/artifact_manifest.json",
        "01a2d35f123d2ba78a1bf5da3af1a6a95f4b516d02e7cb6997e350e6d12bee56",
    ),
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = hashlib.sha256((stamp + "-c-v1.2-onnx").encode()).hexdigest()[:8]
    return f"{stamp}-{suffix}"


def verify_manifest(path: Path, expected_hash: str) -> dict[str, Any]:
    observed = sha256(path)
    if observed != expected_hash:
        raise SystemExit(f"authoritative manifest drift: {path}: {observed}")
    manifest = read_json(path)
    entries = manifest["result_files"] + manifest["implementation_and_report_files"]
    errors = []
    for entry in entries:
        target = ROOT / entry["path"]
        if not target.is_file():
            errors.append({"path": entry["path"], "reason": "missing"})
            continue
        if sha256(target) != entry["sha256"]:
            errors.append({"path": entry["path"], "reason": "sha256"})
        if target.stat().st_size != entry["size_bytes"]:
            errors.append({"path": entry["path"], "reason": "size"})
    if errors:
        raise SystemExit(f"authoritative manifest entry drift: {errors[:3]}")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": observed,
        "verified_entries": len(entries),
        "errors": errors,
    }


def package_version(name: str) -> str:
    return importlib.metadata.version(name)


def main() -> None:
    if not LOCAL_SITE.is_dir():
        raise SystemExit("experiment-local ONNX toolchain is unavailable")
    sys.path.insert(0, str(LOCAL_SITE))
    import onnx
    import onnxruntime
    import onnxscript
    import torch
    import transformers

    run_id = new_run_id()
    run_dir = RESULTS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    verified_manifests = {
        name: verify_manifest(path, expected) for name, (path, expected) in MANIFESTS.items()
    }
    fixed = {
        "design": (V1 / "ablation_design_v1_1/ablation_design_manifest.json", DESIGN_SHA),
        "gold": (
            V1 / "gold/v1/gold_cases.json",
            "33a0b69901fa47e3fe45be0277228cd4a5519fe780fe5b9d2c52b1bfe614927a",
        ),
        "corpus": (
            V1 / "corpus_manifest.json",
            "6f67d510cd35197f107400d33033972c0c3c84478174e4991e491f6c8e4ab563",
        ),
        "phase2_c_trace": (
            V1 / f"results/hybrid_rerank_phase2_v1_1/{PHASE2_RUN_ID}/arm_C/candidate_traces.jsonl",
            next(
                entry["sha256"]
                for entry in read_json(MANIFESTS["phase2"][0])["result_files"]
                if entry["path"].endswith("arm_C/candidate_traces.jsonl")
            ),
        ),
    }
    fixed_hashes = {}
    for name, (path, expected) in fixed.items():
        observed = sha256(path)
        if observed != expected:
            raise SystemExit(f"frozen input drift: {name}: {observed}")
        fixed_hashes[name] = {
            "path": path.relative_to(ROOT).as_posix(),
            "expected_sha256": expected,
            "observed_sha256": observed,
            "match": True,
        }

    phase2_preflight = read_json(
        V1 / f"results/hybrid_rerank_phase2_v1_1/{PHASE2_RUN_ID}/preflight.json"
    )
    production = []
    for relative, expected in phase2_preflight["production_hashes"].items():
        observed = sha256(ROOT / relative)
        production.append(
            {
                "path": relative,
                "expected_sha256": expected,
                "observed_sha256": observed,
                "match": observed == expected,
            }
        )
    if not all(row["match"] for row in production):
        raise SystemExit("production hash gate failed")

    snapshot_files = []
    expected_snapshot = {
        "config.json": "13dcd6c31d9fec9d1d8e158702072f62d7fa7d312a64b9fe057bec9a08cfe41a",
        "tokenizer_config.json": "7e4c1cc848840aeccdd763458c18dd525eb0f795c992e00ebe9c28554e7db2d4",
        "model.safetensors": "d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286",
    }
    for filename in (
        "config.json",
        "tokenizer_config.json",
        "tokenizer.json",
        "sentencepiece.bpe.model",
        "special_tokens_map.json",
        "model.safetensors",
    ):
        path = SNAPSHOT / filename
        observed = sha256(path)
        if filename in expected_snapshot and observed != expected_snapshot[filename]:
            raise SystemExit(f"snapshot drift: {filename}")
        snapshot_files.append(
            {"name": filename, "sha256": observed, "size_bytes": path.stat().st_size}
        )

    base = {
        "design_version": "V1.1",
        "ablation_design_sha256": DESIGN_SHA,
        "phase2_run_id": PHASE2_RUN_ID,
        "phase3_run_id": PHASE3_RUN_ID,
        "phase4_run_id": PHASE4_RUN_ID,
        "c_v1_1_audit_run_id": C_AUDIT_RUN_ID,
        "c_v1_2_run_id": run_id,
        "recorded_at": now(),
    }
    runtime_contract = {
        **base,
        "status": "FROZEN_BEFORE_EXPORT",
        "model_id": "BAAI/bge-reranker-v2-m3",
        "revision": "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
        "source_runtime": "PyTorch CPU FP32",
        "target_runtime": "ONNX Runtime CPUExecutionProvider FP32",
        "export": {
            "tool": "torch.onnx.export legacy exporter",
            "dynamo": False,
            "opset": 17,
            "external_data": True,
            "constant_folding": True,
            "dynamic_axes": {"input_ids": [0, 1], "attention_mask": [0, 1], "logits": [0]},
        },
        "onnx_session": {
            "providers": ["CPUExecutionProvider"],
            "graph_optimization_level": "ORT_ENABLE_ALL",
            "execution_mode": "ORT_SEQUENTIAL",
            "intra_op_num_threads": 8,
            "inter_op_num_threads": 1,
            "enable_cpu_mem_arena": True,
            "enable_mem_pattern": True,
        },
        "input_contract": {
            "pair_count": 18,
            "pair_order": "ascending frozen Dense rank, stable identity tie-break",
            "input_ids": "int64 [dynamic_batch, dynamic_sequence]",
            "attention_mask": "int64 [dynamic_batch, dynamic_sequence]",
            "token_type_ids": "absent; XLM-R tokenizer does not emit them",
            "pair_token_cap": 1024,
            "truncation": "preserve query, truncate chunk only",
            "padding": "dynamic longest pair per 18-pair query batch",
        },
        "output_contract": {"logits": "float32 [dynamic_batch, 1]"},
        "semantic_contract_changes": 0,
        "candidate_depth": 18,
        "top_k": 6,
    }
    write_json(
        run_dir / "integrity_preflight.json",
        {
            **base,
            "status": "PASS",
            "verified_manifests": verified_manifests,
            "fixed_hashes": fixed_hashes,
            "production_file_count": len(production),
            "production_hashes_before": production,
            "all_production_hashes_match": True,
            "snapshot_files": snapshot_files,
        },
    )
    write_json(run_dir / "runtime_manifest.json", runtime_contract)
    write_json(
        run_dir / "environment_identity.json",
        {
            **base,
            "python": sys.version,
            "packages": {
                "torch": torch.__version__,
                "transformers": transformers.__version__,
                "onnx": onnx.__version__,
                "onnxruntime": onnxruntime.__version__,
                "onnxscript": onnxscript.__version__,
                "numpy": package_version("numpy"),
                "protobuf": package_version("protobuf"),
            },
            "experiment_local_site_packages": str(LOCAL_SITE),
            "production_dependency_files_modified": False,
        },
    )
    write_json(
        run_dir / "external_call_audit.json",
        {
            **base,
            "deepseek_calls": 0,
            "openai_calls": 0,
            "other_external_evaluator_calls": 0,
            "model_hub_calls": 0,
            "model_downloads": 0,
            "generation_calls": 0,
            "retrieval_runs": 0,
            "phase3_or_phase4_reruns": 0,
            "dependency_registry_commands": 2,
            "dependency_registry": "https://pypi.tuna.tsinghua.edu.cn/simple",
            "dependency_install_scope": ".tmp/c_v1_2_onnx_runtime/site-packages only",
            "sandbox_blocked_dependency_attempts": 1,
            "production_modifications": 0,
        },
    )
    write_json(
        run_dir / "run_state.json",
        {**base, "status": "PREFLIGHT_PASS_EXPORT_PENDING"},
    )
    write_json(
        RESULTS_ROOT / "latest_run.json",
        {
            **base,
            "status": "PREFLIGHT_PASS_EXPORT_PENDING",
            "run_directory": run_dir.relative_to(ROOT).as_posix(),
        },
    )
    print(json.dumps({"status": "PASS", "run_id": run_id, "run_dir": str(run_dir)}, indent=2))


if __name__ == "__main__":
    main()
