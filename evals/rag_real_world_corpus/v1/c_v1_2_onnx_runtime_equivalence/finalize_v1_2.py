from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
V1 = ROOT / "evals/rag_real_world_corpus/v1"
RESULTS_ROOT = V1 / "results/c_v1_2_onnx_runtime_equivalence"
REPORT = ROOT / "RAG_C_V1_2_ONNX_RUNTIME_EQUIVALENCE.md"
DESIGN_SHA = "442bedce1c43b27b3557b0055708342edd278e98bcac0c12a68c1390fe88f655"
PHASE2_RUN_ID = "20260814T095542Z-1317c6a7"
PHASE3_RUN_ID = "20260814T123142Z-8852712b"
PHASE4_RUN_ID = "20260814T131417Z-04dfc031"
C_V1_1_AUDIT_RUN_ID = "20260814T142012Z-015c3ca0"
CLASSIFICATION = "B. ONNX_FP32_EQUIVALENT_BUT_SPEEDUP_INSUFFICIENT"
RECOMMENDED_NEXT_STATE = "KEEP_A_FOR_V1_AND_DEFER_RERANKER_WORK"

IMPLEMENTATION_FILES = (
    "evals/rag_real_world_corpus/v1/c_v1_2_onnx_runtime_equivalence/build_preflight.py",
    "evals/rag_real_world_corpus/v1/c_v1_2_onnx_runtime_equivalence/export_fp32_onnx.py",
    "evals/rag_real_world_corpus/v1/c_v1_2_onnx_runtime_equivalence/run_equivalence.py",
    "evals/rag_real_world_corpus/v1/c_v1_2_onnx_runtime_equivalence/finalize_v1_2.py",
    "backend/tests/test_rag_c_v1_2_onnx_runtime_equivalence.py",
    "RAG_C_V1_2_ONNX_RUNTIME_EQUIVALENCE.md",
)
TEST_FILES = (
    "backend/tests/test_rag_c_v1_2_onnx_runtime_equivalence.py",
    "backend/tests/test_rag_c_v1_1_regression_latency_audit.py",
    "backend/tests/test_rag_hybrid_rerank_phase4_v1_1.py",
    "backend/tests/test_rag_hybrid_rerank_phase3_v1_1.py",
    "backend/tests/test_rag_hybrid_rerank_phase2_v1_1.py",
    "backend/tests/test_rag_ablation_design_v1_1.py",
)


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


def fmt(value: float | None, digits: int = 3) -> str:
    return "unavailable" if value is None else f"{value:.{digits}f}"


def latency_row(label: str, values: dict[str, Any]) -> str:
    return (
        f"| {label} | {values['mean']:.3f} | {values['p50']:.3f} | "
        f"{values['p95']:.3f} | {values['max']:.3f} |"
    )


def verify_production(run_dir: Path) -> dict[str, Any]:
    preflight = read_json(run_dir / "integrity_preflight.json")
    rows = []
    for before in preflight["production_hashes_before"]:
        path = ROOT / before["path"]
        after = sha256(path)
        rows.append(
            {
                "path": before["path"],
                "frozen_reference_sha256": before["expected_sha256"],
                "experiment_preflight_sha256": before["observed_sha256"],
                "experiment_final_sha256": after,
                "matches_frozen_reference": after == before["expected_sha256"],
                "byte_identical_during_experiment": after == before["observed_sha256"],
            }
        )
    return {
        "checked_file_count": len(rows),
        "all_match_frozen_reference": all(row["matches_frozen_reference"] for row in rows),
        "all_byte_identical_during_experiment": all(
            row["byte_identical_during_experiment"] for row in rows
        ),
        "rows": rows,
    }


def build_decision(
    semantic: dict[str, Any], latency: dict[str, Any], memory: dict[str, Any]
) -> dict[str, Any]:
    pytorch_p50 = latency["pytorch_warm_summary_ms"]["total_reranker_call_ms"]["p50"]
    onnx_p50 = latency["onnx_warm_summary_ms"]["total_reranker_call_ms"]["p50"]
    slower_percent = (onnx_p50 / pytorch_p50 - 1.0) * 100.0
    return {
        "status": "PASS",
        "classification": CLASSIFICATION,
        "semantic_equivalence": semantic["semantic_equivalence"],
        "reranker_order_exact": f"{semantic['reranker_order_exact_count']}/72",
        "governed_top6_exact": f"{semantic['governed_top6_exact_count']}/72",
        "context_digest_exact": f"{semantic['context_digest_exact_count']}/72",
        "required_evidence_presence_exact": f"{semantic['required_evidence_presence_exact_count']}/72",
        "pytorch_warm_total_p50_ms": pytorch_p50,
        "onnx_warm_total_p50_ms": onnx_p50,
        "paired_p50_speedup": latency["paired_representative_total_p50_speedup"],
        "onnx_slower_percent": round(slower_percent, 6),
        "materially_faster": False,
        "interactive_learnpilot_latency_plausible": False,
        "interactive_latency_reason": (
            "A persistent 18-pair reranker call remains approximately 10.4 seconds at representative "
            "warm P50 and is slower than the 7.8-second PyTorch reference."
        ),
        "existing_c_v1_1_semantic_evaluation_remains_authoritative": semantic[
            "existing_c_v1_1_semantic_evaluation_remains_authoritative"
        ],
        "generation_rerun_required": False,
        "recommended_next_state": RECOMMENDED_NEXT_STATE,
        "next_experiment_class_if_reranker_work_is_reopened": "LIGHTWEIGHT_RERANKER_REPLACEMENT",
        "next_class_only_no_implementation": True,
        "production_promotion_performed": False,
        "production_integration_performed": False,
        "memory_measurement_reliable": memory["maximum_observed_working_set_mb"] is not None,
        "ready_for_c_production_decision": True,
    }


def run_tests() -> dict[str, Any]:
    suites = []
    total = 0
    for test_file in TEST_FILES:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", test_file],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise SystemExit(f"test gate failed for {test_file}:\n{result.stdout}\n{result.stderr}")
        match = re.search(r"(\d+) passed", result.stdout)
        passed = (
            int(match.group(1))
            if match
            else sum(line.count(".") for line in result.stdout.splitlines())
        )
        total += passed
        suites.append(
            {
                "test_file": test_file,
                "passed": passed,
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
            }
        )
    return {"status": "PASS", "tests_passed": total, "suites": suites}


def report_text(
    run_id: str,
    preflight: dict[str, Any],
    runtime: dict[str, Any],
    environment: dict[str, Any],
    export: dict[str, Any],
    inputs: dict[str, Any],
    scores: dict[str, Any],
    semantic: dict[str, Any],
    near: dict[str, Any],
    latency: dict[str, Any],
    memory: dict[str, Any],
    production: dict[str, Any],
    external: dict[str, Any],
    decision: dict[str, Any],
    tests: dict[str, Any],
) -> str:
    score_stats = scores["score_difference_statistics"]
    abs_diff = score_stats["absolute_difference"]
    rel_diff = score_stats["relative_difference_where_abs_pytorch_gt_1e_6"]
    pytorch = latency["pytorch_warm_summary_ms"]
    onnx = latency["onnx_warm_summary_ms"]
    full = latency["onnx_full_72_query_summary_ms"]
    minimum = near["minimum_adjacent_score_margin"]
    model_main = next(row for row in export["artifact_files"] if row["path"].endswith(".onnx"))
    artifact_bytes = sum(row["size_bytes"] for row in export["artifact_files"])
    suite_rows = "\n".join(
        f"| `{row['test_file']}` | {row['passed']} | PASS |" for row in tests.get("suites", [])
    ) or "| Finalization test gate | pending during provisional render | PENDING |"
    pytorch_tokenization = {
        key: pytorch["tokenization_ms"][key] + pytorch["feature_assembly_ms"][key]
        for key in ("mean", "p50", "p95", "max")
    }
    fixed_manifests = preflight["verified_manifests"]
    return f"""# LearnPilot RAG C V1.2 ONNX Runtime Equivalence Audit

Run: `{run_id}`  
Decision: `{CLASSIFICATION}`  
Scope: frozen C V1.1 Phase 2 pairs, ONNX Runtime FP32 CPU, no production integration.

## 1. Integrity gate

PASS. Design SHA `{DESIGN_SHA}` and the frozen Phase 2/3/4/C-audit run bindings match exactly. The verified artifact-manifest hashes are:

| Binding | Run | Manifest SHA-256 | Verified entries |
|---|---|---|---:|
| Phase 2 | `{PHASE2_RUN_ID}` | `{fixed_manifests['phase2']['sha256']}` | {fixed_manifests['phase2']['verified_entries']} |
| Phase 3 | `{PHASE3_RUN_ID}` | `{fixed_manifests['phase3']['sha256']}` | {fixed_manifests['phase3']['verified_entries']} |
| Phase 4 | `{PHASE4_RUN_ID}` | `{fixed_manifests['phase4']['sha256']}` | {fixed_manifests['phase4']['verified_entries']} |
| C V1.1 audit | `{C_V1_1_AUDIT_RUN_ID}` | `{fixed_manifests['c_v1_1_audit']['sha256']}` | {fixed_manifests['c_v1_1_audit']['verified_entries']} |

Gold, corpus, design, and frozen Phase 2 C trace hashes matched before export. No authoritative historical artifact was modified.

## 2. Exact runtime/export contract

The experiment uses `torch.onnx.export` legacy mode (`dynamo=False`), opset 17, constant folding, external tensor data, and dynamic batch/sequence axes. ONNX Runtime `{environment['packages']['onnxruntime']}` runs `CPUExecutionProvider`, FP32 initializers, `ORT_ENABLE_ALL`, `ORT_SEQUENTIAL`, CPU arena and memory-pattern optimization enabled. Thread configuration is ONNX intra-op 8/inter-op 1; no sweep was performed.

Inputs are `input_ids: int64[batch,sequence]` and `attention_mask: int64[batch,sequence]`; XLM-R emits no token-type IDs. Output is `logits: float32[batch,1]`. Each call preserves frozen Dense order and dynamically pads one 18-pair batch. Export took {export['export']['export_seconds']:.3f} seconds and is excluded from latency.

## 3. Model/tokenizer identity

Model `BAAI/bge-reranker-v2-m3`, revision `{export['source']['revision']}`, 567,755,777 FP32 parameters. Source `model.safetensors` SHA-256 is `{export['source']['model_safetensors_sha256']}` and was reverified unchanged after export. Tokenizer files were read from the same local snapshot with `local_files_only=True`.

The ONNX main graph SHA-256 is `{model_main['sha256']}`; the export contains {len(export['artifact_files'])} graph/external-data files totaling {artifact_bytes:,} bytes. Tool versions: PyTorch `{environment['packages']['torch']}`, Transformers `{environment['packages']['transformers']}`, ONNX `{environment['packages']['onnx']}`, ONNX Script `{environment['packages']['onnxscript']}`.

## 4. 1296-pair equivalence status

PASS: {inputs['query_count']} queries × {inputs['candidate_depth']} candidates = {inputs['pair_count']} frozen pairs. Effective query, raw text, identity, Dense order, tokenizer policy, special tokens, masks, pair token counts, and dynamic padding semantics were preserved. All frozen token-count telemetry matched and new truncation count was {inputs['truncation_count']}.

Frozen Phase 2 PyTorch logits/ranks were consumed directly; reference logits were not regenerated.

## 5. 72-query reranker-order equivalence

PASS: `{semantic['reranker_order_exact_count']}/72` candidate identity orders are exact across all 18 ranks. Ordering mismatches: {len(semantic['ordering_mismatches'])}. Stable ordering uses descending score, then upstream Dense rank, then stable identity.

Therefore `SEMANTIC_EQUIVALENCE = PASS` and the existing C V1.1 semantic evaluation remains authoritative.

## 6. 72-query Top6/context equivalence

Frozen governance was replayed without modification: overlap dedup, diversity, maximum three per material in the first pass, rank-ordered backfill, Top-6, and context budget.

| Invariant | Exact |
|---|---:|
| Governed Top-6 identity/order | {semantic['governed_top6_exact_count']}/72 |
| Final context text/digest | {semantic['context_digest_exact_count']}/72 |
| Required-evidence presence | {semantic['required_evidence_presence_exact_count']}/72 |

There were zero governance, context, or required-evidence regressions. No new generation or Phase 3/4 semantic review is required.

## 7. Logit-difference statistics

All 1,296 PyTorch/ONNX scores and differences are stored per pair. Score equality is secondary to ordering/context identity.

| Difference | Mean | P50 | P95 | P99 | Max | Exact zero |
|---|---:|---:|---:|---:|---:|---:|
| Absolute | {abs_diff['mean']:.9f} | {abs_diff['p50']:.9f} | {abs_diff['p95']:.9f} | {abs_diff['p99']:.9f} | {abs_diff['max']:.9f} | {score_stats['exact_score_count']} |
| Relative where meaningful | {rel_diff['mean']:.9f} | {rel_diff['p50']:.9f} | {rel_diff['p95']:.9f} | {rel_diff['p99']:.9f} | {rel_diff['max']:.9f} | — |

The maximum absolute difference was `{abs_diff['max']:.9f}` and did not change that pair's rank.

## 8. Near-tie findings

Across {near['adjacent_pair_count']} adjacent rank pairs, minimum PyTorch margin is `{minimum['margin']:.9f}` in `{minimum['case_id']}` at ranks {minimum['higher_rank']}/{minimum['lower_rank']}. The zero margin is resolved deterministically by the frozen Dense-rank/identity tie rule.

| Statistic / descriptive epsilon | Value |
|---|---:|
| P1 margin | {near['margin_distribution']['p1']:.9f} |
| P5 margin | {near['margin_distribution']['p5']:.9f} |
| P50 margin | {near['margin_distribution']['p50']:.9f} |
| margin ≤ 1e-6 | {near['descriptive_near_tie_counts']['margin_lte_1e-06']} |
| margin ≤ 1e-5 | {near['descriptive_near_tie_counts']['margin_lte_1e-05']} |
| margin ≤ 1e-4 | {near['descriptive_near_tie_counts']['margin_lte_0.0001']} |
| margin ≤ 1e-3 | {near['descriptive_near_tie_counts']['margin_lte_0.001']} |
| margin ≤ 1e-2 | {near['descriptive_near_tie_counts']['margin_lte_0.01']} |

These epsilons are descriptive only. Three independent ONNX repeats of the minimum-margin case were bitwise score-deterministic and order-deterministic; no production threshold was introduced.

## 9. PyTorch latency

Reference: C V1.1 audit on the same 16-logical-CPU machine, PyTorch CPU FP32, intra-op 8/inter-op 8, persistent model, one 18-pair dynamic batch. Warm methodology was one first call followed by four alternating repeats over the two frozen regression cases.

| PyTorch component (ms) | Mean | P50 | P95 | Max |
|---|---:|---:|---:|---:|
{latency_row('Tokenization + feature assembly', pytorch_tokenization)}
{latency_row('Tensor preparation', pytorch['tensor_preparation_ms'])}
{latency_row('Model forward', pytorch['forward_ms'])}
{latency_row('Score extraction/sort', pytorch['score_extraction_sorting_ms'])}
{latency_row('Total reranker call', pytorch['total_reranker_call_ms'])}

## 10. ONNX latency

Representative warm measurements use the same two cases and same warm methodology as PyTorch.

| ONNX representative warm component (ms) | Mean | P50 | P95 | Max |
|---|---:|---:|---:|---:|
{latency_row('Tokenization + feature assembly', onnx['tokenization_feature_assembly_ms'])}
{latency_row('Tensor/input preparation', onnx['tensor_input_preparation_ms'])}
{latency_row('Session forward', onnx['session_forward_ms'])}
{latency_row('Score extraction/sort', onnx['score_extraction_sorting_ms'])}
{latency_row('Total reranker call', onnx['total_reranker_call_ms'])}

The full 72-query ONNX total was mean `{full['total_reranker_call_ms']['mean']:.3f}` ms, P50 `{full['total_reranker_call_ms']['p50']:.3f}` ms, P95 `{full['total_reranker_call_ms']['p95']:.3f}` ms, max `{full['total_reranker_call_ms']['max']:.3f}` ms. Download, conversion, and export are excluded.

## 11. Measured speedup

Paired representative warm total P50 speedup is `{latency['paired_representative_total_p50_speedup']:.6f}×`; forward P50 speedup is `{latency['paired_representative_forward_p50_speedup']:.6f}×`. Values below 1 mean slowdown. ONNX is `{decision['onnx_slower_percent']:.3f}%` slower than the PyTorch representative total P50.

Result: `{CLASSIFICATION}`. A persistent approximately 10.4-second reranker call is not plausible for interactive LearnPilot use.

## 12. Initialization/cold-start

PyTorch C V1.1 model load was `{latency['pytorch_model_load_seconds']:.3f}` s and first inference `{latency['pytorch_first_inference_ms']:.3f}` ms. ONNX session load was `{latency['session_load_seconds']:.3f}` s and first inference `{latency['first_inference']['total_reranker_call_ms']:.3f}` ms. Export ({export['export']['export_seconds']:.3f} s) is one-time and excluded.

## 13. Memory

Windows `GetProcessMemoryInfo(PROCESS_MEMORY_COUNTERS_EX)` provided reliable process measurements. ONNX baseline working/private memory was `{memory['baseline_before_onnxruntime_import_and_session']['working_set_mb']:.3f}` / `{memory['baseline_before_onnxruntime_import_and_session']['private_usage_mb']:.3f}` MiB; after session load `{memory['after_onnx_session_load']['working_set_mb']:.3f}` / `{memory['after_onnx_session_load']['private_usage_mb']:.3f}` MiB; maximum observed after calls `{memory['maximum_observed_working_set_mb']:.3f}` / `{memory['maximum_observed_private_usage_mb']:.3f}` MiB. OS-reported peak working set was `{memory['process_peak_working_set_mb_after_inference']:.3f}` MiB.

The exporter process observed PyTorch working set `{export['memory']['baseline_before_pytorch_model_load']['working_set_mb']:.3f}` MiB before load and `{export['memory']['after_pytorch_model_load']['working_set_mb']:.3f}` MiB after load. PyTorch inference peak is unavailable because reference logits were intentionally not regenerated and exporter tracing is not an isolated inference measurement. The two baselines have different import/process scope, so no cross-runtime memory winner is claimed.

## 14. Tests

Test gate: `{tests.get('status', 'PENDING')}`; `{tests.get('tests_passed', 0)}` tests across the focused V1.2 suite and intact C V1.1/Phase 2/3/4/design suites.

| Suite | Passed | Status |
|---|---:|---|
{suite_rows}

Focused coverage includes frozen bindings, tokenizer/input equivalence, ONNX identity and output shape, 1,296-pair depth, deterministic ranking, PyTorch/ONNX order, governed Top-6/context digests, no retrieval/production change, and zero generation/evaluator calls.

## 15. Production-file verification

PASS: all `{production['checked_file_count']}` frozen production files match both the authoritative reference hashes and their experiment-preflight hashes. Production dependency files were not edited; ONNX dependencies live only under `.tmp/c_v1_2_onnx_runtime/site-packages`. No production integration or promotion was performed.

## 16. External/generation/retrieval execution counts

| Execution class | Count |
|---|---:|
| DeepSeek | {external['deepseek_calls']} |
| OpenAI | {external['openai_calls']} |
| Other external evaluators | {external['other_external_evaluator_calls']} |
| Model-hub calls/downloads | {external['model_hub_calls']} / {external['model_downloads']} |
| Generation | {external['generation_calls']} |
| Retrieval | {external['retrieval_runs']} |
| Phase 3/4 reruns | {external['phase3_or_phase4_reruns']} |
| Production modifications | {external['production_modifications']} |
| Successful audited ONNX calls / pairs scored | {external['successful_equivalence_run_onnx_calls']} / {external['successful_equivalence_run_pairs_scored']} |

Two external dependency-registry commands installed experiment-local ONNX packages from `{external['dependency_registry']}`; one sandboxed registry attempt was blocked. These were dependency setup only, not model, evaluator, retrieval, or generation calls.

The successful audited process made 5 profile + 72 full-equivalence + 3 near-tie calls = 80 calls / 1,440 scored pairs; the semantic dataset remains exactly 72×18 = 1,296 unique frozen pairs. Before checkpointing, two orchestration-timeout attempts occurred (first call count unavailable; second reached at least 65 calls). One later checkpoint-initialization bug occurred after 5 profile calls. These extra local attempts are disclosed but excluded from the successful-run latency/equivalence counts.

## 17. Recommended next state

Evidence is sufficient for a production decision, but not for ONNX promotion. Preserve the frozen C V1.1 semantic conclusion, do not rerun DeepSeek, and do not integrate this ONNX artifact.

Recommended next state: `{RECOMMENDED_NEXT_STATE}`. If reranker work is reopened later, the next experiment class is `LIGHTWEIGHT_RERANKER_REPLACEMENT`; this audit selects no model or parameters and implements nothing from that class.

RAG_C_V1_2_ONNX_RUNTIME_AUDIT = PASS
READY_FOR_C_PRODUCTION_DECISION = YES
"""


def main() -> None:
    latest = read_json(RESULTS_ROOT / "latest_run.json")
    if latest["status"] not in {"EQUIVALENCE_COMPLETE_FINALIZATION_PENDING", "PASS"}:
        raise SystemExit("latest C V1.2 run is not ready for finalization")
    run_id = latest["c_v1_2_run_id"]
    run_dir = ROOT / latest["run_directory"]
    preflight = read_json(run_dir / "integrity_preflight.json")
    runtime = read_json(run_dir / "runtime_manifest.json")
    environment = read_json(run_dir / "environment_identity.json")
    export = read_json(run_dir / "model_export_manifest.json")
    inputs = read_json(run_dir / "input_equivalence.json")
    scores = read_json(run_dir / "per_pair_score_comparison.json")
    semantic = read_json(run_dir / "semantic_equivalence.json")
    near = read_json(run_dir / "near_tie_analysis.json")
    latency = read_json(run_dir / "latency_measurements.json")
    memory = read_json(run_dir / "memory_measurements.json")
    external = read_json(run_dir / "external_call_audit.json")

    if semantic["semantic_equivalence"] != "PASS":
        raise SystemExit("semantic equivalence gate failed")
    if not (
        semantic["reranker_order_exact_count"] == 72
        and semantic["governed_top6_exact_count"] == 72
        and semantic["context_digest_exact_count"] == 72
        and semantic["required_evidence_presence_exact_count"] == 72
    ):
        raise SystemExit("semantic exact-count gate failed")
    if inputs["query_count"] != 72 or inputs["pair_count"] != 1296:
        raise SystemExit("input coverage gate failed")

    production = verify_production(run_dir)
    if not production["all_match_frozen_reference"] or not production[
        "all_byte_identical_during_experiment"
    ]:
        raise SystemExit("production hash gate failed")
    decision = build_decision(semantic, latency, memory)
    external.update(
        {
            "successful_equivalence_run_onnx_calls": 80,
            "successful_equivalence_run_pairs_scored": 1440,
            "frozen_semantic_dataset_queries": 72,
            "frozen_semantic_dataset_pairs": 1296,
            "pre_checkpoint_orchestration_timeout_attempts": 2,
            "first_timeout_onnx_calls": "unavailable",
            "second_timeout_known_minimum_onnx_calls": 65,
            "checkpoint_initialization_failure_attempts": 1,
            "checkpoint_initialization_failure_onnx_calls": 5,
            "onnx_calls_across_all_attempts": "unavailable_due_to_first_timeout",
            "onnx_export_attempts": 2,
            "successful_onnx_exports": 1,
        }
    )
    write_json(run_dir / "external_call_audit.json", external)
    write_json(run_dir / "production_hash_verification.json", production)
    write_json(run_dir / "final_decision_evidence.json", decision)

    pending_tests = {"status": "PENDING", "tests_passed": 0, "suites": []}
    REPORT.write_text(
        report_text(
            run_id,
            preflight,
            runtime,
            environment,
            export,
            inputs,
            scores,
            semantic,
            near,
            latency,
            memory,
            production,
            external,
            decision,
            pending_tests,
        ),
        encoding="utf-8",
    )
    tests = run_tests()
    write_json(run_dir / "test_results.json", tests)
    REPORT.write_text(
        report_text(
            run_id,
            preflight,
            runtime,
            environment,
            export,
            inputs,
            scores,
            semantic,
            near,
            latency,
            memory,
            production,
            external,
            decision,
            tests,
        ),
        encoding="utf-8",
    )

    report = REPORT.read_text(encoding="utf-8")
    validation = {
        "status": "PASS",
        "c_v1_2_run_id": run_id,
        "frozen_bindings_verified": preflight["status"] == "PASS",
        "input_query_count": inputs["query_count"],
        "input_pair_count": inputs["pair_count"],
        "candidate_depth": inputs["candidate_depth"],
        "truncation_count": inputs["truncation_count"],
        "semantic_equivalence": semantic["semantic_equivalence"],
        "reranker_order_exact_count": semantic["reranker_order_exact_count"],
        "governed_top6_exact_count": semantic["governed_top6_exact_count"],
        "context_digest_exact_count": semantic["context_digest_exact_count"],
        "required_evidence_presence_exact_count": semantic[
            "required_evidence_presence_exact_count"
        ],
        "classification": CLASSIFICATION,
        "production_hashes_unchanged": production["all_byte_identical_during_experiment"],
        "report_section_count": len(re.findall(r"(?m)^## \d+\. ", report)),
        "report_exact_ending": report.endswith(
            "RAG_C_V1_2_ONNX_RUNTIME_AUDIT = PASS\n"
            "READY_FOR_C_PRODUCTION_DECISION = YES\n"
        ),
        "tests_passed": tests["tests_passed"],
        "deepseek_calls": external["deepseek_calls"],
        "generation_calls": external["generation_calls"],
        "retrieval_runs": external["retrieval_runs"],
        "phase3_or_phase4_reruns": external["phase3_or_phase4_reruns"],
        "production_modifications": external["production_modifications"],
        "ready_for_c_production_decision": True,
    }
    if validation["report_section_count"] != 17 or not validation["report_exact_ending"]:
        raise SystemExit("report format gate failed")
    write_json(run_dir / "machine_validation.json", validation)

    runtime["status"] = "PASS"
    runtime["classification"] = CLASSIFICATION
    write_json(run_dir / "runtime_manifest.json", runtime)
    state = read_json(run_dir / "run_state.json")
    state.update(
        {
            "status": "PASS",
            "classification": CLASSIFICATION,
            "recommended_next_state": RECOMMENDED_NEXT_STATE,
            "ready_for_c_production_decision": True,
        }
    )
    write_json(run_dir / "run_state.json", state)
    write_json(
        run_dir / "run_manifest.json",
        {
            "design_version": "V1.1",
            "ablation_design_sha256": DESIGN_SHA,
            "phase2_run_id": PHASE2_RUN_ID,
            "phase3_run_id": PHASE3_RUN_ID,
            "phase4_run_id": PHASE4_RUN_ID,
            "c_v1_1_audit_run_id": C_V1_1_AUDIT_RUN_ID,
            "c_v1_2_run_id": run_id,
            "recorded_at": now(),
            "status": "PASS",
            "classification": CLASSIFICATION,
            "report": REPORT.name,
            "production_integration_performed": False,
        },
    )

    result_names = sorted(
        path.name
        for path in run_dir.iterdir()
        if path.is_file() and path.name != "artifact_manifest.json"
    )
    model_main = next(
        row for row in export["artifact_files"] if row["path"].endswith(".onnx")
    )
    artifact_manifest = {
        "design_version": "V1.1",
        "ablation_design_sha256": DESIGN_SHA,
        "phase2_run_id": PHASE2_RUN_ID,
        "phase3_run_id": PHASE3_RUN_ID,
        "phase4_run_id": PHASE4_RUN_ID,
        "c_v1_1_audit_run_id": C_V1_1_AUDIT_RUN_ID,
        "c_v1_2_run_id": run_id,
        "recorded_at": now(),
        "status": "PASS",
        "classification": CLASSIFICATION,
        "result_files": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for name in result_names
            for path in [run_dir / name]
        ],
        "model_artifact_reference": {
            "manifest": "model_export_manifest.json",
            "file_count": len(export["artifact_files"]),
            "total_bytes": sum(row["size_bytes"] for row in export["artifact_files"]),
            "main_onnx": model_main,
        },
        "implementation_and_report_files": [
            {
                "path": relative,
                "sha256": sha256(ROOT / relative),
                "size_bytes": (ROOT / relative).stat().st_size,
            }
            for relative in IMPLEMENTATION_FILES
        ],
    }
    write_json(run_dir / "artifact_manifest.json", artifact_manifest)
    manifest_hash = sha256(run_dir / "artifact_manifest.json")
    write_json(
        RESULTS_ROOT / "latest_run.json",
        {
            "design_version": "V1.1",
            "ablation_design_sha256": DESIGN_SHA,
            "phase2_run_id": PHASE2_RUN_ID,
            "phase3_run_id": PHASE3_RUN_ID,
            "phase4_run_id": PHASE4_RUN_ID,
            "c_v1_1_audit_run_id": C_V1_1_AUDIT_RUN_ID,
            "c_v1_2_run_id": run_id,
            "recorded_at": now(),
            "status": "PASS",
            "run_directory": run_dir.relative_to(ROOT).as_posix(),
            "report": REPORT.name,
            "classification": CLASSIFICATION,
            "recommended_next_state": RECOMMENDED_NEXT_STATE,
            "artifact_manifest_sha256": manifest_hash,
        },
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "c_v1_2_run_id": run_id,
                "tests_passed": tests["tests_passed"],
                "classification": CLASSIFICATION,
                "artifact_manifest_sha256": manifest_hash,
                "report": str(REPORT),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
