from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
V1 = ROOT / "evals/rag_real_world_corpus/v1"
sys.path.insert(0, str(V1))

from canonical_model_path import resolve_canonical_reranker_model_path  # noqa: E402

RESULTS_ROOT = V1 / "results/c_v1_3a_cuda_env_and_smoke"
REPORT = ROOT / "RAG_C_V1_3A_CUDA_ENV_AND_SMOKE.md"
MODEL_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
MODEL_PATH = resolve_canonical_reranker_model_path()
VENV = ROOT / ".venv-cuda"
CACHE_ROOT = Path("D:/AI_Cache")
V12_RUN_ID = "20260814T145246Z-298674d5"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def command(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (result.stdout + result.stderr).strip()


def main() -> None:
    latest = read_json(RESULTS_ROOT / "latest_run.json")
    if latest["status"] != "PREFLIGHT_PASS_CUDA_ENV_PENDING":
        raise SystemExit("latest V1.3A run is not in CUDA environment pending state")
    run_id = latest["run_id"]
    run_dir = ROOT / latest["run_directory"]
    preflight = read_json(run_dir / "preflight.json")
    before = read_json(run_dir / "production_hashes_before.json")

    after_rows = []
    for row in before["rows"]:
        observed = sha256(ROOT / row["path"])
        after_rows.append(
            {
                "path": row["path"],
                "frozen_reference_sha256": row["frozen_reference_sha256"],
                "v1_3a_before_sha256": row["v1_3a_before_sha256"],
                "v1_3a_after_sha256": observed,
                "matches_frozen_reference": observed == row["frozen_reference_sha256"],
                "byte_identical_during_v1_3a": observed == row["v1_3a_before_sha256"],
            }
        )
    production_match = all(
        row["matches_frozen_reference"] and row["byte_identical_during_v1_3a"] for row in after_rows
    )
    write_json(
        run_dir / "production_hashes_after.json",
        {
            "run_id": run_id,
            "recorded_at": now(),
            "file_count": len(after_rows),
            "production_frozen_hash_match": production_match,
            "rows": after_rows,
        },
    )

    partial = CACHE_ROOT / "temp/pip-unpack-87a1fud4/torch-2.11.0+cu128-cp311-cp311-win_amd64.whl"
    environment_text = "\n".join(
        [
            f"run_id={run_id}",
            f"recorded_at={now()}",
            f"git_head={preflight['repository']['git_head']}",
            "baseline_python=3.11.9",
            "baseline_torch=2.12.1+cpu",
            "baseline_torch_cuda=None",
            "baseline_transformers=5.12.1",
            "baseline_tokenizers=0.22.2",
            "baseline_safetensors=0.8.0",
            "baseline_numpy=2.4.6",
            f"cuda_venv={VENV}",
            "cuda_venv_python=3.11.9",
            "cuda_venv_installed_packages=pip==24.0,setuptools==65.5.0",
            "requested_torch=2.11.0+cu128",
            "wheel_index=https://download.pytorch.org/whl/cu128",
            "wheel_size_advertised_bytes=2753100000",
            f"partial_wheel_bytes={partial.stat().st_size if partial.exists() else 0}",
            "install_elapsed_seconds=600",
            "install_outcome=STOPPED_BY_10_MINUTE_NO_CLEAR_PROGRESS_RULE",
            "nvidia_smi_gpu=NVIDIA GeForce RTX 4060 Laptop GPU",
            "nvidia_driver=572.83",
            "nvidia_driver_cuda=12.8",
            "nvidia_total_vram_mib=8188",
            "nvidia_free_vram_before_install_mib=7957",
            "nvidia_compute_processes=0",
            "torch_cuda_import_in_isolated_venv=UNAVAILABLE",
            "external_model_downloads=0",
        ]
    ) + "\n"
    (run_dir / "environment_packages.txt").write_text(environment_text, encoding="utf-8")

    common_blocker = {
        "status": "NOT_EXECUTED",
        "reason": "CUDA_ENVIRONMENT_GATE failed before smoke selection/execution",
        "smoke_queries_executed": 0,
        "smoke_pairs_executed": 0,
    }
    write_json(
        run_dir / "smoke_case_selection.json",
        {
            **common_blocker,
            "selection_rule": "deferred; deterministic short/median/long selection was not run after stop gate",
            "selected_case_ids": [],
            "planned_case_count": 3,
            "planned_pair_count": 54,
        },
    )
    write_json(run_dir / "smoke_candidate_integrity.json", common_blocker)
    write_json(run_dir / "smoke_equivalence_results.json", common_blocker)
    write_json(
        run_dir / "smoke_latency_results.json",
        {**common_blocker, "smoke_latency_only": True, "full_latency_classification_deferred": True},
    )
    write_json(
        run_dir / "smoke_gpu_memory_results.json",
        {
            **common_blocker,
            "nvidia_smi_before_install": {
                "gpu": "NVIDIA GeForce RTX 4060 Laptop GPU",
                "total_vram_mib": 8188,
                "free_vram_mib": 7957,
                "used_vram_mib": 0,
                "running_compute_processes": 0,
            },
            "model_loaded_allocated": None,
            "model_loaded_reserved": None,
            "inference_peak_allocated": None,
            "inference_peak_reserved": None,
            "oom": None,
        },
    )
    write_json(
        run_dir / "next_run_contract.json",
        {
            "status": "BLOCKED",
            "blocker": "isolated CUDA PyTorch wheel was not established within the V1.3A install timebox",
            "cuda_venv_path": str(VENV),
            "python_executable": str(VENV / "Scripts/python.exe"),
            "environment_variables": {
                "PIP_CACHE_DIR": "D:\\AI_Cache\\pip",
                "HF_HOME": "D:\\AI_Cache\\huggingface",
                "HUGGINGFACE_HUB_CACHE": "D:\\AI_Cache\\huggingface\\hub",
                "TRANSFORMERS_CACHE": "D:\\AI_Cache\\huggingface\\transformers",
                "TORCH_HOME": "D:\\AI_Cache\\torch",
                "TEMP": "D:\\AI_Cache\\temp",
                "TMP": "D:\\AI_Cache\\temp",
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
            },
            "runner_path": None,
            "model_path": str(MODEL_PATH.resolve()),
            "model_revision": MODEL_REVISION,
            "reference_path": str((V1 / f"results/c_v1_2_onnx_runtime_equivalence/{V12_RUN_ID}").resolve()),
            "frozen_input_path": preflight["frozen_input_path"],
            "exact_full_command_template": None,
            "full_command_not_created_or_executed": True,
            "strict_fp32_settings": {
                "dtype": "torch.float32",
                "allow_tf32_matmul": False,
                "allow_tf32_cudnn": False,
                "float32_matmul_precision": "highest",
                "autocast": False,
                "candidate_depth": 18,
            },
        },
    )

    validation = {
        "status": "FAIL",
        "run_id": run_id,
        "cuda_hardware_visible_to_nvidia_smi": True,
        "cuda_environment_gate": "FAIL",
        "cuda_environment_blocker": (
            "Official torch 2.11.0+cu128 wheel download reached only 12,339,200 of approximately "
            "2,753,100,000 bytes in 600 seconds and was stopped by the hard install rule; isolated "
            "venv therefore has no torch package and torch.cuda.is_available() cannot pass."
        ),
        "local_model_gate": "PASS",
        "strict_fp32_configuration": "FAIL_NOT_EXECUTED",
        "smoke_candidate_inputs": "FAIL_NOT_EXECUTED",
        "smoke_equivalence": "FAIL_NOT_EXECUTED",
        "smoke_gpu_memory": "FAIL_NOT_EXECUTED",
        "planned_smoke_cases": 3,
        "planned_smoke_pairs": 54,
        "executed_smoke_cases": 0,
        "executed_smoke_pairs": 0,
        "full_72_query_run_executed": False,
        "deepseek_calls": 0,
        "retrieval_reruns": 0,
        "generation_reruns": 0,
        "model_downloads": 0,
        "production_code_changed": False,
        "production_dependencies_changed": False,
        "production_frozen_hash_match": production_match,
        "ready_for_v1_3b_full_equivalence": False,
        "final_rag_architecture": "NOT_YET_FROZEN",
    }
    write_json(run_dir / "machine_validation.json", validation)

    report = f"""# LearnPilot RAG C V1.3A — CUDA Environment Gate + Smoke Equivalence

Run ID: `{run_id}`  
Artifact directory: `{run_dir}`

The repository/artifact and local-model gates passed. `nvidia-smi` identified an NVIDIA GeForce RTX 4060 Laptop GPU with driver 572.83, driver CUDA 12.8, 8188 MiB total VRAM, 7957 MiB free, and no compute process.

The isolated environment was created at `{VENV}`. The official `torch 2.11.0+cu128` wheel is approximately 2753.1 MB; after exactly 10 minutes the temporary wheel contained only 12,339,200 bytes and pip had not completed. The process was terminated under the explicit V1.3A install stop rule. No retry, CUDA Toolkit, alternate precision, model change, or non-isolated fallback was attempted.

The authoritative local model remains `{MODEL_PATH.resolve()}`, revision `{MODEL_REVISION}`, with its frozen model/tokenizer hashes verified. No model download occurred.

Because the isolated venv has no CUDA-enabled torch, `torch.cuda.is_available()` could not pass and strict FP32 model placement was not attempted. The deterministic three-case selection, 54-pair scoring, input comparison, ordering/Top6/context/evidence comparison, smoke timing, and model/inference VRAM measurements were not executed. This is a hard environment blocker, not semantic evidence.

All 15 frozen production file hashes match before and after. No production source or dependency file was changed. No full 72-query run, retrieval, generation, DeepSeek call, or Phase rerun occurred.

```text
RAG_C_V1_3A_CUDA_ENV_AND_SMOKE = FAIL

CUDA_ENVIRONMENT_GATE = FAIL
LOCAL_MODEL_GATE = PASS
STRICT_FP32_CONFIGURATION = FAIL
SMOKE_CANDIDATE_INPUTS = FAIL
SMOKE_EQUIVALENCE = FAIL
SMOKE_GPU_MEMORY = FAIL

SMOKE_CASES = 0
SMOKE_PAIRS = 0
PLANNED_SMOKE_CASES = 3
PLANNED_SMOKE_PAIRS = 54
FULL_72_QUERY_RUN_EXECUTED = false
DEEPSEEK_CALLS = 0
RETRIEVAL_RERUNS = 0
GENERATION_RERUNS = 0
PRODUCTION_CODE_CHANGED = false
PRODUCTION_DEPENDENCIES_CHANGED = false
PRODUCTION_FROZEN_HASH_MATCH = {str(production_match).lower()}

READY_FOR_V1_3B_FULL_EQUIVALENCE = NO
FINAL_RAG_ARCHITECTURE = NOT_YET_FROZEN
```
"""
    REPORT.write_text(report, encoding="utf-8")

    artifact_names = (
        "environment_packages.txt",
        "machine_validation.json",
        "next_run_contract.json",
        "preflight.json",
        "production_hashes_after.json",
        "production_hashes_before.json",
        "smoke_candidate_integrity.json",
        "smoke_case_selection.json",
        "smoke_equivalence_results.json",
        "smoke_gpu_memory_results.json",
        "smoke_latency_results.json",
    )
    artifacts = []
    for name in artifact_names:
        path = run_dir / name
        artifacts.append(
            {
                "run_id": run_id,
                "created_at": now(),
                "git_head": preflight["repository"]["git_head"],
                "artifact_path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256(path),
                "size_bytes": path.stat().st_size,
                "authoritative_reference_run": V12_RUN_ID,
                "model_revision": MODEL_REVISION,
                "model_local_path": str(MODEL_PATH.resolve()),
            }
        )
    for path in (
        ROOT / "RAG_C_V1_3A_CUDA_ENV_AND_SMOKE.md",
        ROOT / "evals/rag_real_world_corpus/v1/c_v1_3a_cuda_env_and_smoke/build_preflight.py",
        ROOT / "evals/rag_real_world_corpus/v1/c_v1_3a_cuda_env_and_smoke/finalize_blocked.py",
    ):
        artifacts.append(
            {
                "run_id": run_id,
                "created_at": now(),
                "git_head": preflight["repository"]["git_head"],
                "artifact_path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256(path),
                "size_bytes": path.stat().st_size,
                "authoritative_reference_run": V12_RUN_ID,
                "model_revision": MODEL_REVISION,
                "model_local_path": str(MODEL_PATH.resolve()),
            }
        )
    manifest = {
        "run_id": run_id,
        "created_at": now(),
        "status": "FAIL",
        "git_head": preflight["repository"]["git_head"],
        "authoritative_reference_run": V12_RUN_ID,
        "model_revision": MODEL_REVISION,
        "model_local_path": str(MODEL_PATH.resolve()),
        "artifacts": artifacts,
    }
    write_json(run_dir / "artifact_manifest.json", manifest)
    manifest_sha = sha256(run_dir / "artifact_manifest.json")
    write_json(
        RESULTS_ROOT / "latest_run.json",
        {
            "run_id": run_id,
            "created_at": now(),
            "status": "FAIL",
            "run_directory": run_dir.relative_to(ROOT).as_posix(),
            "report": REPORT.name,
            "blocker": validation["cuda_environment_blocker"],
            "artifact_manifest_sha256": manifest_sha,
            "ready_for_v1_3b_full_equivalence": False,
        },
    )
    print(json.dumps({"status": "FAIL", "run_id": run_id, "manifest_sha256": manifest_sha}, indent=2))


if __name__ == "__main__":
    main()
