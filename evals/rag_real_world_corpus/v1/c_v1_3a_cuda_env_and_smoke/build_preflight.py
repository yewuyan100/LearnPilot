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
V12_RUN_ID = "20260814T145246Z-298674d5"
V12 = V1 / f"results/c_v1_2_onnx_runtime_equivalence/{V12_RUN_ID}"
PHASE2_RUN_ID = "20260814T095542Z-1317c6a7"
PHASE3_RUN_ID = "20260814T123142Z-8852712b"
PHASE2 = V1 / f"results/hybrid_rerank_phase2_v1_1/{PHASE2_RUN_ID}"
MODEL_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
MODEL_PATH = resolve_canonical_reranker_model_path()
DESIGN_SHA = "442bedce1c43b27b3557b0055708342edd278e98bcac0c12a68c1390fe88f655"


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


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = hashlib.sha256((stamp + "-c-v1.3a-cuda-smoke").encode()).hexdigest()[:8]
    return f"{stamp}-{suffix}"


def verify_v12_manifest() -> dict[str, Any]:
    latest = read_json(V12.parent / "latest_run.json")
    if latest["c_v1_2_run_id"] != V12_RUN_ID or latest["status"] != "PASS":
        raise SystemExit("authoritative C V1.2 latest-run binding failed")
    path = V12 / "artifact_manifest.json"
    observed = sha256(path)
    if observed != latest["artifact_manifest_sha256"]:
        raise SystemExit("authoritative C V1.2 artifact manifest hash drift")
    manifest = read_json(path)
    entries = manifest["result_files"] + manifest["implementation_and_report_files"]
    errors = []
    for entry in entries:
        target = ROOT / entry["path"]
        if not target.is_file():
            errors.append({"path": entry["path"], "reason": "missing"})
        elif target.stat().st_size != entry["size_bytes"]:
            errors.append({"path": entry["path"], "reason": "size"})
        elif sha256(target) != entry["sha256"]:
            errors.append({"path": entry["path"], "reason": "sha256"})
    if errors:
        raise SystemExit(f"authoritative C V1.2 manifest entry drift: {errors[:3]}")
    return {
        "run_id": V12_RUN_ID,
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": observed,
        "verified_entries": len(entries),
        "errors": [],
    }


def main() -> None:
    if not MODEL_PATH.is_dir():
        raise SystemExit("LOCAL_MODEL_GATE = FAIL: authoritative local snapshot missing")
    run_id = new_run_id()
    run_dir = RESULTS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    v12_manifest = verify_v12_manifest()
    v12_validation = read_json(V12 / "machine_validation.json")
    if not (
        v12_validation["status"] == "PASS"
        and v12_validation["input_query_count"] == 72
        and v12_validation["input_pair_count"] == 1296
        and v12_validation["reranker_order_exact_count"] == 72
        and v12_validation["governed_top6_exact_count"] == 72
        and v12_validation["context_digest_exact_count"] == 72
        and v12_validation["required_evidence_presence_exact_count"] == 72
    ):
        raise SystemExit("FROZEN_REFERENCE_GATE = FAIL: C V1.2 validation contract")

    traces = [
        json.loads(line)
        for line in (PHASE2 / "arm_C/candidate_traces.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    if len(traces) != 72 or sum(len(row["candidates"]) for row in traces) != 1296:
        raise SystemExit("FROZEN_REFERENCE_GATE = FAIL: trace coverage")
    if any(len(row["candidates"]) != 18 for row in traces):
        raise SystemExit("FROZEN_REFERENCE_GATE = FAIL: candidate depth")

    v12_preflight = read_json(V12 / "integrity_preflight.json")
    production_rows = []
    for before in v12_preflight["production_hashes_before"]:
        target = ROOT / before["path"]
        observed = sha256(target)
        production_rows.append(
            {
                "path": before["path"],
                "frozen_reference_sha256": before["expected_sha256"],
                "v1_3a_before_sha256": observed,
                "match": observed == before["expected_sha256"],
            }
        )
    if not all(row["match"] for row in production_rows):
        raise SystemExit("production frozen hash baseline failed")

    expected_model_hash = "d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286"
    model_hash = sha256(MODEL_PATH / "model.safetensors")
    if model_hash != expected_model_hash:
        raise SystemExit("LOCAL_MODEL_GATE = FAIL: model weight hash")
    model_files = []
    for name in (
        "config.json",
        "tokenizer_config.json",
        "tokenizer.json",
        "sentencepiece.bpe.model",
        "special_tokens_map.json",
        "model.safetensors",
    ):
        target = MODEL_PATH / name
        if not target.is_file():
            raise SystemExit(f"LOCAL_MODEL_GATE = FAIL: missing {name}")
        model_files.append({"name": name, "sha256": sha256(target), "size_bytes": target.stat().st_size})

    repo = {
        "git_head": git("rev-parse", "HEAD").strip(),
        "git_status_short": git("status", "--short").splitlines(),
        "git_diff_stat": git("diff", "--stat").splitlines(),
        "git_diff_name_only": git("diff", "--name-only").splitlines(),
    }
    base = {
        "run_id": run_id,
        "created_at": now(),
        "scope": "RAG_C_V1_3A_CUDA_ENV_AND_SMOKE",
        "design_sha256": DESIGN_SHA,
        "authoritative_reference_run": V12_RUN_ID,
        "phase2_run_id": PHASE2_RUN_ID,
        "phase3_run_id": PHASE3_RUN_ID,
        "model_id": "BAAI/bge-reranker-v2-m3",
        "model_revision": MODEL_REVISION,
        "model_local_path": str(MODEL_PATH.resolve()),
    }
    write_json(
        run_dir / "production_hashes_before.json",
        {**base, "file_count": len(production_rows), "all_match": True, "rows": production_rows},
    )
    write_json(
        run_dir / "preflight.json",
        {
            **base,
            "status": "PASS",
            "repository": repo,
            "authoritative_v1_2_manifest": v12_manifest,
            "authoritative_v1_2_validation": v12_validation,
            "frozen_input_path": str((PHASE2 / "arm_C/candidate_traces.jsonl").resolve()),
            "frozen_context_path": str((V1 / f"results/hybrid_rerank_phase3_v1_1/{PHASE3_RUN_ID}/context_freeze.json").resolve()),
            "reference_pair_path": str((V12 / "per_pair_score_comparison.json").resolve()),
            "reference_query_path": str((V12 / "per_query_ranking_comparison.json").resolve()),
            "reference_governance_path": str((V12 / "governance_context_comparison.json").resolve()),
            "frozen_query_count": 72,
            "frozen_pair_count": 1296,
            "candidate_depth": 18,
            "model_files": model_files,
            "model_weight_sha256": model_hash,
            "local_model_gate": "PASS",
            "production_hash_gate": "PASS",
        },
    )
    write_json(
        RESULTS_ROOT / "latest_run.json",
        {
            **base,
            "status": "PREFLIGHT_PASS_CUDA_ENV_PENDING",
            "run_directory": run_dir.relative_to(ROOT).as_posix(),
        },
    )
    print(json.dumps({"status": "PASS", "run_id": run_id, "run_dir": str(run_dir)}, indent=2))


if __name__ == "__main__":
    main()
