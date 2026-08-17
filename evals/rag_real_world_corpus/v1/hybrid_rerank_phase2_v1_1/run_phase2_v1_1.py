from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
from hashlib import sha256
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from time import perf_counter
from typing import Any, Iterable, Sequence
from uuid import uuid4

from experiment import (
    ABLATION_DESIGN_SHA256,
    BM25_B,
    BM25_EPSILON,
    BM25_K1,
    DESIGN_VERSION,
    DENSE_THRESHOLD,
    FUSED_LIMIT,
    FrozenBM25Index,
    FrozenCorpus,
    FrozenDenseTraceAdapter,
    HuggingFaceRerankerAdapter,
    RERANKER_MODEL_ID,
    RERANKER_REVISION,
    RERANKER_TOKEN_CAP,
    REJECTION_REASONS,
    RRF_CONSTANT,
    ArmExecution,
    Candidate,
    ContractViolation,
    build_candidate_pool,
    candidate_order,
    execute_arm,
    govern_evidence,
    group_coverage,
    stable_candidate_identity,
)


HERE = Path(__file__).resolve().parent
V1 = HERE.parent
ROOT = V1.parents[2]
RESULTS_ROOT = V1 / "results/hybrid_rerank_phase2_v1_1"
BASELINE_PATH = (
    V1
    / "results/dense_only_baseline_v1/20260814T052007Z-593cd2ac/raw_results.json"
)
REPORT_PATH = ROOT / "RAG_HYBRID_RERANK_PHASE2_V1_1.md"
V1_DESIGN_SHA256 = "4c3b2e294b63dcc0ae57be1d30d713b3cf1ffed5b0f3a989499f1298902703c6"
RERANKER_WEIGHT_SIZE = 2_271_071_852
RERANKER_WEIGHT_SHA256 = (
    "d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286"
)

FROZEN_HASHES = {
    "v1_1_design": (
        V1 / "ablation_design_v1_1/ablation_design_manifest.json",
        ABLATION_DESIGN_SHA256,
    ),
    "v1_design": (
        V1 / "ablation_design_v1/ablation_design_manifest.json",
        V1_DESIGN_SHA256,
    ),
    "gold": (
        V1 / "gold/v1/gold_cases.json",
        "33a0b69901fa47e3fe45be0277228cd4a5519fe780fe5b9d2c52b1bfe614927a",
    ),
    "gold_freeze": (
        V1 / "gold/v1/gold_dataset_v1_freeze_manifest.json",
        "d979079be4eb901a825ab29414dd7b5124d030182e09b55eea1e93749c12a5c2",
    ),
    "corpus": (
        V1 / "corpus_manifest.json",
        "6f67d510cd35197f107400d33033972c0c3c84478174e4991e491f6c8e4ab563",
    ),
    "frozen_a": (
        BASELINE_PATH,
        "bf718aed08e226149c9310cbf20bf25c403708217e2908789120178ac5574e28",
    ),
    "failure_analysis": (
        V1 / "failure_analysis_v1/failure_analysis_manifest.json",
        "e869fd73e2570413595c1af194b6ec6876e8b822fbd4eac279541a03cac27fb8",
    ),
}

PHASE1_TEST_FILES = (
    "backend/tests/test_rag_hybrid_rerank_phase2_v1_1.py",
    "backend/tests/test_rag_ablation_design_v1_1.py",
    "backend/tests/test_rag_ablation_design_v1.py",
    "backend/tests/test_rag_real_world_failure_analysis_v1.py",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def metadata(run_id: str, arm: str) -> dict[str, Any]:
    return {
        "design_version": DESIGN_VERSION,
        "ablation_design_sha256": ABLATION_DESIGN_SHA256,
        "arm": arm,
        "run_id": run_id,
    }


def result_payload(run_id: str, arm: str, **payload: Any) -> dict[str, Any]:
    return {**metadata(run_id, arm), "recorded_at": utc_now(), **payload}


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def production_hashes() -> dict[str, str]:
    failure = read_json(V1 / "failure_analysis_v1/failure_analysis_manifest.json")
    binding = failure["frozen_bindings"]["production_code"]
    if not binding["all_match"] or len(binding["baseline_sha256"]) != 15:
        raise ContractViolation("frozen production binding is not the expected 15-file set")
    observed = {
        relative: file_hash(ROOT / relative)
        for relative in binding["baseline_sha256"]
    }
    mismatches = {
        relative: {"expected": binding["baseline_sha256"][relative], "observed": digest}
        for relative, digest in observed.items()
        if digest != binding["baseline_sha256"][relative]
    }
    if mismatches:
        raise ContractViolation(f"frozen production binding drift: {mismatches}")
    return observed


def integrity_preflight() -> dict[str, Any]:
    rows = {}
    for name, (path, expected) in FROZEN_HASHES.items():
        observed = file_hash(path)
        rows[name] = {
            "path": path.relative_to(ROOT).as_posix(),
            "expected_sha256": expected,
            "observed_sha256": observed,
            "match": observed == expected,
        }
    if not all(row["match"] for row in rows.values()):
        raise ContractViolation(f"frozen artifact hash mismatch: {rows}")
    baseline = read_json(BASELINE_PATH)
    if baseline["run_id"] != "20260814T052007Z-593cd2ac" or len(baseline["cases"]) != 72:
        raise ContractViolation("frozen Arm A identity or case count mismatch")
    production = production_hashes()
    return {
        "status": "PASS",
        "frozen_artifacts": rows,
        "frozen_a_run_id": baseline["run_id"],
        "frozen_a_case_count": len(baseline["cases"]),
        "production_file_count": len(production),
        "production_hashes": production,
    }


def run_phase1_tests() -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", *PHASE1_TEST_FILES, "-q"]
    started = perf_counter()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    elapsed = perf_counter() - started
    result = {
        "command": command,
        "exit_code": completed.returncode,
        "elapsed_seconds": round(elapsed, 6),
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "observed_test_progress_count": completed.stdout.count("."),
    }
    if completed.returncode != 0:
        raise ContractViolation(f"Phase 1 tests failed: {result}")
    return result


def package_versions() -> dict[str, str | None]:
    packages = (
        "pytest",
        "numpy",
        "pypdf",
        "sentence-transformers",
        "transformers",
        "torch",
        "huggingface-hub",
    )
    versions: dict[str, str | None] = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def process_memory() -> dict[str, Any]:
    if os.name != "nt":
        return {
            "reliable": False,
            "method": "unavailable_non_windows_without_psutil",
            "working_set_mb": None,
            "peak_working_set_mb": None,
            "private_usage_mb": None,
        }

    size_t = ctypes.c_size_t

    class ProcessMemoryCountersEx(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("page_fault_count", ctypes.c_ulong),
            ("peak_working_set_size", size_t),
            ("working_set_size", size_t),
            ("quota_peak_paged_pool_usage", size_t),
            ("quota_paged_pool_usage", size_t),
            ("quota_peak_non_paged_pool_usage", size_t),
            ("quota_non_paged_pool_usage", size_t),
            ("pagefile_usage", size_t),
            ("peak_pagefile_usage", size_t),
            ("private_usage", size_t),
        ]

    counters = ProcessMemoryCountersEx()
    counters.cb = ctypes.sizeof(counters)
    process = ctypes.windll.kernel32.GetCurrentProcess()
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(
        process, ctypes.byref(counters), counters.cb
    )
    if not ok:
        return {
            "reliable": False,
            "method": "GetProcessMemoryInfo_failed",
            "working_set_mb": None,
            "peak_working_set_mb": None,
            "private_usage_mb": None,
        }
    to_mb = lambda value: round(value / (1024 * 1024), 3)
    return {
        "reliable": True,
        "method": "Windows GetProcessMemoryInfo PROCESS_MEMORY_COUNTERS_EX",
        "working_set_mb": to_mb(counters.working_set_size),
        "peak_working_set_mb": to_mb(counters.peak_working_set_size),
        "private_usage_mb": to_mb(counters.private_usage),
    }


def resolve_model(
    cache_dir: Path,
    *,
    local_files_only: bool,
    snapshot_path: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    started = perf_counter()
    if snapshot_path is None:
        from huggingface_hub import snapshot_download

        cache_dir.mkdir(parents=True, exist_ok=True)
        snapshot = Path(
            snapshot_download(
                repo_id=RERANKER_MODEL_ID,
                revision=RERANKER_REVISION,
                cache_dir=str(cache_dir),
                local_files_only=local_files_only,
            )
        ).resolve()
        resolution_source = "huggingface_hub.snapshot_download"
    else:
        snapshot = snapshot_path.resolve()
        if not snapshot.is_dir():
            raise ContractViolation(f"explicit model snapshot does not exist: {snapshot}")
        resolution_source = "explicit_local_snapshot"
    elapsed = perf_counter() - started
    if snapshot.name != RERANKER_REVISION:
        raise ContractViolation(
            f"resolved model revision mismatch: {snapshot.name} != {RERANKER_REVISION}"
        )
    identity_files = []
    for pattern in ("config.json", "tokenizer_config.json", "*.safetensors"):
        for path in sorted(snapshot.glob(pattern)):
            identity_files.append(
                {
                    "name": path.name,
                    "size_bytes": path.stat().st_size,
                    "sha256": file_hash(path),
                }
            )
    if not any(row["name"].endswith(".safetensors") for row in identity_files):
        raise ContractViolation("resolved reranker snapshot has no safetensors weights")
    weights = next(
        (row for row in identity_files if row["name"] == "model.safetensors"), None
    )
    if weights is None:
        raise ContractViolation("resolved reranker snapshot has no model.safetensors")
    if weights["size_bytes"] != RERANKER_WEIGHT_SIZE:
        raise ContractViolation(
            "reranker weight size mismatch: "
            f"{weights['size_bytes']} != {RERANKER_WEIGHT_SIZE}"
        )
    if weights["sha256"] != RERANKER_WEIGHT_SHA256:
        raise ContractViolation(
            "reranker weight SHA-256 mismatch: "
            f"{weights['sha256']} != {RERANKER_WEIGHT_SHA256}"
        )
    return snapshot, {
        "model_id": RERANKER_MODEL_ID,
        "requested_revision": RERANKER_REVISION,
        "resolved_revision": snapshot.name,
        "snapshot_path": str(snapshot),
        "local_files_only": local_files_only,
        "resolution_source": resolution_source,
        "snapshot_resolution_seconds": round(elapsed, 6),
        "identity_files": identity_files,
        "automatic_fallback_used": False,
    }


def percentile(values: Sequence[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize(values: Sequence[float]) -> dict[str, float]:
    return {
        "mean": round(statistics.fmean(values), 6) if values else 0.0,
        "p50": round(percentile(values, 0.50), 6),
        "p95": round(percentile(values, 0.95), 6),
        "max": round(max(values), 6) if values else 0.0,
    }


def candidate_signature(execution: ArmExecution) -> dict[str, Any]:
    bm25 = sorted(
        (candidate for candidate in execution.pool if candidate.bm25_rank is not None),
        key=lambda item: int(item.bm25_rank),
    )
    fusion = sorted(
        (candidate for candidate in execution.pool if candidate.fusion_rank is not None),
        key=lambda item: int(item.fusion_rank),
    )
    reranked = sorted(
        (candidate for candidate in execution.pool if candidate.reranker_rank is not None),
        key=lambda item: int(item.reranker_rank),
    )
    return {
        "bm25_order": candidate_order(bm25),
        "rrf_order": candidate_order(fusion),
        "reranker_order": candidate_order(reranked),
        "governance_input_order": candidate_order(execution.ordered_for_governance),
        "selected_order": candidate_order(execution.selected),
    }


def execution_trace(
    *, run_id: str, case_id: str, sequence: int, execution: ArmExecution
) -> dict[str, Any]:
    return result_payload(
        run_id,
        execution.arm,
        case_id=case_id,
        case_run_id=f"{run_id}-{execution.arm}-{sequence:03d}",
        effective_query=execution.query,
        pipeline={
            "B": "frozen_dense_top18+dense_admission | bm25_top18+membership -> admitted_union -> rrf_k60 -> fused_top18 -> governance",
            "C": "frozen_dense_top18 -> dense_admission -> frozen_reranker -> governance",
            "D": "frozen_dense_top18+dense_admission | bm25_top18+membership -> admitted_union -> rrf_k60 -> fused_top18 -> frozen_reranker -> governance",
        }[execution.arm],
        counts={
            "dense_raw": sum(item.dense_rank is not None for item in execution.pool),
            "bm25_raw": sum(item.bm25_rank is not None for item in execution.pool),
            "observed_identity_union": len(execution.pool),
            "admitted_identity_union": sum(item.candidate_admitted for item in execution.pool),
            "fused": sum(
                item.fusion_rank is not None and item.fusion_rank <= FUSED_LIMIT
                for item in execution.pool
            ),
            "reranker_pairs": execution.pair_count,
            "selected": len(execution.selected),
        },
        stage_latency_ms=execution.stage_latency_ms,
        ordered_for_governance=candidate_order(execution.ordered_for_governance),
        selected=candidate_order(execution.selected),
        candidates=[item.to_dict() for item in execution.pool],
    )


def validate_execution(case_id: str, execution: ArmExecution) -> list[str]:
    errors: list[str] = []
    dense_count = sum(item.dense_rank is not None for item in execution.pool)
    bm25_count = sum(item.bm25_rank is not None for item in execution.pool)
    if dense_count > 18:
        errors.append("dense_raw_cap")
    if bm25_count > 18:
        errors.append("bm25_raw_cap")
    if len(execution.pool) > 36:
        errors.append("identity_union_cap")
    if len(execution.ordered_for_governance) > 18:
        errors.append("governance_input_cap")
    if execution.pair_count > 18:
        errors.append("reranker_pair_cap")
    if any(not item.candidate_admitted for item in execution.ordered_for_governance):
        errors.append("post_admission_leak")
    for candidate in execution.pool:
        expected_identity = stable_candidate_identity(
            candidate.document_id, candidate.chunk_index, candidate.content_hash
        )
        if candidate.identity != expected_identity:
            errors.append("stable_identity")
        if sha256(candidate.raw_text.encode("utf-8")).hexdigest() != candidate.content_hash:
            errors.append("raw_text_hash")
        if (candidate.dense_rank is None) != (candidate.dense_score is None):
            errors.append("dense_observation_null")
        if (candidate.bm25_rank is None) != (candidate.bm25_score is None):
            errors.append("bm25_observation_null")
        expected_dense = (
            candidate.dense_rank is not None
            and candidate.dense_score is not None
            and candidate.dense_score >= DENSE_THRESHOLD
        )
        expected_bm25 = candidate.bm25_rank is not None and 1 <= candidate.bm25_rank <= 18
        if candidate.branch_admitted_dense != expected_dense:
            errors.append("dense_admission")
        if candidate.branch_admitted_bm25 != expected_bm25:
            errors.append("bm25_admission")
        if candidate.candidate_admitted != (expected_dense or expected_bm25):
            errors.append("or_admission")
        if candidate.dense_fusion_rank != (
            candidate.dense_rank if expected_dense else None
        ):
            errors.append("dense_fusion_rank")
        if candidate.bm25_fusion_rank != (
            candidate.bm25_rank if expected_bm25 else None
        ):
            errors.append("bm25_fusion_rank")
        if candidate.dense_rank is not None and candidate.dense_rank > 18:
            errors.append("dense_rank19_refill")
        if candidate.bm25_rank is not None and candidate.bm25_rank > 18:
            errors.append("bm25_rank_cap")
        if candidate.rejection_reason not in (*REJECTION_REASONS, None):
            errors.append("rejection_reason")
        if candidate.selected and candidate.rejection_reason is not None:
            errors.append("selected_with_rejection")
        if not candidate.selected and candidate.rejection_reason is None:
            errors.append("missing_final_fate")
    if errors:
        return [f"{case_id}:{execution.arm}:{error}" for error in sorted(set(errors))]
    return []


def governance_parity(dense_adapter: FrozenDenseTraceAdapter) -> dict[str, Any]:
    mismatches = []
    for case_id in dense_adapter.cases:
        _, dense = dense_adapter.retrieve(case_id, arm="C")
        pool = build_candidate_pool(arm="C", dense_candidates=dense)
        ordered = sorted(
            (item for item in pool if item.candidate_admitted),
            key=lambda item: (int(item.dense_rank), item.identity),
        )
        observed = [
            (item.chunk_id, item.material_id, item.chunk_index)
            for item in govern_evidence(ordered)
        ]
        expected = [
            (item["chunk_id"], item["material_id"], item["chunk_index"])
            for item in dense_adapter.reference_selected(case_id)
        ]
        if observed != expected:
            mismatches.append(
                {"case_id": case_id, "observed": observed, "expected": expected}
            )
    return {
        "method": "reference-only reconstruction from frozen A raw candidates; Arm A retrieval/generation not executed",
        "case_count": len(dense_adapter.cases),
        "matching_case_count": len(dense_adapter.cases) - len(mismatches),
        "mismatches": mismatches,
        "pass": not mismatches,
    }


def coverage_record(
    case: dict[str, Any], candidates: Sequence[Candidate] | Sequence[dict[str, Any]]
) -> dict[str, Any]:
    return group_coverage(case.get("evidence_groups", []), candidates)


def diagnostics(
    *,
    executions: dict[str, dict[str, ArmExecution]],
    dense_adapter: FrozenDenseTraceAdapter,
    target_sets: dict[str, Any],
) -> dict[str, Any]:
    case_rows: dict[str, dict[str, Any]] = {}
    for case_id in dense_adapter.cases:
        gold = dense_adapter.gold_case(case_id)
        row = {
            "A_candidate": coverage_record(
                gold, dense_adapter.reference_candidates(case_id)
            ),
            "A_selected": coverage_record(gold, dense_adapter.reference_selected(case_id)),
        }
        for arm in ("B", "C", "D"):
            execution = executions[arm][case_id]
            row[f"{arm}_candidate"] = coverage_record(
                gold, execution.ordered_for_governance
            )
            row[f"{arm}_selected"] = coverage_record(gold, execution.selected)
        case_rows[case_id] = row

    def target_summary(arm: str, surface: str, case_ids: Sequence[str]) -> dict[str, Any]:
        rows = []
        for case_id in case_ids:
            coverage = case_rows[case_id][f"{arm}_{surface}"]
            rows.append(
                {
                    "case_id": case_id,
                    "document_pass": coverage["document_pass"],
                    "anchor_pass": coverage["anchor_pass"],
                    "required_group_count": coverage["required_group_count"],
                    "document_groups_covered": coverage["document_groups_covered"],
                    "anchor_groups_covered": coverage["anchor_groups_covered"],
                }
            )
        return {
            "arm": arm,
            "surface": surface,
            "case_count": len(rows),
            "document_pass_count": sum(row["document_pass"] for row in rows),
            "anchor_pass_count": sum(row["anchor_pass"] for row in rows),
            "cases": rows,
        }

    comparisons = []
    for arm in ("B", "C", "D"):
        for surface in ("candidate", "selected"):
            for metric in ("document_pass", "anchor_pass"):
                regressions = []
                repairs = []
                for case_id, row in case_rows.items():
                    before = row[f"A_{surface}"][metric]
                    after = row[f"{arm}_{surface}"][metric]
                    if before and not after:
                        regressions.append(case_id)
                    if not before and after:
                        repairs.append(case_id)
                comparisons.append(
                    {
                        "arm": arm,
                        "surface": surface,
                        "metric": metric,
                        "new_regressions": regressions,
                        "repairs": repairs,
                    }
                )
    return {
        "diagnostic_only_no_tuning": True,
        "B_retrieval_miss_targets": target_summary(
            "B", "candidate", target_sets["hybrid"]
        ),
        "C_selection_targets": target_summary(
            "C", "selected", target_sets["dense_rerank"]
        ),
        "D_selection_targets": target_summary(
            "D", "selected", target_sets["dense_rerank"]
        ),
        "C_ranking_miss_split": target_summary(
            "C", "selected", target_sets["reranker_ranking_miss"]
        ),
        "C_diversity_miss_split": target_summary(
            "C", "selected", target_sets["reranker_diversity_miss"]
        ),
        "D_ranking_miss_split": target_summary(
            "D", "selected", target_sets["reranker_ranking_miss"]
        ),
        "D_diversity_miss_split": target_summary(
            "D", "selected", target_sets["reranker_diversity_miss"]
        ),
        "all_case_comparisons": comparisons,
        "case_rows": case_rows,
        "production_winner_selected": False,
        "semantic_answer_review_started": False,
    }


def latency_summary(
    executions: dict[str, dict[str, ArmExecution]], errors: dict[str, list[str]]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for arm in ("B", "C", "D"):
        rows = list(executions[arm].values())
        stages = rows[0].stage_latency_ms
        result[arm] = {
            "case_count": len(rows),
            "error_count": len(errors[arm]),
            "stages_ms": {
                stage: summarize([row.stage_latency_ms[stage] for row in rows])
                for stage in stages
            },
        }
    return result


def pair_statistics(executions: dict[str, dict[str, ArmExecution]]) -> dict[str, Any]:
    result = {}
    for arm in ("C", "D"):
        rows = list(executions[arm].values())
        pairs = [row.pair_count for row in rows]
        truncations = sum(row.truncation_count for row in rows)
        total_pairs = sum(pairs)
        result[arm] = {
            "query_count": len(rows),
            "total_pairs": total_pairs,
            "pair_count": summarize([float(value) for value in pairs]),
            "minimum_pairs": min(pairs),
            "truncation_count": truncations,
            "truncation_rate": round(truncations / total_pairs, 8) if total_pairs else 0.0,
        }
    return result


def determinism_repeat(
    *,
    corpus: FrozenCorpus,
    dense_adapter: FrozenDenseTraceAdapter,
    reranker: HuggingFaceRerankerAdapter,
    executions: dict[str, dict[str, ArmExecution]],
    subset: Sequence[str],
) -> dict[str, Any]:
    fresh_dense = {
        arm: FrozenDenseTraceAdapter(BASELINE_PATH, corpus) for arm in ("B", "C", "D")
    }
    fresh_bm25 = {
        "B": FrozenBM25Index(corpus.chunks),
        "D": FrozenBM25Index(corpus.chunks),
    }
    comparisons = []
    for arm in ("B", "C", "D"):
        for case_id in subset:
            repeated = execute_arm(
                arm=arm,
                case_id=case_id,
                dense_adapter=fresh_dense[arm],
                bm25_index=fresh_bm25.get(arm),
                reranker=reranker if arm in {"C", "D"} else None,
            )
            first = candidate_signature(executions[arm][case_id])
            second = candidate_signature(repeated)
            comparisons.append(
                {
                    "arm": arm,
                    "case_id": case_id,
                    "match": first == second,
                    "first": first,
                    "repeat": second,
                }
            )
    token_digest_first = sha256(
        "\n".join("\0".join(index_tokens) for index_tokens in fresh_bm25["B"].tokenized).encode(
            "utf-8"
        )
    ).hexdigest()
    token_digest_second = sha256(
        "\n".join("\0".join(index_tokens) for index_tokens in fresh_bm25["D"].tokenized).encode(
            "utf-8"
        )
    ).hexdigest()
    return {
        "strategy": "repeat all B/C/D stages for six position-stratified frozen cases with fresh Dense/BM25 adapters; reuse the exact stateless frozen reranker adapter",
        "subset_case_ids": list(subset),
        "repeat_execution_count": len(comparisons),
        "analyzer_token_digest_first": token_digest_first,
        "analyzer_token_digest_second": token_digest_second,
        "analyzer_tokens_match": token_digest_first == token_digest_second,
        "comparisons": comparisons,
        "all_orders_match": all(row["match"] for row in comparisons),
        "parameter_changes_after_repeat": False,
    }


def artifact_manifest(run_id: str, run_dir: Path) -> dict[str, Any]:
    files = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.name == "artifact_manifest.json":
            continue
        files.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": file_hash(path),
                "size_bytes": path.stat().st_size,
            }
        )
    implementation = []
    for path in (
        HERE / "experiment.py",
        HERE / "run_phase2_v1_1.py",
        HERE / "download_model_v1_1.py",
        HERE / "candidate_trace.schema.json",
        ROOT / "backend/tests/test_rag_hybrid_rerank_phase2_v1_1.py",
        REPORT_PATH,
    ):
        implementation.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": file_hash(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return result_payload(
        run_id,
        "B,C,D",
        result_files=files,
        implementation_and_report_files=implementation,
    )


def latency_table(summary_data: dict[str, Any]) -> str:
    lines = [
        "| Arm | Stage | mean ms | P50 ms | P95 ms | max ms | errors |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for arm in ("B", "C", "D"):
        for stage, values in summary_data[arm]["stages_ms"].items():
            lines.append(
                f"| {arm} | {stage} | {values['mean']:.3f} | {values['p50']:.3f} | "
                f"{values['p95']:.3f} | {values['max']:.3f} | {summary_data[arm]['error_count']} |"
            )
    return "\n".join(lines)


def render_report(
    *,
    run_id: str,
    run_dir: Path,
    phase1: dict[str, Any],
    environment: dict[str, Any],
    model_identity: dict[str, Any],
    latency: dict[str, Any],
    reranker_operations: dict[str, Any],
    memory: dict[str, Any],
    pairs: dict[str, Any],
    diagnostic: dict[str, Any],
    isolation: dict[str, Any],
    determinism: dict[str, Any],
    validation: dict[str, Any],
) -> str:
    b_target = diagnostic["B_retrieval_miss_targets"]
    c_target = diagnostic["C_selection_targets"]
    d_target = diagnostic["D_selection_targets"]
    regressions = [
        row
        for row in diagnostic["all_case_comparisons"]
        if row["new_regressions"]
    ]
    weights = next(
        row for row in model_identity["identity_files"] if row["name"].endswith(".safetensors")
    )
    return f"""# LearnPilot RAG Hybrid + Reranker Phase 2 V1.1

Run `{run_id}` is bound to design `{DESIGN_VERSION}` / `{ABLATION_DESIGN_SHA256}`. Phase 3 was not started.

## 1. Phase 1 implementation status

PASS. The experiment-only deep module exposes one `execute_arm` interface over isolated Dense/BM25 and reranker Adapters; Arm A execution is rejected.

## 2. Exact files created or modified

Created `experiment.py`, `run_phase2_v1_1.py`, `download_model_v1_1.py`, `candidate_trace.schema.json`, `backend/tests/test_rag_hybrid_rerank_phase2_v1_1.py`, this report, and versioned results under `{run_dir.relative_to(ROOT).as_posix()}`. Frozen design, Gold, Corpus, target-set and production files were not edited.

## 3. Frozen production files

All 15 bound production hashes matched before and after Phase 2. `PRODUCTION_SEAM_WITHOUT_BOUND_FILE_CHANGE=YES` remains true.

## 4. Dependencies and environment changes

No dependency contract or requirements file changed. Runtime: Python {environment['python']}; packages `{json.dumps(environment['packages'], ensure_ascii=False)}`. The pinned model snapshot was cached under the experiment-selected D-drive cache.

## 5. BM25 implementation identity

Experiment-local dependency-free BM25Okapi, `k1={BM25_K1}`, `b={BM25_B}`, `epsilon={BM25_EPSILON}`, exact frozen bilingual analyzer, 442 runtime chunks. No production dependency was added.

## 6. Reranker resolved model and revision

`{model_identity['model_id']}` resolved exactly to `{model_identity['resolved_revision']}`; fallback=false. Weight `{weights['name']}` is {weights['size_bytes']} bytes, SHA-256 `{weights['sha256']}`.

## 7. Exact B/C/D pipelines executed

- B: frozen production Dense Top18 trace → Dense admission; BM25 Top18 → membership admission → admitted union → RRF k=60 → fused Top18 → frozen governance.
- C: frozen production Dense Top18 trace → Dense admission → pinned reranker → frozen governance.
- D: the B candidate path through fused Top18 → pinned reranker → frozen governance.

Dense is intentionally an immutable frozen-trace Adapter, so its measured stage is trace lookup/identity verification, not a new embedding/FAISS benchmark and not an Arm A rerun.

## 8. Candidate-budget invariants

PASS: Dense raw ≤18, BM25 raw ≤18, observed/admitted union ≤36, fused ≤18, C/D pairs ≤18, and no Dense rank19+ refill across all 216 executions.

## 9. Branch admission and provenance

PASS: Dense contributions require `score>=0.35`; BM25 contributions require Top18 membership; admission is OR; observed-but-non-admitting raw values remain present while their fusion rank is null. No post-admission fused-capacity leak was found.

## 10. Governance equivalence

Frozen A reference-only reconstruction matched historical selected identity/order for {validation['governance_parity']['matching_case_count']}/{validation['governance_parity']['case_count']} cases. No production governance code changed.

## 11. Isolation results

{isolation['status']}. Each arm used a distinct Dense Adapter and output directory; B/D used distinct BM25 index instances. SQLite, FAISS, uploads, conversations and checkpoints were not instantiated in this offline frozen-trace run.

## 12. Determinism results

{determinism['repeat_execution_count']} repeat executions over `{', '.join(determinism['subset_case_ids'])}` produced identical analyzer token digest, BM25 order, RRF order, reranker order and governed identity/order: `{determinism['all_orders_match']}`. No parameter changed.

## 13. Test results

Phase 1 plus historical suites exit={phase1['exit_code']}, observed progress count={phase1['observed_test_progress_count']}, elapsed={phase1['elapsed_seconds']:.3f}s.

## 14. Latency table

{latency_table(latency)}

Dense rows measure frozen trace lookup. One-time snapshot resolution/download and model load are excluded from per-query P50/P95.

## 15. Model load, cold start and steady-state reranker

Snapshot resolution/download: {model_identity['snapshot_resolution_seconds']:.3f}s; model load: {reranker_operations['model_load_seconds']:.3f}s; first inference: {reranker_operations['first_inference_ms']:.3f}ms; steady-state mean/P50/P95/max: {reranker_operations['steady_state_ms']}.

## 16. Memory observations

Reliable OS process measurements: `{memory['reliable']}` via `{memory['method']}`. Baseline `{memory['before_model']['working_set_mb']}` MB, after load `{memory['after_model_load']['working_set_mb']}` MB, final `{memory['after_phase2']['working_set_mb']}` MB, observed peak `{memory['after_phase2']['peak_working_set_mb']}` MB.

## 17. Pair and truncation statistics

C: `{json.dumps(pairs['C'], ensure_ascii=False)}`. D: `{json.dumps(pairs['D'], ensure_ascii=False)}`. Query text was preserved; only chunk tails could be truncated.

## 18. Retrieval-only target diagnostics

Diagnostic only; no tuning or winner selection. B candidate coverage on 9 retrieval-miss targets: document {b_target['document_pass_count']}/9, anchor {b_target['anchor_pass_count']}/9. C selected coverage on 10 targets: document {c_target['document_pass_count']}/10, anchor {c_target['anchor_pass_count']}/10. D: document {d_target['document_pass_count']}/10, anchor {d_target['anchor_pass_count']}/10. The frozen 2 ranking / 8 diversity split is preserved in `diagnostics.json`.

## 19. Regressions and anomalies

New candidate/selection coverage regression groups: `{json.dumps(regressions, ensure_ascii=False)}`. Validation error count: {validation['error_count']}. These are retrieval-only observations; no semantic answer review was performed.

## 20. External generative LLM calls

`0`. No DeepSeek/OpenAI-compatible generation, no Arm A generation, and no Phase 3 request occurred.

## 21. Blockers and deviations

Blockers: none. Recorded deviation/measurement limitation: Dense used exact frozen production Top18 traces, so Phase 2 does not provide new online embedding/FAISS latency. This prevents Arm A rerun and preserves the frozen Dense comparison set; it does not alter candidate identities or scores.

RAG_HYBRID_RERANK_PHASE2_V1_1 = PASS
READY_FOR_ABLATION_GENERATION = YES
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run LearnPilot RAG Phase 2 V1.1")
    parser.add_argument(
        "--model-cache",
        type=Path,
        default=ROOT / ".tmp/rag_phase2_v1_1_model_cache",
    )
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument(
        "--model-snapshot",
        type=Path,
        help="Exact local snapshot directory; basename must equal the frozen revision.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    run_dir = RESULTS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    preflight = integrity_preflight()
    production_before = dict(preflight["production_hashes"])
    write_json(
        run_dir / "preflight.json",
        result_payload(run_id, "B,C,D", **preflight),
    )

    phase1 = run_phase1_tests()
    write_json(
        run_dir / "phase1_tests.json",
        result_payload(run_id, "B,C,D", status="PASS", **phase1),
    )

    environment = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": package_versions(),
        "dependency_files_modified": False,
        "external_generative_llm_clients_initialized": 0,
    }
    write_json(
        run_dir / "environment.json",
        result_payload(run_id, "B,C,D", **environment),
    )

    memory_before = process_memory()
    corpus = FrozenCorpus.from_project(ROOT)
    corpus_identity_digest = sha256(
        "\n".join(item.identity for item in corpus.chunks).encode("utf-8")
    ).hexdigest()

    dense_adapters = {
        arm: FrozenDenseTraceAdapter(BASELINE_PATH, corpus) for arm in ("B", "C", "D")
    }
    bm25_started = perf_counter()
    bm25_indexes = {
        "B": FrozenBM25Index(corpus.chunks),
        "D": FrozenBM25Index(corpus.chunks),
    }
    bm25_build_seconds = perf_counter() - bm25_started
    token_digests = {
        arm: sha256(
            "\n".join("\0".join(tokens) for tokens in index.tokenized).encode("utf-8")
        ).hexdigest()
        for arm, index in bm25_indexes.items()
    }
    if token_digests["B"] != token_digests["D"]:
        raise ContractViolation("isolated BM25 indexes produced different token identities")
    bm25_identity = {
        "implementation_id": FrozenBM25Index.implementation_id,
        "implementation_sha256": file_hash(HERE / "experiment.py"),
        "parameters": {"k1": BM25_K1, "b": BM25_B, "epsilon": BM25_EPSILON},
        "analyzer": "Unicode NFKC + casefold + frozen identifier expansion + CJK bigrams",
        "corpus_chunk_count": len(corpus.chunks),
        "corpus_identity_digest": corpus_identity_digest,
        "analyzer_token_digest": token_digests["B"],
        "isolated_index_count": len(bm25_indexes),
        "total_build_seconds": round(bm25_build_seconds, 6),
        "third_party_bm25_dependency": None,
    }
    write_json(
        run_dir / "bm25_identity.json",
        result_payload(run_id, "B,D", **bm25_identity),
    )

    snapshot, model_identity = resolve_model(
        args.model_cache.resolve(),
        local_files_only=args.local_files_only,
        snapshot_path=args.model_snapshot,
    )
    write_json(
        run_dir / "model_snapshot_identity.json",
        result_payload(run_id, "C,D", **model_identity),
    )

    executions: dict[str, dict[str, ArmExecution]] = {"B": {}, "C": {}, "D": {}}
    errors: dict[str, list[str]] = {"B": [], "C": [], "D": []}
    case_ids = list(dense_adapters["B"].cases)

    # B is executed before model load so its operational measurements exclude model memory.
    for sequence, case_id in enumerate(case_ids, start=1):
        execution = execute_arm(
            arm="B",
            case_id=case_id,
            dense_adapter=dense_adapters["B"],
            bm25_index=bm25_indexes["B"],
            reranker=None,
        )
        executions["B"][case_id] = execution
        errors["B"].extend(validate_execution(case_id, execution))
        append_jsonl(
            run_dir / "arm_B/candidate_traces.jsonl",
            execution_trace(
                run_id=run_id, case_id=case_id, sequence=sequence, execution=execution
            ),
        )

    memory_before_model_load = process_memory()
    reranker = HuggingFaceRerankerAdapter(snapshot)
    memory_after_model_load = process_memory()
    first_inference_ms: float | None = None
    steady_reranker_ms: list[float] = []
    for arm in ("C", "D"):
        for sequence, case_id in enumerate(case_ids, start=1):
            execution = execute_arm(
                arm=arm,
                case_id=case_id,
                dense_adapter=dense_adapters[arm],
                bm25_index=bm25_indexes.get(arm),
                reranker=reranker,
            )
            if first_inference_ms is None:
                first_inference_ms = execution.stage_latency_ms["reranker_inference"]
            else:
                steady_reranker_ms.append(execution.stage_latency_ms["reranker_inference"])
            executions[arm][case_id] = execution
            errors[arm].extend(validate_execution(case_id, execution))
            append_jsonl(
                run_dir / f"arm_{arm}/candidate_traces.jsonl",
                execution_trace(
                    run_id=run_id,
                    case_id=case_id,
                    sequence=sequence,
                    execution=execution,
                ),
            )

    subset = [case_ids[index] for index in (0, 14, 28, 42, 56, 71)]
    determinism = determinism_repeat(
        corpus=corpus,
        dense_adapter=dense_adapters["B"],
        reranker=reranker,
        executions=executions,
        subset=subset,
    )
    write_json(
        run_dir / "determinism.json",
        result_payload(run_id, "B,C,D", **determinism),
    )

    parity = governance_parity(dense_adapters["B"])
    target_sets = read_json(
        V1 / "ablation_design_v1_1/ablation_design_manifest.json"
    )["target_case_sets"]
    diagnostic = diagnostics(
        executions=executions,
        dense_adapter=dense_adapters["B"],
        target_sets=target_sets,
    )
    write_json(
        run_dir / "diagnostics.json",
        result_payload(run_id, "B,C,D", **diagnostic),
    )

    latency = latency_summary(executions, errors)
    write_json(
        run_dir / "latency_summary.json",
        result_payload(run_id, "B,C,D", **latency),
    )
    pairs = pair_statistics(executions)
    write_json(
        run_dir / "reranker_pair_statistics.json",
        result_payload(run_id, "C,D", **pairs),
    )
    memory_after = process_memory()
    memory = {
        "reliable": memory_after["reliable"],
        "method": memory_after["method"],
        "before_corpus_and_model": memory_before,
        "before_model": memory_before_model_load,
        "after_model_load": memory_after_model_load,
        "after_phase2": memory_after,
    }
    write_json(
        run_dir / "memory.json",
        result_payload(run_id, "B,C,D", **memory),
    )
    reranker_operations = {
        "model_load_seconds": round(reranker.load_seconds, 6),
        "first_inference_ms": round(float(first_inference_ms), 6),
        "steady_state_ms": summarize(steady_reranker_ms),
        "main_run_inference_calls": 144,
        "determinism_repeat_inference_calls": 12,
        "adapter_total_inference_calls": reranker.inference_calls,
        "adapter_total_pair_count": reranker.pair_count,
        "download_or_snapshot_resolution_excluded_from_query_latency": True,
        "model_load_excluded_from_query_latency": True,
    }
    write_json(
        run_dir / "reranker_operations.json",
        result_payload(run_id, "C,D", **reranker_operations),
    )

    isolation = {
        "status": "PASS",
        "dense_adapter_instance_ids_distinct": len(
            {id(value) for value in dense_adapters.values()}
        )
        == 3,
        "bm25_index_instance_ids_distinct": id(bm25_indexes["B"])
        != id(bm25_indexes["D"]),
        "arm_output_directories": {
            arm: (run_dir / f"arm_{arm}").relative_to(ROOT).as_posix()
            for arm in ("B", "C", "D")
        },
        "sqlite": "not instantiated; immutable offline trace adapter",
        "faiss": "not instantiated; immutable frozen Dense trace adapter",
        "conversations": "not instantiated",
        "request_ids": "unique case_run_id per arm/case",
        "uploads": "not instantiated",
        "checkpoints": "not instantiated",
        "cross_arm_candidate_object_sharing": False,
    }
    if not all(
        (
            isolation["dense_adapter_instance_ids_distinct"],
            isolation["bm25_index_instance_ids_distinct"],
        )
    ):
        raise ContractViolation(f"arm-state isolation failure: {isolation}")
    write_json(
        run_dir / "isolation.json",
        result_payload(run_id, "B,C,D", **isolation),
    )

    production_after = production_hashes()
    all_errors = [error for arm_errors in errors.values() for error in arm_errors]
    validation = {
        "status": "PASS",
        "execution_counts": {"A": 0, "B": 72, "C": 72, "D": 72},
        "external_generative_llm_calls": 0,
        "design_hash_match": file_hash(
            V1 / "ablation_design_v1_1/ablation_design_manifest.json"
        )
        == ABLATION_DESIGN_SHA256,
        "gold_hash_match": file_hash(V1 / "gold/v1/gold_cases.json")
        == FROZEN_HASHES["gold"][1],
        "corpus_hash_match": file_hash(V1 / "corpus_manifest.json")
        == FROZEN_HASHES["corpus"][1],
        "production_hashes_unchanged_during_run": production_before == production_after,
        "production_file_count": len(production_after),
        "reranker_revision_match": model_identity["resolved_revision"]
        == RERANKER_REVISION,
        "fallback_reranker_used": False,
        "governance_parity": parity,
        "determinism_pass": determinism["all_orders_match"]
        and determinism["analyzer_tokens_match"],
        "isolation_pass": isolation["status"] == "PASS",
        "phase1_tests_pass": phase1["exit_code"] == 0,
        "error_count": len(all_errors),
        "errors": all_errors,
        "phase3_started": False,
    }
    hard_checks = [
        validation["design_hash_match"],
        validation["gold_hash_match"],
        validation["corpus_hash_match"],
        validation["production_hashes_unchanged_during_run"],
        validation["reranker_revision_match"],
        not validation["fallback_reranker_used"],
        validation["governance_parity"]["pass"],
        validation["determinism_pass"],
        validation["isolation_pass"],
        validation["phase1_tests_pass"],
        validation["error_count"] == 0,
        validation["external_generative_llm_calls"] == 0,
        not validation["phase3_started"],
    ]
    if not all(hard_checks):
        validation["status"] = "BLOCKED"
        write_json(
            run_dir / "validation.json",
            result_payload(run_id, "B,C,D", **validation),
        )
        raise ContractViolation(f"Phase 2 hard validation failed: {validation}")
    write_json(
        run_dir / "validation.json",
        result_payload(run_id, "B,C,D", **validation),
    )

    report = render_report(
        run_id=run_id,
        run_dir=run_dir,
        phase1=phase1,
        environment=environment,
        model_identity=model_identity,
        latency=latency,
        reranker_operations=reranker_operations,
        memory=memory,
        pairs=pairs,
        diagnostic=diagnostic,
        isolation=isolation,
        determinism=determinism,
        validation=validation,
    )
    REPORT_PATH.write_text(report, encoding="utf-8")
    manifest = artifact_manifest(run_id, run_dir)
    write_json(run_dir / "artifact_manifest.json", manifest)
    write_json(
        RESULTS_ROOT / "latest_run.json",
        result_payload(
            run_id,
            "B,C,D",
            status="PASS",
            run_directory=run_dir.relative_to(ROOT).as_posix(),
            report=REPORT_PATH.relative_to(ROOT).as_posix(),
            artifact_manifest_sha256=file_hash(run_dir / "artifact_manifest.json"),
        ),
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "run_id": run_id,
                "run_dir": str(run_dir),
                "report": str(REPORT_PATH),
                "execution_counts": validation["execution_counts"],
                "external_generative_llm_calls": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
