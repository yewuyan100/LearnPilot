from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
V1 = ROOT / "evals/rag_real_world_corpus/v1"
RESULTS_ROOT = V1 / "results/c_v1_3a_cuda_env_recovery"
REPORT = ROOT / "RAG_C_V1_3A_R_CUDA_WHEEL_RECOVERY.md"
PARENT_RUN_ID = "20260815T072031Z-126ba16e"
PARENT = V1 / f"results/c_v1_3a_cuda_env_and_smoke/{PARENT_RUN_ID}"
VENV = ROOT / ".venv-cuda"
PARTIAL_WHEEL = Path(
    "D:/AI_Cache/temp/pip-unpack-87a1fud4/torch-2.11.0+cu128-cp311-cp311-win_amd64.whl"
)
PROBE_FILE = Path("D:/AI_Cache/temp/v1_3a_r_probe_16m.bin")
WHEEL_URL = (
    "https://download-r2.pytorch.org/whl/cu128/"
    "torch-2.11.0%2Bcu128-cp311-cp311-win_amd64.whl"
)
WHEEL_SIZE = 2_753_148_611
PROBE_BYTES = 16_777_216
PROBE_SECONDS = 51.307660
PROBE_SPEED = 326_993


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
    suffix = hashlib.sha256((stamp + "-c-v1.3a-r").encode()).hexdigest()[:8]
    return f"{stamp}-{suffix}"


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def main() -> None:
    parent_validation = read_json(PARENT / "machine_validation.json")
    parent_manifest = PARENT / "artifact_manifest.json"
    parent_latest = read_json(PARENT.parent / "latest_run.json")
    if (
        parent_validation["run_id"] != PARENT_RUN_ID
        or parent_validation["status"] != "FAIL"
        or sha256(parent_manifest) != parent_latest["artifact_manifest_sha256"]
    ):
        raise SystemExit("parent V1.3A failure binding drift")
    if not PROBE_FILE.is_file() or PROBE_FILE.stat().st_size != PROBE_BYTES:
        raise SystemExit("bounded throughput probe artifact missing or wrong size")

    run_id = new_run_id()
    run_dir = RESULTS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    git_head = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    estimate_seconds = WHEEL_SIZE / PROBE_SPEED

    before = read_json(PARENT / "production_hashes_after.json")
    production_rows = []
    for row in before["rows"]:
        observed = sha256(ROOT / row["path"])
        production_rows.append(
            {
                "path": row["path"],
                "frozen_reference_sha256": row["frozen_reference_sha256"],
                "parent_v1_3a_after_sha256": row["v1_3a_after_sha256"],
                "recovery_observed_sha256": observed,
                "matches_frozen_reference": observed == row["frozen_reference_sha256"],
                "unchanged_during_recovery": observed == row["v1_3a_after_sha256"],
            }
        )
    production_match = all(
        row["matches_frozen_reference"] and row["unchanged_during_recovery"]
        for row in production_rows
    )

    wheel_inventory = {
        "run_id": run_id,
        "recorded_at": now(),
        "parent_failed_run": PARENT_RUN_ID,
        "cuda_venv_path": str(VENV),
        "cuda_venv_python": str(VENV / "Scripts/python.exe"),
        "cuda_venv_packages": {"pip": "24.0", "setuptools": "65.5.0"},
        "cuda_venv_torch_spec": None,
        "complete_reusable_cuda_wheels_found": 0,
        "pip_cache_complete_torch_wheels": 0,
        "d_drive_complete_torch_cuda_wheels": 0,
        "partial_download": {
            "path": str(PARTIAL_WHEEL),
            "exists": PARTIAL_WHEEL.exists(),
            "size_bytes": PARTIAL_WHEEL.stat().st_size if PARTIAL_WHEEL.exists() else 0,
            "valid_installable_wheel": False,
        },
        "anaconda_torch_reusable": False,
        "anaconda_import_error": "ModuleNotFoundError: No module named 'torch._strobelight'",
        "correct_build": {
            "package": "torch==2.11.0+cu128",
            "python_tag": "cp311",
            "platform_tag": "win_amd64",
            "index": "https://download.pytorch.org/whl/cu128",
            "reason": (
                "latest official cu128 build exposed by the PyTorch index for CPython 3.11; "
                "driver 572.83 advertises CUDA 12.8 and RTX 4060 compute capability 8.9"
            ),
        },
    }
    write_json(run_dir / "wheel_inventory.json", wheel_inventory)

    throughput = {
        "run_id": run_id,
        "recorded_at": now(),
        "url": WHEEL_URL,
        "head_probe": {
            "http_status": 200,
            "content_length": WHEEL_SIZE,
            "accept_ranges": "bytes",
            "etag": "8145ca21fefbdd3257c20c5e43cb50b5-14",
            "last_modified": "Tue, 31 Mar 2026 08:18:10 GMT",
        },
        "range_probe": {
            "requested_range": "bytes=0-16777215",
            "http_status": 206,
            "size_download_bytes": PROBE_BYTES,
            "time_total_seconds": PROBE_SECONDS,
            "average_speed_bytes_per_second": PROBE_SPEED,
            "probe_path": str(PROBE_FILE),
            "probe_sha256": sha256(PROBE_FILE),
        },
        "linear_full_wheel_estimate": {
            "seconds": round(estimate_seconds, 3),
            "minutes": round(estimate_seconds / 60.0, 3),
            "hours": round(estimate_seconds / 3600.0, 3),
            "excludes_dependency_download_and_install_time": True,
        },
        "download_time_clearly_controllable": False,
        "installation_authorized_by_gate": False,
        "full_wheel_download_started": False,
        "pip_install_started": False,
    }
    write_json(run_dir / "throughput_probe.json", throughput)

    environment_gate = {
        "run_id": run_id,
        "recorded_at": now(),
        "gpu": "NVIDIA GeForce RTX 4060 Laptop GPU",
        "driver_version": "572.83",
        "driver_cuda_version": "12.8",
        "compute_capability": "8.9",
        "total_vram_mib": 8188,
        "free_vram_mib": 7957,
        "hardware_gate": "PASS",
        "correct_cuda_pytorch_build_identified": True,
        "isolated_torch_installed": False,
        "torch_version": None,
        "torch_version_cuda": None,
        "torch_cuda_is_available": None,
        "torch_cuda_device_count": None,
        "torch_cuda_device_name": None,
        "cuda_environment_gate": "FAIL_NOT_RECOVERED",
        "reason": "bounded throughput probe predicts approximately 140.3 minutes for wheel bytes alone",
        "reranker_loaded": False,
        "model_files_opened": 0,
        "benchmark_executed": False,
        "smoke_executed": False,
        "full_72_query_run_executed": False,
    }
    write_json(run_dir / "cuda_environment_gate.json", environment_gate)
    write_json(
        run_dir / "production_hash_verification.json",
        {
            "run_id": run_id,
            "recorded_at": now(),
            "file_count": len(production_rows),
            "production_frozen_hash_match": production_match,
            "rows": production_rows,
        },
    )

    validation = {
        "status": "BLOCKED",
        "run_id": run_id,
        "parent_failed_run": PARENT_RUN_ID,
        "correct_cuda_pytorch_build": "torch==2.11.0+cu128",
        "complete_local_wheel_found": False,
        "throughput_probe_pass": False,
        "estimated_full_wheel_minutes": round(estimate_seconds / 60.0, 3),
        "installation_performed": False,
        "cuda_environment_recovered": False,
        "cuda_environment_gate": "FAIL_NOT_RECOVERED",
        "reranker_loaded": False,
        "benchmark_executed": False,
        "smoke_executed": False,
        "full_72_query_run_executed": False,
        "deepseek_calls": 0,
        "retrieval_reruns": 0,
        "generation_reruns": 0,
        "production_code_changed": False,
        "production_dependencies_changed": False,
        "production_frozen_hash_match": production_match,
        "ready_for_v1_3a_smoke": False,
        "final_rag_architecture": "NOT_YET_FROZEN",
    }
    write_json(run_dir / "machine_validation.json", validation)

    report = f"""# LearnPilot RAG C V1.3A-R — CUDA Wheel Acquisition & Environment Recovery

Run ID: `{run_id}`  
Parent failed run: `{PARENT_RUN_ID}`  
Artifact directory: `{run_dir}`

## Build identification

The correct bounded candidate is the official CPython 3.11 Windows x64 build `torch==2.11.0+cu128` from `https://download.pytorch.org/whl/cu128`. The machine has an RTX 4060 Laptop GPU (compute capability 8.9), driver 572.83, and driver CUDA 12.8.

## Local inventory

No complete reusable CUDA torch wheel was found in the D-drive cache, project cache, pip cache, or isolated venv. `.venv-cuda` still contains only pip 24.0 and setuptools 65.5.0. The parent run's 12,339,200-byte file is incomplete and not installable. The existing Anaconda torch import is broken and is not a reusable isolated source.

## Official download probe

The official CDN returned `Content-Length: {WHEEL_SIZE}` and `Accept-Ranges: bytes`. A bounded 16 MiB request completed with HTTP 206 in `{PROBE_SECONDS:.6f}` seconds at `{PROBE_SPEED:,}` bytes/s. Linear wheel-only estimate: `{estimate_seconds / 60.0:.3f}` minutes (`{estimate_seconds / 3600.0:.3f}` hours), excluding other dependencies and installation.

This is not a clearly controllable acquisition time. The full wheel download and pip installation were not started.

## Environment result

The hardware gate remains PASS, but the isolated CUDA PyTorch environment was not recovered. `torch.cuda.is_available()` remains unavailable because torch is not installed in `.venv-cuda`. No reranker model was loaded and no smoke, benchmark, candidate scoring, or full 72-query execution occurred.

All 15 frozen production file hashes remained identical. No production source or dependency file changed.

```text
RAG_C_V1_3A_R_CUDA_WHEEL_RECOVERY = BLOCKED
CORRECT_CUDA_PYTORCH_BUILD = torch==2.11.0+cu128
COMPLETE_LOCAL_WHEEL_FOUND = false
DOWNLOAD_THROUGHPUT_GATE = FAIL
FULL_WHEEL_DOWNLOAD_STARTED = false
CUDA_PYTORCH_INSTALLED = false
CUDA_ENVIRONMENT_GATE = FAIL_NOT_RECOVERED
RERANKER_LOADED = false
BENCHMARK_EXECUTED = false
SMOKE_EXECUTED = false
FULL_72_QUERY_RUN_EXECUTED = false
PRODUCTION_FROZEN_HASH_MATCH = {str(production_match).lower()}
READY_FOR_V1_3A_SMOKE = NO
FINAL_RAG_ARCHITECTURE = NOT_YET_FROZEN
```
"""
    REPORT.write_text(report, encoding="utf-8")

    artifact_paths = [
        run_dir / "cuda_environment_gate.json",
        run_dir / "machine_validation.json",
        run_dir / "production_hash_verification.json",
        run_dir / "throughput_probe.json",
        run_dir / "wheel_inventory.json",
        REPORT,
        ROOT / "evals/rag_real_world_corpus/v1/c_v1_3a_cuda_env_recovery/finalize_recovery.py",
    ]
    manifest = {
        "run_id": run_id,
        "created_at": now(),
        "status": "BLOCKED",
        "git_head": git_head,
        "parent_failed_run": PARENT_RUN_ID,
        "artifacts": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for path in artifact_paths
        ],
        "external_probe_artifact": {
            "path": str(PROBE_FILE),
            "sha256": sha256(PROBE_FILE),
            "size_bytes": PROBE_FILE.stat().st_size,
        },
    }
    write_json(run_dir / "artifact_manifest.json", manifest)
    manifest_sha = sha256(run_dir / "artifact_manifest.json")
    write_json(
        RESULTS_ROOT / "latest_run.json",
        {
            "run_id": run_id,
            "created_at": now(),
            "status": "BLOCKED",
            "run_directory": run_dir.relative_to(ROOT).as_posix(),
            "report": REPORT.name,
            "artifact_manifest_sha256": manifest_sha,
            "cuda_environment_recovered": False,
            "ready_for_v1_3a_smoke": False,
        },
    )
    print(
        json.dumps(
            {
                "status": "BLOCKED",
                "run_id": run_id,
                "estimated_full_wheel_minutes": round(estimate_seconds / 60.0, 3),
                "manifest_sha256": manifest_sha,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
