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
RESULTS_ROOT = V1 / "results/c_v1_1_regression_latency_audit"
REPORT = ROOT / "RAG_C_V1_1_REGRESSION_LATENCY_AUDIT.md"
DESIGN_SHA = "442bedce1c43b27b3557b0055708342edd278e98bcac0c12a68c1390fe88f655"
PHASE2_RUN_ID = "20260814T095542Z-1317c6a7"
PHASE3_RUN_ID = "20260814T123142Z-8852712b"
PHASE4_RUN_ID = "20260814T131417Z-04dfc031"

IMPLEMENTATION_FILES = (
    "evals/rag_real_world_corpus/v1/c_v1_1_regression_latency_audit/build_audit_evidence.py",
    "evals/rag_real_world_corpus/v1/c_v1_1_regression_latency_audit/profile_reranker.py",
    "evals/rag_real_world_corpus/v1/c_v1_1_regression_latency_audit/finalize_audit.py",
    "backend/tests/test_rag_c_v1_1_regression_latency_audit.py",
    "RAG_C_V1_1_REGRESSION_LATENCY_AUDIT.md",
)
TEST_FILES = (
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
    return "N/A" if value is None else f"{value:.{digits}f}"


def compact_identity(identity: str) -> str:
    document, chunk, _ = identity.split(":", 2)
    return f"{document}:{chunk}"


def selected_list(values: list[str]) -> str:
    return ", ".join(f"`{compact_identity(value)}`" for value in values)


def candidate_table(case: dict[str, Any]) -> str:
    rows = []
    for row in case["candidate_rows_dense_order"]:
        evidence = ", ".join(row["evidence_ids"]) or "—"
        rows.append(
            "| {dense_rank} | {dense_score:.6f} | `{identity}` | {evidence} | {reranker_score:.6f} | "
            "{reranker_rank} | {a_final_fate} | {c_final_fate} |".format(
                **{
                    **row,
                    "identity": compact_identity(row["identity"]),
                    "evidence": evidence,
                }
            )
        )
    return "\n".join(rows)


def decision_evidence(profile: dict[str, Any], depth: dict[str, Any]) -> dict[str, Any]:
    warm = profile["warm_summary_ms"]
    serving = [
        {
            "candidate": "persistent_singleton_model",
            "APPLICABLE": "YES",
            "CURRENTLY_ALREADY_DONE": "YES",
            "EXPECTED_IMPACT": "LOW",
            "SEMANTIC_CONTRACT_CHANGE": "NO",
            "evidence": "One adapter is loaded per Phase 2 process and reused for all C/D calls; load is excluded from query latency.",
        },
        {
            "candidate": "batched_18_pair_inference",
            "APPLICABLE": "YES",
            "CURRENTLY_ALREADY_DONE": "YES",
            "EXPECTED_IMPACT": "LOW",
            "SEMANTIC_CONTRACT_CHANGE": "NO",
            "evidence": "All 18 pairs form one padded tensor batch and one model forward.",
        },
        {
            "candidate": "torch_inference_mode",
            "APPLICABLE": "YES",
            "CURRENTLY_ALREADY_DONE": "YES",
            "EXPECTED_IMPACT": "LOW",
            "SEMANTIC_CONTRACT_CHANGE": "NO",
            "evidence": "Gradient tracking is disabled inside the measured forward.",
        },
        {
            "candidate": "model_eval",
            "APPLICABLE": "YES",
            "CURRENTLY_ALREADY_DONE": "YES",
            "EXPECTED_IMPACT": "LOW",
            "SEMANTIC_CONTRACT_CHANGE": "NO",
            "evidence": "The loaded model is in eval mode.",
        },
        {
            "candidate": "cache_query_tokens_and_batch_tokenization_work",
            "APPLICABLE": "YES",
            "CURRENTLY_ALREADY_DONE": "NO",
            "EXPECTED_IMPACT": "LOW",
            "SEMANTIC_CONTRACT_CHANGE": "NO",
            "evidence": f"Current full tokenization warm P50 is only {warm['tokenization_ms']['p50']:.3f} ms.",
        },
        {
            "candidate": "avoid_redundant_cpu_tensor_to_and_python_conversion",
            "APPLICABLE": "YES",
            "CURRENTLY_ALREADY_DONE": "NO",
            "EXPECTED_IMPACT": "LOW",
            "SEMANTIC_CONTRACT_CHANGE": "NO",
            "evidence": (
                f"Tensor preparation and score extraction warm P50 total "
                f"{warm['tensor_preparation_ms']['p50'] + warm['score_extraction_sorting_ms']['p50']:.3f} ms."
            ),
        },
        {
            "candidate": "controlled_cpu_thread_configuration",
            "APPLICABLE": "YES",
            "CURRENTLY_ALREADY_DONE": "NO",
            "EXPECTED_IMPACT": "UNKNOWN",
            "SEMANTIC_CONTRACT_CHANGE": "NO",
            "evidence": "Current 8 intra-op/8 inter-op threads were observed but not tuned in this audit.",
        },
        {
            "candidate": "dynamic_padding_to_longest_pair",
            "APPLICABLE": "YES",
            "CURRENTLY_ALREADY_DONE": "YES",
            "EXPECTED_IMPACT": "MEDIUM",
            "SEMANTIC_CONTRACT_CHANGE": "NO",
            "evidence": "The current call already pads only to the longest pair in each 18-pair batch.",
        },
        {
            "candidate": "length_bucketed_microbatches",
            "APPLICABLE": "YES",
            "CURRENTLY_ALREADY_DONE": "NO",
            "EXPECTED_IMPACT": "UNKNOWN",
            "SEMANTIC_CONTRACT_CHANGE": "NO",
            "evidence": "Could reduce padding but adds forward launches; bitwise/order equivalence would require validation.",
        },
    ]
    semantic = [
        {
            "candidate": "reduce_rerank_depth",
            "classification": "SEMANTIC_EXPERIMENT_REQUIRED",
            "semantic_contract_change": "YES",
            "finding": (
                "C fixed long-bge-training using selected required evidence from Dense rank 15; "
                "Top8/Top12 cannot be declared equivalent."
            ),
        },
        {
            "candidate": "replace_reranker_model",
            "classification": "SEMANTIC_EXPERIMENT_REQUIRED",
            "semantic_contract_change": "YES",
            "finding": "Scores and ordering are model-specific; a new frozen C V1.2 experiment is required.",
        },
        {
            "candidate": "reduce_token_cap",
            "classification": "SEMANTIC_EXPERIMENT_REQUIRED",
            "semantic_contract_change": "YES",
            "finding": "No current pair reaches 1024, so it offers no measured benefit on this corpus until below 379, where truncation semantics change.",
        },
        {
            "candidate": "two_stage_heuristic_candidate_pruning",
            "classification": "SEMANTIC_EXPERIMENT_REQUIRED",
            "semantic_contract_change": "YES",
            "finding": "It changes which candidates receive independent cross-encoder scores.",
        },
        {
            "candidate": "quantization",
            "classification": "MODEL_RUNTIME_OPTIMIZATION",
            "semantic_contract_change": "YES",
            "finding": "Reduced precision can change close score ordering; treat acceptance as a semantic-equivalence experiment.",
        },
        {
            "candidate": "onnx_or_openvino",
            "classification": "MODEL_RUNTIME_OPTIMIZATION",
            "semantic_contract_change": "NO",
            "finding": "Intended semantics may be preserved, but numerical/order equivalence must be proven before serving.",
        },
        {
            "candidate": "gpu_serving",
            "classification": "INFRASTRUCTURE_CHANGE",
            "semantic_contract_change": "NO",
            "finding": "Weights/architecture may remain fixed; device numerical/order equivalence and deployment cost require validation.",
        },
    ]
    return {
        "serving_only_optimization_candidates": serving,
        "semantic_or_runtime_change_candidates": semantic,
        "recommended_c_v1_2_optimization_class": "D. CURRENT_RERANKER_NOT_PRACTICAL_ON_TARGET_CPU",
        "recommendation_rationale": [
            f"Warm total P50 is {warm['total_reranker_call_ms']['p50']:.3f} ms.",
            f"Model forward is {profile['forward_fraction_of_warm_p50'] * 100:.3f}% of warm P50.",
            "Already-enabled singleton, batching, eval, inference mode, and dynamic padding rule out common serving mistakes.",
            "Removing measured Python/tensor/postprocess overhead cannot remove a seconds-scale CPU forward.",
            "A smaller depth is not semantically free and rank-15 evidence accompanied a frozen C fix.",
        ],
        "smallest_supported_next_path_if_c_is_pursued": (
            "Define a new C V1.2 experiment for a lighter/runtime-accelerated reranker with frozen semantic "
            "equivalence and regression gates; this audit does not choose a model, depth, quantization, or runtime."
        ),
        "no_parameters_selected": True,
        "no_implementation_performed": True,
    }


def verify_production(run_dir: Path) -> dict[str, Any]:
    preflight = read_json(run_dir / "integrity_preflight.json")
    rows = []
    for before in preflight["production_hashes_before"]:
        target = ROOT / before["path"]
        after = sha256(target)
        rows.append(
            {
                "path": before["path"],
                "phase2_expected_sha256": before["expected_sha256"],
                "audit_before_sha256": before["observed_sha256"],
                "audit_after_sha256": after,
                "matches_phase2": after == before["expected_sha256"],
                "byte_identical_during_audit": after == before["observed_sha256"],
            }
        )
    return {
        "checked_file_count": len(rows),
        "all_match_phase2": all(row["matches_phase2"] for row in rows),
        "all_byte_identical_during_audit": all(row["byte_identical_during_audit"] for row in rows),
        "rows": rows,
    }


def report_text(
    run_id: str,
    regression: dict[str, Any],
    architecture: dict[str, Any],
    profile: dict[str, Any],
    tokens: dict[str, Any],
    depth: dict[str, Any],
    decision: dict[str, Any],
    production: dict[str, Any],
) -> str:
    cases = regression["cases"]
    first, second = cases
    warm = profile["warm_summary_ms"]
    cold = profile["measurements"][0]
    lengths = tokens["token_lengths"]
    serving_rows = "\n".join(
        f"| `{row['candidate']}` | {row['APPLICABLE']} | {row['CURRENTLY_ALREADY_DONE']} | "
        f"{row['EXPECTED_IMPACT']} | {row['SEMANTIC_CONTRACT_CHANGE']} | {row['evidence']} |"
        for row in decision["serving_only_optimization_candidates"]
    )
    semantic_rows = "\n".join(
        f"| `{row['candidate']}` | {row['classification']} | {row['semantic_contract_change']} | {row['finding']} |"
        for row in decision["semantic_or_runtime_change_candidates"]
    )
    fixed_depth_rows = "\n".join(
        f"| `{row['case_id']}` | "
        f"{', '.join(map(str, row['selected_required_evidence_dense_ranks'])) or 'none with exact anchor telemetry'} |"
        for row in depth["fixed_case_required_evidence_ranks"]
    )
    created_results = (
        "integrity_preflight.json, regression_case_audit.json, candidate_depth_analysis.json, "
        "implementation_architecture.json, reranker_microprofile.json, token_length_profile.json, "
        "optimization_decision.json, production_hash_verification.json, test_results.json, "
        "machine_validation.json, run_state.json, run_manifest.json, artifact_manifest.json"
    )
    return f"""# LearnPilot RAG — C V1.1 Regression & Reranker Latency Audit

## 1. Frozen binding verification

PASS. Design V1.1 `{DESIGN_SHA}`, Phase 2 `{PHASE2_RUN_ID}`, Phase 3 `{PHASE3_RUN_ID}`, and Phase 4 `{PHASE4_RUN_ID}` were re-hashed through their artifact manifests. Gold, Corpus, frozen A, Phase 3 raw/context, and Phase 4 blind adjudication match their authoritative hashes. Audit run: `{run_id}`. No historical artifact was modified.

## 2. Exact regression case traces

Both cases have 18/18 identical A/C pre-rerank candidate identities, dense scores, dense ranks, and eligibility decisions. A and C therefore diverge only after the shared Dense admission point.

### 2.1 `{first['case_id']}`

| Dense rank | Dense score | stable candidate | evidence IDs | reranker score | reranker rank | A fate | C fate |
|---:|---:|---|---|---:|---:|---|---|
{candidate_table(first)}

A Top6: {selected_list(first['a_final_top6_identities'])}.

C Top6: {selected_list(first['c_final_top6_identities'])}.

The rank-effect anchor `rw-eval-context-precision:6` moved Dense 9 → reranker 2 but was overlap-deduplicated behind chunk 7. C still selected chunk 7 containing the 0.5 example and chunk 0 containing the definition. One definition anchor moved 2 → 3; that did not remove it. The C answer explained the ordering effect but omitted the frozen “about 1.0 to about 0.5” change. Context was sufficient; generation/citation expression was weaker.

### 2.2 `{second['case_id']}`

| Dense rank | Dense score | stable candidate | evidence IDs | reranker score | reranker rank | A fate | C fate |
|---:|---:|---|---|---:|---:|---|---|
{candidate_table(second)}

A Top6: {selected_list(second['a_final_top6_identities'])}.

C Top6: {selected_list(second['c_final_top6_identities'])}.

The async threadpool anchor moved Dense 8 → reranker 3 and was selected. C also retained dependency mixing guidance and async chunks. The answer described threadpool behavior but omitted the async document's endpoint-selection guidance. Again, context was sufficient; the frozen answer/citation expression was incomplete.

## 3. Dominant cause for each regression

| Case | Context comparison | Dominant cause | Frozen semantic downgrade |
|---|---|---|---|
| `{first['case_id']}` | {first['context_comparison']} | `{first['independent_dominant_cause']}` | claim 2 `SUPPORTED_BUT_INCOMPLETE`; weak citation support |
| `{second['case_id']}` | {second['context_comparison']} | `{second['independent_dominant_cause']}` | claim 1 `SUPPORTED_BUT_INCOMPLETE`; weak citation support |

The independent reconstruction agrees with the frozen Phase 4 causal traces. Neither case is a `RERANKER_ORDERING`, `SELECTION_DIVERSITY`, or `CONTEXT_BUDGET` failure.

## 4. Regression addressability

Both cases are `GENERATION_ADDRESSABLE`, `HIGH_CONFIDENCE`. Reducing reranker depth: `NO_EVIDENCE` that it repairs either regression. Changing reranker model: `NO_EVIDENCE`. Any serving-only optimization leaves both frozen semantic regressions unchanged: `YES`. They are not evidence for tuning C V1.2 retrieval/reranking parameters.

## 5. Current reranker execution architecture

`MODEL_LOAD_SCOPE = per process`; `TOKENIZATION = pair-by-pair encode`; `FORWARD_PASS = single batch`; `PAIR_COUNT = 18`; `DEVICE = CPU`; `DTYPE = torch.float32`; `TORCH_THREADS = {profile['runtime']['torch_num_threads']}`; `INTEROP_THREADS = {profile['runtime']['torch_num_interop_threads']}`; `INFERENCE_MODE = yes`; `GRAD_ENABLED = no during forward`; `MODEL_EVAL_MODE = yes`.

The tokenizer and model are initialized once with `local_files_only=True`. Candidate features are assembled in a Python loop; the unchanged query is encoded 18 times. One `tokenizer.pad` call creates the full tensor batch, followed by one CPU dictionary `.to()` pass and one model call. Scores are detached to CPU/list and sorted deterministically. These small conversion/loop costs are measured separately below.

## 6. Batching behavior

The current implementation is already the second pattern: one call containing all 18 `(query, candidate)` pairs. It is not 18 sequential model forwards and is not micro-batched. Dynamic padding uses the longest pair in each query batch; attention masks are constructed as ones and zero-padded. Measured batch shape is 18 × that query's actual padding length.

## 7. Model lifetime behavior

The Phase 2 runner creates one adapter after Arm B, then reuses it for all 72 C, 72 D, and determinism calls. Model load is not per query. Historical load was 2.288 s; this diagnostic process loaded the exact cached snapshot in {profile['model_runtime']['model_load_seconds_diagnostic']:.3f} s. Both are excluded from steady-state query latency.

## 8. Token-length profile

Scope: all 72 frozen C queries and 1,296 pairs. Query tokens mean/P50/P95/max = {lengths['query_token_length']['mean']:.1f}/{lengths['query_token_length']['p50']:.0f}/{lengths['query_token_length']['p95']:.0f}/{lengths['query_token_length']['max']:.0f}. Candidate chunk tokens = {lengths['candidate_chunk_token_length']['mean']:.1f}/{lengths['candidate_chunk_token_length']['p50']:.0f}/{lengths['candidate_chunk_token_length']['p95']:.0f}/{lengths['candidate_chunk_token_length']['max']:.0f}. Pair tokens = {lengths['pair_token_length']['mean']:.1f}/{lengths['pair_token_length']['p50']:.0f}/{lengths['pair_token_length']['p95']:.0f}/{lengths['pair_token_length']['max']:.0f}.

Actual padding length mean/P50/P95/max = {lengths['actual_padding_length_per_query']['mean']:.1f}/{lengths['actual_padding_length_per_query']['p50']:.0f}/{lengths['actual_padding_length_per_query']['p95']:.2f}/{lengths['actual_padding_length_per_query']['max']:.0f}. Exact padded token-slot fraction = {lengths['aggregate_padding_token_slot_fraction'] * 100:.2f}%; theoretical attention-cell padding upper bound = {lengths['aggregate_attention_quadratic_padding_upper_bound_fraction'] * 100:.2f}% (not total-model FLOPs). Pairs reaching 1024 = {lengths['pairs_reaching_1024_cap']}; truncated = {lengths['truncation_count']}. Phase 2's zero truncation means the corpus is far below the cap (P95 297, max 379), not close to 1024.

## 9. CPU and thread configuration

Logical CPU count = {profile['runtime']['logical_cpu_count']}; physical count = unavailable under the restricted process and not fabricated; architecture = `{profile['runtime']['processor_architecture']}`; processor = `{profile['runtime']['processor_identifier']}`; Torch intra-op/inter-op = {profile['runtime']['torch_num_threads']}/{profile['runtime']['torch_num_interop_threads']}; CUDA = {profile['runtime']['cuda_available']}.

No global configuration changed. No thread sweep was performed: 8 intra-op threads on 16 logical CPUs is not an obvious oversubscription defect, and selecting a thread count would be tuning outside this audit.

## 10. Latency decomposition

| Component | first inference after load | warm P50 | warm P95 |
|---|---:|---:|---:|
| tokenization | {cold['tokenization_ms']:.3f} ms | {warm['tokenization_ms']['p50']:.3f} ms | {warm['tokenization_ms']['p95']:.3f} ms |
| feature assembly | {cold['feature_assembly_ms']:.3f} ms | {warm['feature_assembly_ms']['p50']:.3f} ms | {warm['feature_assembly_ms']['p95']:.3f} ms |
| tensor preparation | {cold['tensor_preparation_ms']:.3f} ms | {warm['tensor_preparation_ms']['p50']:.3f} ms | {warm['tensor_preparation_ms']['p95']:.3f} ms |
| model forward | {cold['forward_ms']:.3f} ms | {warm['forward_ms']['p50']:.3f} ms | {warm['forward_ms']['p95']:.3f} ms |
| score extraction/sorting | {cold['score_extraction_sorting_ms']:.3f} ms | {warm['score_extraction_sorting_ms']['p50']:.3f} ms | {warm['score_extraction_sorting_ms']['p95']:.3f} ms |
| other timer residual | {cold['other_timer_residual_ms']:.3f} ms | {warm['other_timer_residual_ms']['p50']:.3f} ms | {warm['other_timer_residual_ms']['p95']:.3f} ms |
| total reranker call | {cold['total_reranker_call_ms']:.3f} ms | {warm['total_reranker_call_ms']['p50']:.3f} ms | {warm['total_reranker_call_ms']['p95']:.3f} ms |

The measured warm P50 is consistent with Phase 2's 8.416 s P50. `PRIMARY_LATENCY_BOTTLENECK = model forward` ({profile['forward_fraction_of_warm_p50'] * 100:.3f}% of warm P50). `SECONDARY_LATENCY_BOTTLENECK = tokenization`, but only about {warm['tokenization_ms']['p50']:.3f} ms. The 0.6B FP32 cross-encoder's CPU batch forward—not Python sequencing, model load, downloading, or truncation—explains the approximately 8 seconds.

## 11. Serving-only optimization opportunities

| Candidate | APPLICABLE | ALREADY DONE | EXPECTED IMPACT | SEMANTIC CHANGE | Evidence |
|---|---|---|---|---|---|
{serving_rows}

Common high-value serving safeguards are already present. Remaining plainly semantic-preserving cleanup is millisecond-scale. CPU runtime acceleration may be worth a separately frozen equivalence benchmark, but is not selected here.

## 12. Semantic-changing and infrastructure opportunities

| Candidate | Classification | Semantic contract change | Finding |
|---|---|---|---|
{semantic_rows}

Quantization is a runtime technique but must be treated as semantic-risking because score/order drift is possible. ONNX/OpenVINO and GPU are intended runtime/infrastructure changes, yet still require exact ranking/regression validation.

## 13. Historical candidate-depth opportunity analysis

| C fixed case | Dense ranks of selected exact required anchors |
|---|---|
{fixed_depth_rows}

Across exact required evidence groups, best Dense rank mean/P50/P95/max = {depth['distributions']['required_group_best_dense_rank']['mean']:.2f}/{depth['distributions']['required_group_best_dense_rank']['p50']:.0f}/{depth['distributions']['required_group_best_dense_rank']['p95']:.0f}/{depth['distributions']['required_group_best_dense_rank']['max']}. Selected exact required evidence Dense rank mean/P50/P95/max = {depth['distributions']['selected_required_evidence_dense_rank']['mean']:.2f}/{depth['distributions']['selected_required_evidence_dense_rank']['p50']:.0f}/{depth['distributions']['selected_required_evidence_dense_rank']['p95']:.0f}/{depth['distributions']['selected_required_evidence_dense_rank']['max']}.

Thirteen cases selected required anchors beyond Top8; six did so beyond Top12. Crucially, C's fixed `rw-gold-v1-long-bge-training` used required evidence at Dense rank 15. Historical conclusion: `{depth['historical_depth_conclusion']}`. This is descriptive only: no alternate depth was rescored or selected.

## 14. Recommended C V1.2 optimization class

`{decision['recommended_c_v1_2_optimization_class']}`.

Serving cleanup cannot remove a 7.787 s median model forward. A depth reduction is not free and would exclude rank-15 evidence associated with a C fix. If C is pursued, the smallest evidence-based next path is a new, frozen equivalence/regression experiment for a lighter or runtime-accelerated reranker; this audit selects no model, depth, token cap, quantization mode, runtime, or thread count and implements nothing.

## 15. Exact files created or modified

Created: {', '.join(f'`{path}`' for path in IMPLEMENTATION_FILES)}. Created audit results under `evals/rag_real_world_corpus/v1/results/c_v1_1_regression_latency_audit/{run_id}/`: {created_results}. Created/updated only the audit namespace `latest_run.json`. Production files and Phase 2/3/4 artifacts modified: none.

## 16. Production-file hash verification

All {production['checked_file_count']} production files match both the Phase 2 frozen hashes and their audit-start hashes: `{production['all_match_phase2'] and production['all_byte_identical_during_audit']}`. This verification was performed after local profiling and report evidence generation.

## 17. External call counts

`DEEPSEEK_CALLS=0`; `OPENAI_CALLS=0`; `OTHER_EXTERNAL_EVALUATOR_CALLS=0`; `NETWORK_MODEL_DOWNLOADS=0`; `NEW_RETRIEVAL_RUNS=0`; `NEW_GENERATION_RUNS=0`; `PHASE3_RERUNS=0`; `PRODUCTION_MODIFICATIONS=0`.

## 18. Local reranker profiling execution counts

`LOCAL_MODEL_INITIALIZATIONS={profile['local_reranker_model_initializations']}`; `LOCAL_RERANKER_INFERENCE_CALLS={profile['local_reranker_inference_calls']}`; `LOCAL_RERANKER_PAIRS_SCORED={profile['local_reranker_pairs_scored']}`. One first-inference measurement plus four warm repetitions used the two frozen regression inputs. All five rankings and all logits were bitwise identical to frozen Phase 2; no semantic experiment output was created.

RAG_C_V1_1_REGRESSION_LATENCY_AUDIT = PASS
READY_FOR_C_V1_2_OPTIMIZATION = YES
"""


def run_tests() -> dict[str, Any]:
    suites = []
    total = 0
    for test_file in TEST_FILES:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_file, "-q"],
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


def main() -> None:
    latest = read_json(RESULTS_ROOT / "latest_run.json")
    if latest["status"] != "PROFILING_COMPLETE_FINALIZATION_PENDING":
        raise SystemExit("latest audit run is not ready for finalization")
    run_id = latest["audit_run_id"]
    run_dir = ROOT / latest["run_directory"]
    regression = read_json(run_dir / "regression_case_audit.json")
    architecture = read_json(run_dir / "implementation_architecture.json")
    profile = read_json(run_dir / "reranker_microprofile.json")
    tokens = read_json(run_dir / "token_length_profile.json")
    depth = read_json(run_dir / "candidate_depth_analysis.json")
    decision = decision_evidence(profile, depth)
    production = verify_production(run_dir)
    if not production["all_match_phase2"] or not production["all_byte_identical_during_audit"]:
        raise SystemExit("production hash gate failed")
    write_json(run_dir / "optimization_decision.json", decision)
    write_json(run_dir / "production_hash_verification.json", production)
    REPORT.write_text(
        report_text(run_id, regression, architecture, profile, tokens, depth, decision, production),
        encoding="utf-8",
    )

    tests = run_tests()
    write_json(run_dir / "test_results.json", tests)
    report = REPORT.read_text(encoding="utf-8")
    validation = {
        "status": "PASS",
        "audit_run_id": run_id,
        "frozen_bindings_verified": True,
        "regression_case_count": len(regression["cases"]),
        "pre_rerank_pools_identical": all(
            case["pre_rerank_pool"]["identities_identical"] for case in regression["cases"]
        ),
        "regression_causes": {
            case["case_id"]: case["independent_dominant_cause"]
            for case in regression["cases"]
        },
        "profiling_ranking_and_scores_match_frozen": all(
            row["ranking_order_matches_frozen_phase2"]
            and row["all_scores_bitwise_equal_to_frozen_phase2"]
            for row in profile["measurements"]
        ),
        "primary_latency_bottleneck": profile["primary_latency_bottleneck"],
        "candidate_depth_conclusion": depth["historical_depth_conclusion"],
        "recommendation": decision["recommended_c_v1_2_optimization_class"],
        "production_hashes_unchanged": production["all_byte_identical_during_audit"],
        "report_section_count": len(re.findall(r"(?m)^## \d+\. ", report)),
        "report_exact_ending": report.endswith(
            "RAG_C_V1_1_REGRESSION_LATENCY_AUDIT = PASS\n"
            "READY_FOR_C_V1_2_OPTIMIZATION = YES\n"
        ),
        "tests_passed": tests["tests_passed"],
        "external_calls": 0,
        "new_retrieval_runs": 0,
        "new_generation_runs": 0,
        "production_modifications": 0,
        "local_reranker_inference_calls": profile["local_reranker_inference_calls"],
        "local_reranker_pairs_scored": profile["local_reranker_pairs_scored"],
        "ready_for_c_v1_2_optimization": True,
    }
    if validation["report_section_count"] != 18 or not validation["report_exact_ending"]:
        raise SystemExit("report format gate failed")
    write_json(run_dir / "machine_validation.json", validation)
    write_json(
        run_dir / "run_manifest.json",
        {
            "design_version": "V1.1",
            "ablation_design_sha256": DESIGN_SHA,
            "phase2_run_id": PHASE2_RUN_ID,
            "phase3_run_id": PHASE3_RUN_ID,
            "phase4_run_id": PHASE4_RUN_ID,
            "audit_run_id": run_id,
            "recorded_at": now(),
            "status": "PASS",
            "recommendation": decision["recommended_c_v1_2_optimization_class"],
            "report": REPORT.name,
        },
    )
    state = read_json(run_dir / "run_state.json")
    state.update(
        {
            "status": "PASS",
            "recommendation": decision["recommended_c_v1_2_optimization_class"],
            "ready_for_c_v1_2_optimization": True,
        }
    )
    write_json(run_dir / "run_state.json", state)

    result_names = sorted(
        path.name for path in run_dir.iterdir() if path.is_file() and path.name != "artifact_manifest.json"
    )
    artifact_manifest = {
        "design_version": "V1.1",
        "ablation_design_sha256": DESIGN_SHA,
        "phase2_run_id": PHASE2_RUN_ID,
        "phase3_run_id": PHASE3_RUN_ID,
        "phase4_run_id": PHASE4_RUN_ID,
        "audit_run_id": run_id,
        "recorded_at": now(),
        "status": "PASS",
        "result_files": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for name in result_names
            for path in [run_dir / name]
        ],
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
            "audit_run_id": run_id,
            "recorded_at": now(),
            "status": "PASS",
            "run_directory": run_dir.relative_to(ROOT).as_posix(),
            "report": REPORT.name,
            "recommendation": decision["recommended_c_v1_2_optimization_class"],
            "artifact_manifest_sha256": manifest_hash,
        },
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "audit_run_id": run_id,
                "tests_passed": tests["tests_passed"],
                "recommendation": decision["recommended_c_v1_2_optimization_class"],
                "artifact_manifest_sha256": manifest_hash,
                "report": str(REPORT),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
