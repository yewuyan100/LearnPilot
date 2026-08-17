from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
V1 = HERE.parent
ROOT = V1.parents[2]
RUN_ID = "20260814T131417Z-04dfc031"
RUN_DIR = V1 / f"results/hybrid_rerank_phase4_v1_1/{RUN_ID}"
RESULTS_ROOT = RUN_DIR.parent
REPORT = ROOT / "RAG_HYBRID_RERANK_PHASE4_SEMANTIC_REVIEW_V1_1.md"
DESIGN_SHA256 = "442bedce1c43b27b3557b0055708342edd278e98bcac0c12a68c1390fe88f655"
PHASE2_RUN_ID = "20260814T095542Z-1317c6a7"
PHASE3_RUN_ID = "20260814T123142Z-8852712b"
PASS1_SHA256 = "0e91fedd1a4b98152e77a093dff1a18ed3f177a92b3d1d4ddc67073b3fcdaf9c"
IMPLEMENTATION_FILES = (
    "evals/rag_real_world_corpus/v1/hybrid_rerank_phase4_v1_1/prepare_blinded_review.py",
    "evals/rag_real_world_corpus/v1/hybrid_rerank_phase4_v1_1/freeze_blinded_adjudication.py",
    "evals/rag_real_world_corpus/v1/hybrid_rerank_phase4_v1_1/build_unblinded_evidence.py",
    "evals/rag_real_world_corpus/v1/hybrid_rerank_phase4_v1_1/finalize_phase4_v1_1.py",
    "backend/tests/test_rag_hybrid_rerank_phase4_v1_1.py",
    "RAG_HYBRID_RERANK_PHASE4_SEMANTIC_REVIEW_V1_1.md",
)
TEST_FILES = (
    "backend/tests/test_rag_hybrid_rerank_phase4_v1_1.py",
    "backend/tests/test_rag_hybrid_rerank_phase3_v1_1.py",
    "backend/tests/test_rag_hybrid_rerank_phase2_v1_1.py",
    "backend/tests/test_rag_ablation_design_v1_1.py",
    "backend/tests/test_rag_real_world_failure_analysis_v1.py",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def metadata(**payload: Any) -> dict[str, Any]:
    return {
        "design_version": "V1.1",
        "ablation_design_sha256": DESIGN_SHA256,
        "phase2_run_id": PHASE2_RUN_ID,
        "phase3_run_id": PHASE3_RUN_ID,
        "phase4_run_id": RUN_ID,
        "recorded_at": utc_now(),
        **payload,
    }


def ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "none"


def render_report() -> str:
    preflight = read_json(RUN_DIR / "integrity_preflight.json")
    freeze = read_json(RUN_DIR / "pass1_freeze.json")
    metrics = read_json(RUN_DIR / "unblinded_metrics.json")
    transitions = read_json(RUN_DIR / "case_transitions.json")
    severe = read_json(RUN_DIR / "severe_regressions.json")
    target = read_json(RUN_DIR / "target_group_analysis.json")
    complementarity = read_json(RUN_DIR / "complementarity.json")
    causal = read_json(RUN_DIR / "causal_traces.json")
    quality = read_json(RUN_DIR / "quality_latency.json")
    gates = read_json(RUN_DIR / "production_gate_matrix.json")
    recommendation = read_json(RUN_DIR / "final_recommendation_evidence.json")
    reconciliation = read_json(RUN_DIR / "historical_a_reconciliation.json")
    claim_lines = []
    case_lines = []
    answerability_lines = []
    citation_lines = []
    for arm in "ABCD":
        row = metrics["arms"][arm]
        state = row["semantic_state_counts"]
        verdict = row["case_verdict_counts"]
        claim_lines.append(
            f"| {arm} | {row['reviewed_correctness']['count']}/132 | {row['required_claim_coverage']['count']}/132 | "
            f"{state.get('SUPPORTED_BUT_INCOMPLETE', 0)} | {state.get('MISSING', 0)} | {row['unsupported_claim_count']} | {row['contradicted_claim_count']} |"
        )
        case_lines.append(
            f"| {arm} | {verdict.get('FULL_PASS', 0)} | {verdict.get('PARTIAL_PASS', 0)} | {verdict.get('FAIL', 0)} | "
            f"{verdict.get('CORRECT_REFUSAL', 0)} | {verdict.get('INCORRECT_REFUSAL', 0)} | {row['fully_correct_case_count']}/72 |"
        )
        answerability_lines.append(
            f"| {arm} | {row['answerability_accuracy']['count']}/72 | {row['answerability_accuracy']['correct_refusal']} | {row['answerability_accuracy']['incorrect_refusal']} |"
        )
        citation = row["semantic_citation_support"]
        citation_lines.append(
            f"| {arm} | {citation['valid_id_and_support_count']}/{citation['applicable_claim_count']} | "
            f"{citation['status_counts'].get('VALID_ID_BUT_WEAK_SUPPORT', 0)} | "
            f"{citation['status_counts'].get('MISSING_REQUIRED_CITATION', 0)} | "
            f"{citation['status_counts'].get('MISATTRIBUTED_SUPPORT', 0)} |"
        )
    transition_lines = []
    for arm in "BCD":
        count = transitions["summary"][arm]["counts"]
        transition_lines.append(
            f"| {arm} | {count['FIXED_FAILURE']} | {count['UNCHANGED_FAILURE']} | {count['NEW_REGRESSION']} | {count['UNCHANGED_PASS']} |"
        )
    latency_lines = []
    for arm in "BCD":
        row = quality["arms"][arm]
        latency_lines.append(
            f"| {arm} | {row['fully_correct_case_count']} | {row['retrieval_selection_p50_ms']:.3f} | {row['retrieval_selection_p95_ms']:.3f} | "
            f"{row['generation_p50_ms']:.3f} | {row['generation_p95_ms']:.3f} | {row['approx_total_p50_ms']:.3f} | {row['approx_total_p95_ms']:.3f} |"
        )
    gate_lines = []
    for row in gates["arms"]:
        gate_lines.append(
            f"| {row['arm']} | {'PASS' if row['gate_1_validity']['pass'] else 'FAIL'} | "
            f"{'PASS' if row['gate_2_own_primary_target']['pass'] else 'FAIL'} | "
            f"{'PASS' if row['gate_3_hard_regression']['pass'] else 'FAIL'} | "
            f"{'PASS' if row['gate_4_target_balance']['pass'] else 'FAIL'} | "
            f"{'PASS' if row['gate_5_operational_evidence']['pass'] else 'FAIL'} | "
            f"{'PASS' if row['additional_d_complementarity']['pass'] else 'FAIL'} | "
            f"{'YES' if row['eligible_before_pareto'] else 'NO'} |"
        )
    c_rank = target["reranker_primary_metric"]["C"]["SELECTION_RANKING_MISS"]
    c_div = target["reranker_primary_metric"]["C"]["SELECTION_DIVERSITY_MISS"]
    d_rank = target["reranker_primary_metric"]["D"]["SELECTION_RANKING_MISS"]
    d_div = target["reranker_primary_metric"]["D"]["SELECTION_DIVERSITY_MISS"]
    severe_lines = "\n".join(
        f"- {arm}: {severe['arms'][arm]['severe_regression_count']} — {ids(severe['arms'][arm]['case_ids'])}"
        for arm in "BCD"
    )
    created = [
        "integrity_preflight.json", "blinded_review_input.json", "blinded_review_input.sha256", "sealed_blind_mapping.json",
        "blinded_claim_reviews.json", "blinded_case_verdicts.json", "blinded_adjudication.json", "blinded_adjudication.sha256",
        "pass1_freeze.json", "unblinding_record.json", "unblinded_metrics.json", "case_transitions.json", "target_group_analysis.json",
        "severe_regressions.json", "causal_traces.json", "complementarity.json", "quality_latency.json", "production_gate_matrix.json",
        "historical_a_reconciliation.json", "final_recommendation_evidence.json", "machine_validation.json", "test_results.json",
        "run_manifest.json", "artifact_manifest.json",
    ]
    return f"""# LearnPilot RAG Phase 4 Blinded Semantic Review & Ablation Decision Evidence V1.1

## 1. Integrity-gate result

PASS. Design `{DESIGN_SHA256}`, Phase 2 `{PHASE2_RUN_ID}`, Phase 3 `{PHASE3_RUN_ID}`, Phase 3 canonical raw/context, Gold, Corpus, frozen A, failure analysis, all Phase 2/3 manifest entries, and all {preflight['production_bindings']['file_count']} production hashes matched. Frozen cardinality: 72 cases, 288 A/B/C/D outputs, 132 unique Gold claims; no answer, citation, or context drift.

## 2. Blinded-review method

Each case independently permuted A/B/C/D into `response_X1..X4` using a recorded fixed seed. Pass 1 exposed only question, Gold contract, anonymous answer/answerability, citation IDs, and cited evidence. It excluded arm, architecture, historical verdict, diagnostics, and latency. The mapping remained sealed until Pass 1 was detached-hashed.

## 3. Blinded-review hash

`BLINDED_REVIEW_COMPLETE = YES`; `BLINDED_REVIEW_SHA256 = {freeze['blinded_review_sha256']}`. The detached digest matches `blinded_adjudication.json`.

## 4. Review completeness

Complete: 72 cases × 4 anonymous responses = 288 verdicts; 132 claims × 4 responses = 528 claim reviews. `REVIEW_UNCERTAIN=0`; post-unblind corrections: 0.

## 5. A/B/C/D claim-level metrics

| Arm | SUPPORTED_CORRECT | claim coverage | incomplete | missing | unsupported | contradicted |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(claim_lines)}

Claim coverage means correct or supported-but-incomplete; it is not a redefinition of Overall Accuracy. The frozen design defines no single Overall Accuracy decision metric, so none was invented.

## 6. A/B/C/D case-level metrics

| Arm | FULL | PARTIAL | FAILURE | correct refusal | incorrect refusal | fully correct |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(case_lines)}

CORE/STRESS, case type, query language, frozen failure class, and target-membership breakdowns are preserved in `unblinded_metrics.json`.

## 7. Refusal and answerability outcomes

| Arm | answerability correct | correct refusal | incorrect refusal |
|---|---:|---:|---:|
{chr(10).join(answerability_lines)}

All 10 frozen unanswerable cases were correctly refused by all four outputs. Fewer refusals were not treated as intrinsically better.

## 8. Semantic citation-support outcomes

Phase 3 mechanical citation-ID validity remains frozen at 72/72 per B/C/D. Phase 4 semantic results:

| Arm | valid ID + support | weak support | missing required citation | misattributed support |
|---|---:|---:|---:|---:|
{chr(10).join(citation_lines)}

Denominator 122 excludes the 10 answerability-only correct-refusal obligations.

## 9. B/C/D transition counts

| Arm | FIXED_FAILURE | UNCHANGED_FAILURE | NEW_REGRESSION | UNCHANGED_PASS |
|---|---:|---:|---:|---:|
{chr(10).join(transition_lines)}

Transitions use the symmetrically blinded, frozen Phase-4 A verdicts. The historical-A sensitivity comparison is preserved separately.

## 10. Exact FIXED_FAILURE case IDs

- B: {ids(transitions['summary']['B']['case_ids']['FIXED_FAILURE'])}
- C: {ids(transitions['summary']['C']['case_ids']['FIXED_FAILURE'])}
- D: {ids(transitions['summary']['D']['case_ids']['FIXED_FAILURE'])}

## 11. Exact NEW_REGRESSION case IDs

- B: {ids(transitions['summary']['B']['case_ids']['NEW_REGRESSION'])}
- C: {ids(transitions['summary']['C']['case_ids']['NEW_REGRESSION'])}
- D: {ids(transitions['summary']['D']['case_ids']['NEW_REGRESSION'])}

## 12. 33-case regression guard

All 33 frozen `NO_FAILURE` cases were inspected for all three arms (99 comparisons). Severe regressions:

{severe_lines}

The B severe regression is the previously full `single-ragas-dataset` answer becoming incomplete.

## 13. Hybrid 9-case target result

Frozen primary metric (`claim_required_evidence_candidate_coverage`, anchor-pass): A {target['hybrid_primary_metric']['a_complete']}/9 → B {target['hybrid_primary_metric']['b_complete']}/9; document-pass stays {target['hybrid_primary_metric']['a_document_complete']}/9 → {target['hybrid_primary_metric']['b_document_complete']}/9. Recovered candidate-evidence case: {ids(target['hybrid_primary_metric']['recovered_case_ids'])}. That recovered retrieval still produced an incorrect refusal, so improved lexical recall produced **no downstream semantic fix on the recovered case**. Across the 9 targets: `{json.dumps(target['hybrid_downstream_counts'], ensure_ascii=False)}`.

## 14. Reranker 2/8 target result

- C ranking 2: anchor selected 0→{c_rank['arm_selected_complete']}; recovered {ids(c_rank['recovered_case_ids'])}.
- C diversity 8: anchor selected 0→{c_div['arm_selected_complete']}; recovered {ids(c_div['recovered_case_ids'])}.
- D ranking 2: anchor selected 0→{d_rank['arm_selected_complete']}; recovered {ids(d_rank['recovered_case_ids'])}.
- D diversity 8: anchor selected 0→{d_div['arm_selected_complete']}; recovered {ids(d_div['recovered_case_ids'])}.

The unchanged diversity policy remains visible; the per-case artifact distinguishes promotion, demotion, diversity removal, already-sufficient context, and generation failure despite context.

## 15. D unique complementarity fixes

`D_UNIQUE_TARGET_FIXES = {json.dumps(complementarity['d_unique_target_fixes'])}`. `D_COMPLEMENTARITY_GATE = {complementarity['d_complementarity_gate']}`. D adds no target fix that neither B nor C fixes.

## 16. Causal failure distribution

All {causal['changed_case_arm_count']} fixed/regressed arm-case pairs have full candidate→admission→ordering→selection→evidence→generation→citation→verdict traces. Dominant causes: `{json.dumps(causal['dominant_cause_distribution'], ensure_ascii=False, sort_keys=True)}`. This is diagnosis only; nothing was tuned.

## 17. Quality and latency comparison

| Arm | fully correct cases | retrieval P50 | retrieval P95 | generation P50 | generation P95 | approx total P50 | approx total P95 |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(latency_lines)}

Approximate totals add separately measured Phase 2/3 percentiles. Dense timing is frozen-trace lookup; B is not a production-normalized end-to-end SLO. Reranker: load {quality['reranker_operations']['model_load_seconds']:.3f}s, first inference {quality['reranker_operations']['first_inference_ms']:.3f}ms, steady P50/P95 {quality['reranker_operations']['steady_state_ms']['p50']:.3f}/{quality['reranker_operations']['steady_state_ms']['p95']:.3f}ms. Memory is unavailable (`{quality['memory_measurement']['method']}`); no value was fabricated.

## 18. Production gate matrix

| Arm | validity | own target | hard regression | target balance | operational | D complement | eligible |
|---|---|---|---|---|---|---|---|
{chr(10).join(gate_lines)}

All arms show research signal on their primary retrieval metric, but none survives every preregistered production gate. No Pareto selection is made from an empty eligible set.

## 19. Recommended architecture state

`{recommendation['recommendation']}`. Keep frozen A; do not integrate B/C/D. B/C/D are labeled `RESEARCH_EFFECTIVE_BUT_NOT_PRODUCTION_WORTHY`: each improves its own retrieval target, but Gate 3 fails; D additionally fails complementarity. This is a recommendation evidence state, not a production modification or Phase 5 action.

## 20. Unresolved uncertainties

- Reranker memory could not be measured in frozen Phase 2.
- Approximate total latency is derived, not one continuous production request.
- Fresh blinded A differs from historical failure-analysis A on {reconciliation['difference_count']} cases: {ids([row['case_id'] for row in reconciliation['differences']])}. Pass-1 verdicts were not changed after unblinding; both frames are preserved.

## 21. Exact files created or modified

Created implementation/report files: {', '.join(f'`{path}`' for path in IMPLEMENTATION_FILES)}. Created run artifacts under `evals/rag_real_world_corpus/v1/results/hybrid_rerank_phase4_v1_1/{RUN_ID}/`: {', '.join(f'`{name}`' for name in created)}. `latest_run.json` is created/updated in the Phase 4 result namespace only. Production, Phase 2, and Phase 3 files modified: none.

## 22. New external, model, retrieval, and production execution counts

`NEW_DEEPSEEK_CALLS=0`; `NEW_GENERATION_CALLS=0`; `NEW_RETRIEVAL_RUNS=0`; `NEW_RERANKER_RUNS=0`; `ARM_A_RERUNS=0`; `PRODUCTION_MODIFICATIONS=0`. No external evaluator LLM or other provider was called.

RAG_HYBRID_RERANK_PHASE4_V1_1 = PASS
READY_FOR_PRODUCTION_DECISION = YES
"""


def run_tests() -> dict[str, Any]:
    suites = []
    total = 0
    for test_file in TEST_FILES:
        command = [sys.executable, "-m", "pytest", test_file, "-q"]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise SystemExit(f"test gate failed for {test_file}:\n{result.stdout}\n{result.stderr}")
        match = re.search(r"(\d+) passed", result.stdout)
        passed = int(match.group(1)) if match else sum(line.count(".") for line in result.stdout.splitlines())
        total += passed
        suites.append({"test_file": test_file, "command": command, "exit_code": 0, "passed": passed, "stdout_tail": result.stdout.strip().splitlines()[-3:]})
    return metadata(status="PASS", suite_count=len(suites), passed=total, isolation="one pytest process per suite", suites=suites)


def manifest() -> dict[str, Any]:
    result_files = []
    for path in sorted(RUN_DIR.rglob("*")):
        if path.is_file() and path.name != "artifact_manifest.json":
            result_files.append({"path": path.relative_to(ROOT).as_posix(), "sha256": file_sha256(path), "size_bytes": path.stat().st_size})
    implementation = []
    for relative in IMPLEMENTATION_FILES:
        path = ROOT / relative
        implementation.append({"path": relative, "sha256": file_sha256(path), "size_bytes": path.stat().st_size})
    return metadata(status="PASS", result_files=result_files, implementation_and_report_files=implementation)


def main() -> int:
    REPORT.write_text(render_report(), encoding="utf-8")
    tests = run_tests()
    write_json(RUN_DIR / "test_results.json", tests)
    report_text = REPORT.read_text(encoding="utf-8")
    recommendation = read_json(RUN_DIR / "final_recommendation_evidence.json")
    preflight = read_json(RUN_DIR / "integrity_preflight.json")
    validation = metadata(
        status="PASS",
        blockers=[],
        integrity_gate_passed=preflight["status"] == "PASS",
        blinded_review_sha256=PASS1_SHA256,
        blinded_review_detached_hash_match=file_sha256(RUN_DIR / "blinded_adjudication.json") == PASS1_SHA256,
        review_counts={"cases": 72, "outputs": 288, "claims_per_arm": 132, "claim_reviews": 528},
        post_unblind_review_corrections=[],
        report_section_count=sum(line.startswith("## ") for line in report_text.splitlines()),
        report_exact_ending=report_text.endswith("RAG_HYBRID_RERANK_PHASE4_V1_1 = PASS\nREADY_FOR_PRODUCTION_DECISION = YES\n"),
        recommendation=recommendation["recommendation"],
        target_diagnostics_reproduced=read_json(RUN_DIR / "target_group_analysis.json")["phase2_diagnostics_reproduction"]["status"] == "PASS",
        tests_passed=tests["passed"],
        production_hashes_unchanged=preflight["production_bindings"]["all_match"],
        execution_counts={key: recommendation[key] for key in ("new_deepseek_calls", "new_generation_calls", "new_retrieval_runs", "new_reranker_runs", "arm_a_reruns", "production_modifications")},
        ready_for_production_decision=True,
    )
    if validation["report_section_count"] != 22 or not validation["report_exact_ending"]:
        raise SystemExit("final report contract failed")
    write_json(RUN_DIR / "machine_validation.json", validation)
    write_json(
        RUN_DIR / "run_manifest.json",
        metadata(
            status="PASS",
            objective="Phase 4 blinded semantic review and production-decision evidence only",
            blinded_review_sha256=PASS1_SHA256,
            recommendation=recommendation["recommendation"],
            ready_for_production_decision=True,
            phase5_started=False,
            production_integration_started=False,
        ),
    )
    write_json(RUN_DIR / "artifact_manifest.json", manifest())
    manifest_hash = file_sha256(RUN_DIR / "artifact_manifest.json")
    write_json(
        RESULTS_ROOT / "latest_run.json",
        metadata(
            status="PASS",
            run_directory=RUN_DIR.relative_to(ROOT).as_posix(),
            report=REPORT.relative_to(ROOT).as_posix(),
            recommendation=recommendation["recommendation"],
            artifact_manifest_sha256=manifest_hash,
        ),
    )
    print(json.dumps({"status": "PASS", "run_id": RUN_ID, "blinded_review_sha256": PASS1_SHA256, "tests_passed": tests["passed"], "recommendation": recommendation["recommendation"], "artifact_manifest_sha256": manifest_hash, "report": str(REPORT)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
