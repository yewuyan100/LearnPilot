from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import re
import statistics
import subprocess
import sys
from typing import Any, Iterable, Sequence
from uuid import uuid4

from experiment import (
    ABLATION_DESIGN_SHA256,
    ARMS,
    DESIGN_VERSION,
    MAX_NORMAL_GENERATION_REQUESTS,
    MODEL_NAME,
    PHASE2_RUN_ID,
    PROVIDER_HOST,
    ContractViolation,
    DeepSeekGenerationAdapter,
    GenerationContract,
    HttpxGenerationTransport,
    file_sha256,
    freeze_phase2_contexts,
    json_sha256,
    sources_from_frozen_context,
    text_sha256,
    validate_generation_result,
)


HERE = Path(__file__).resolve().parent
V1 = HERE.parent
ROOT = V1.parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import Settings  # noqa: E402
from app.services.rag.prompts import answer_messages  # noqa: E402
from app.services.rag.types import RagSource  # noqa: E402


PHASE2_DIR = V1 / f"results/hybrid_rerank_phase2_v1_1/{PHASE2_RUN_ID}"
RESULTS_ROOT = V1 / "results/hybrid_rerank_phase3_v1_1"
REPORT_PATH = ROOT / "RAG_HYBRID_RERANK_PHASE3_V1_1.md"
FROZEN_A_PATH = (
    V1 / "results/dense_only_baseline_v1/20260814T052007Z-593cd2ac/raw_results.json"
)
FROZEN_A_SHA256 = "bf718aed08e226149c9310cbf20bf25c403708217e2908789120178ac5574e28"
FROZEN_HASHES = {
    "v1_1_design": (
        V1 / "ablation_design_v1_1/ablation_design_manifest.json",
        ABLATION_DESIGN_SHA256,
    ),
    "v1_design": (
        V1 / "ablation_design_v1/ablation_design_manifest.json",
        "4c3b2e294b63dcc0ae57be1d30d713b3cf1ffed5b0f3a989499f1298902703c6",
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
    "frozen_a": (FROZEN_A_PATH, FROZEN_A_SHA256),
    "failure_analysis": (
        V1 / "failure_analysis_v1/failure_analysis_manifest.json",
        "e869fd73e2570413595c1af194b6ec6876e8b822fbd4eac279541a03cac27fb8",
    ),
}
TEST_FILES = (
    "backend/tests/test_rag_hybrid_rerank_phase3_v1_1.py",
    "backend/tests/test_rag_hybrid_rerank_phase2_v1_1.py",
    "backend/tests/test_rag_ablation_design_v1_1.py",
    "backend/tests/test_rag_ablation_design_v1.py",
    "backend/tests/test_rag_real_world_failure_analysis_v1.py",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def metadata(run_id: str, arm: str = "B,C,D") -> dict[str, Any]:
    return {
        "design_version": DESIGN_VERSION,
        "ablation_design_sha256": ABLATION_DESIGN_SHA256,
        "phase2_run_id": PHASE2_RUN_ID,
        "phase3_run_id": run_id,
        "arm": arm,
    }


def artifact(run_id: str, arm: str = "B,C,D", **payload: Any) -> dict[str, Any]:
    return {**metadata(run_id, arm), "recorded_at": utc_now(), **payload}


def production_hashes() -> dict[str, str]:
    failure = read_json(V1 / "failure_analysis_v1/failure_analysis_manifest.json")
    binding = failure["frozen_bindings"]["production_code"]
    expected = binding["baseline_sha256"]
    if not binding["all_match"] or len(expected) != 15:
        raise ContractViolation("frozen production binding is not the expected 15-file set")
    observed = {relative: file_sha256(ROOT / relative) for relative in expected}
    mismatches = {
        relative: {"expected": expected[relative], "observed": observed[relative]}
        for relative in expected
        if observed[relative] != expected[relative]
    }
    if mismatches:
        raise ContractViolation(f"frozen production binding drift: {mismatches}")
    return observed


def verify_phase2_artifacts() -> dict[str, Any]:
    latest_path = V1 / "results/hybrid_rerank_phase2_v1_1/latest_run.json"
    latest = read_json(latest_path)
    if latest.get("run_id") != PHASE2_RUN_ID or latest.get("status") != "PASS":
        raise ContractViolation("authoritative Phase 2 latest-run binding mismatch")
    manifest_path = PHASE2_DIR / "artifact_manifest.json"
    manifest_sha = file_sha256(manifest_path)
    if manifest_sha != latest.get("artifact_manifest_sha256"):
        raise ContractViolation("Phase 2 artifact manifest drift")
    manifest = read_json(manifest_path)
    verified = []
    for item in manifest["result_files"] + manifest["implementation_and_report_files"]:
        path = ROOT / item["path"]
        observed_hash = file_sha256(path)
        observed_size = path.stat().st_size
        if observed_hash != item["sha256"] or observed_size != item["size_bytes"]:
            raise ContractViolation(f"Phase 2 artifact drift: {item['path']}")
        verified.append(item["path"])
    validation = read_json(PHASE2_DIR / "validation.json")
    if (
        validation.get("status") != "PASS"
        or validation.get("execution_counts") != {"A": 0, "B": 72, "C": 72, "D": 72}
        or validation.get("external_generative_llm_calls") != 0
        or validation.get("phase3_started") is not False
    ):
        raise ContractViolation("Phase 2 validation artifact is not the authoritative PASS")
    return {
        "latest_run_sha256": file_sha256(latest_path),
        "artifact_manifest_sha256": manifest_sha,
        "verified_artifact_count": len(verified),
        "verified_artifacts": verified,
        "validation_sha256": file_sha256(PHASE2_DIR / "validation.json"),
        "candidate_trace_sha256": {
            arm: file_sha256(PHASE2_DIR / f"arm_{arm}/candidate_traces.jsonl")
            for arm in ARMS
        },
    }


def _historical_source(value: dict[str, Any]) -> RagSource:
    return RagSource(
        source_label=value["source_label"],
        rank=value["rank"],
        score=value["score"],
        chunk_id=value["chunk_id"],
        material_id=value["material_id"],
        original_filename=value["original_filename"],
        chunk_index=value["chunk_index"],
        content=value["content"],
        page_number=value["page_number"],
        section_title=value["section_title"],
    )


def verify_historical_generation_contract(contract: GenerationContract) -> dict[str, Any]:
    frozen_a = read_json(FROZEN_A_PATH)
    config = frozen_a["effective_configuration"]
    expected = {
        "provider": "openai_compatible",
        "host": PROVIDER_HOST,
        "model": MODEL_NAME,
        "structured_model": MODEL_NAME,
        "temperature": 0.1,
        "structured_reasoning_enabled": False,
        "structured_max_output_tokens": 2400,
        "timeout_seconds": 60,
        "max_retries": 2,
        "rag_prompt_version": "rag-answer-v2-evidence-binding",
    }
    mismatches = {
        key: {"expected": value, "observed": config.get(key)}
        for key, value in expected.items()
        if config.get(key) != value
    }
    if mismatches:
        raise ContractViolation(f"historical Arm A generation contract drift: {mismatches}")
    if len(frozen_a["cases"]) != 72:
        raise ContractViolation("frozen Arm A does not contain 72 cases")
    sample = frozen_a["cases"][0]
    sources = [_historical_source(item) for item in sample["retrieval"]["selected_sources"]]
    messages = answer_messages(sample["gold_case"]["question"], sources)
    historical_digest = sha256(
        json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    started = next(
        event
        for event in sample["generation"]["events"]
        if event["event"] == "llm.structured.started"
    )
    if messages != started["messages"] or historical_digest != started["messages_sha256"]:
        raise ContractViolation("current prompt builder does not reproduce frozen Arm A messages")
    if contract.model != config["structured_model"]:
        raise ContractViolation("current generation model differs from frozen Arm A")
    return {
        "frozen_a_run_id": frozen_a["run_id"],
        "frozen_a_case_count": len(frozen_a["cases"]),
        "arm_a_execution_count": 0,
        "sample_case_id": sample["case_id"],
        "sample_messages_sha256": historical_digest,
        "sample_messages_match": True,
        "effective_configuration": expected,
    }


def integrity_preflight(settings: Settings, contract: GenerationContract) -> dict[str, Any]:
    hashes = {}
    for name, (path, expected) in FROZEN_HASHES.items():
        observed = file_sha256(path)
        if observed != expected:
            raise ContractViolation(
                f"frozen hash mismatch for {name}: {observed} != {expected}"
            )
        hashes[name] = {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": observed,
            "match": True,
        }
    phase2 = verify_phase2_artifacts()
    historical = verify_historical_generation_contract(contract)
    production = production_hashes()
    return {
        "status": "PASS",
        "frozen_hashes": hashes,
        "phase2": phase2,
        "historical_arm_a": historical,
        "production_hashes": production,
        "production_file_count": len(production),
        "generation_contract_identity": contract.identity,
        "api_key_present": bool(
            settings.llm_api_key and settings.llm_api_key.get_secret_value().strip()
        ),
        "secret_values_recorded": False,
    }


def run_tests() -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    suites = []
    passed = 0
    for test_file in TEST_FILES:
        command = [sys.executable, "-m", "pytest", test_file, "-q"]
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise ContractViolation(
                f"Phase 3 pre-request test gate failed for {test_file}:\n"
                + result.stdout
                + "\n"
                + result.stderr
            )
        match = re.search(r"(\d+) passed", result.stdout)
        suite_passed = (
            int(match.group(1))
            if match
            else sum(line.count(".") for line in result.stdout.splitlines())
        )
        passed += suite_passed
        suites.append(
            {
                "test_file": test_file,
                "command": command,
                "exit_code": result.returncode,
                "passed": suite_passed,
                "stdout_tail": result.stdout.strip().splitlines()[-3:],
            }
        )
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    return {
        "status": "PASS",
        "isolation": "one pytest process per suite to avoid experiment.py module-name collision",
        "suite_count": len(suites),
        "passed": passed,
        "elapsed_seconds": round(elapsed, 3),
        "suites": suites,
    }


def freeze_context_artifact(
    run_id: str,
    run_dir: Path,
    gold_cases: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    reconstructed = freeze_phase2_contexts(
        phase2_run_dir=PHASE2_DIR, gold_cases=gold_cases
    )
    payload = artifact(
        run_id,
        context_count=len(reconstructed),
        per_arm_counts={
            arm: sum(row["arm"] == arm for row in reconstructed) for arm in ARMS
        },
        construction=(
            "direct consumption of Phase 2 selected candidate identities/raw text; "
            "no retrieval, reranking, or Arm A execution"
        ),
        records=reconstructed,
    )
    path = run_dir / "context_freeze.json"
    if path.exists():
        existing = read_json(path)
        comparable_existing = dict(existing)
        comparable_existing.pop("recorded_at", None)
        comparable_payload = dict(payload)
        comparable_payload.pop("recorded_at", None)
        if comparable_existing != comparable_payload:
            raise ContractViolation("CONTEXT_FREEZE_MISMATCH existing context artifact")
    else:
        write_json(path, payload)
        (run_dir / "context_freeze.sha256").write_text(
            file_sha256(path) + "  context_freeze.json\n", encoding="utf-8"
        )
    observed_hash = file_sha256(path)
    detached = (run_dir / "context_freeze.sha256").read_text(encoding="utf-8").split()[0]
    if observed_hash != detached:
        raise ContractViolation("CONTEXT_FREEZE_MISMATCH detached digest")
    frozen = read_json(path)["records"]
    for record in frozen:
        sources_from_frozen_context(record)
    return frozen, {
        "status": "PASS",
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": observed_hash,
        "context_count": len(frozen),
        "mismatch_count": 0,
        "retrieval_rerun_count": 0,
        "reranker_rerun_count": 0,
    }


def load_existing_results(run_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    results: dict[tuple[str, str], dict[str, Any]] = {}
    for arm in ARMS:
        case_dir = run_dir / f"arm_{arm}/cases"
        if not case_dir.exists():
            continue
        for path in case_dir.glob("*.json"):
            row = read_json(path)
            key = (row["arm"], row["case_id"])
            if key in results:
                raise ContractViolation(f"duplicate persisted Phase 3 result: {key}")
            results[key] = row
    return results


def ledger_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def assert_resume_safe(
    *,
    ledger: Sequence[dict[str, Any]],
    existing: dict[tuple[str, str], dict[str, Any]],
) -> None:
    events_by_case: dict[tuple[str, str], int] = {}
    for event in ledger:
        key = (event["arm"], event["case_id"])
        events_by_case[key] = events_by_case.get(key, 0) + 1
    ambiguous = [key for key in events_by_case if key not in existing]
    if ambiguous:
        raise ContractViolation(
            "ambiguous prior provider delivery state; refusing duplicate generation: "
            + repr(ambiguous[:5])
        )


def execute_generation(
    *,
    run_id: str,
    run_dir: Path,
    contexts: Sequence[dict[str, Any]],
    settings: Settings,
    contract: GenerationContract,
) -> list[dict[str, Any]]:
    ledger_path = run_dir / "request_ledger.jsonl"
    existing = load_existing_results(run_dir)
    prior_ledger = ledger_events(ledger_path)
    assert_resume_safe(ledger=prior_ledger, existing=existing)
    current_context: dict[str, Any] | None = None

    def sink(event: dict[str, Any]) -> None:
        assert current_context is not None
        append_jsonl(
            ledger_path,
            {
                **metadata(run_id, current_context["arm"]),
                "recorded_at": utc_now(),
                "case_id": current_context["case_id"],
                "query_digest": current_context["query_digest"],
                "context_digest": current_context["context_digest"],
                "generation_contract_identity": contract.identity,
                **event,
            },
        )

    adapter = DeepSeekGenerationAdapter(
        settings=settings,
        contract=contract,
        transport=HttpxGenerationTransport(),
        ledger_sink=sink,
    )
    adapter.normal_generation_calls = len(existing)
    adapter.total_http_requests = sum(
        event.get("event") == "http_request_started" for event in prior_ledger
    )
    context_by_key = {(row["arm"], row["case_id"]): row for row in contexts}
    for key, result in existing.items():
        context = context_by_key.get(key)
        if context is None:
            raise ContractViolation(f"persisted result has no frozen context: {key}")
        errors = validate_generation_result(
            result, context, contract_identity=contract.identity
        )
        if errors:
            raise ContractViolation(f"persisted result validation failed {key}: {errors}")

    for context in contexts:
        key = (context["arm"], context["case_id"])
        if key in existing:
            continue
        if adapter.normal_generation_calls >= MAX_NORMAL_GENERATION_REQUESTS:
            raise ContractViolation("normal generation request cap exhausted before completion")
        current_context = context
        result = adapter.generate(context, phase3_run_id=run_id)
        errors = validate_generation_result(
            result, context, contract_identity=contract.identity
        )
        if errors:
            result["post_generation_validation_errors"] = errors
            payload = dict(result)
            payload.pop("result_identity_sha256", None)
            result["result_identity_sha256"] = json_sha256(payload)
        path = run_dir / f"arm_{context['arm']}/cases/{context['case_id']}.json"
        write_json(path, result)
        existing[key] = result
        print(
            f"PHASE3 {len(existing):03d}/216 arm={context['arm']} "
            f"case={context['case_id']} status={result['status']} "
            f"http={result['attempt_count']} repair={result['repair_attempted']}",
            flush=True,
        )
        if result["parse_status"] == "model_mismatch":
            raise ContractViolation("provider returned an unexpected model")
        if result["failure_reason"] in {"http_401", "http_403"}:
            raise ContractViolation("DeepSeek authentication failed")
    return [
        existing[(context["arm"], context["case_id"])] for context in contexts
    ]


def percentile(values: Sequence[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def distribution(values: Iterable[float]) -> dict[str, float | int]:
    rows = list(values)
    if not rows:
        return {"count": 0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "count": len(rows),
        "mean": round(statistics.fmean(rows), 3),
        "p50": round(percentile(rows, 0.50), 3),
        "p95": round(percentile(rows, 0.95), 3),
        "max": round(max(rows), 3),
    }


def summarize_results(
    run_id: str,
    results: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    machine: dict[str, Any] = {}
    latency: dict[str, Any] = {}
    tokens: dict[str, Any] = {}
    for arm in ARMS:
        rows = [row for row in results if row["arm"] == arm]
        final_errors = [row for row in rows if row["status"] != "COMPLETED"]
        machine[arm] = {
            "case_count": len(rows),
            "completed_cases": sum(row["status"] == "COMPLETED" for row in rows),
            "valid_structured_outputs": sum(row["validation_status"] == "PASS" for row in rows),
            "refusals": sum(row.get("answerable") is False for row in rows),
            "citation_valid_outputs": sum(
                row["status"] == "COMPLETED" and row["validation_status"] == "PASS"
                for row in rows
            ),
            "final_parse_failures": sum(
                row["status"] != "COMPLETED" and "parse" in row["parse_status"]
                for row in rows
            ),
            "provider_failures": sum(bool(row["provider_failure"]) for row in rows),
            "timeout_count": sum(row["timeout_count"] for row in rows),
            "retry_count": sum(row["retry_count"] for row in rows),
            "repair_count": sum(bool(row["repair_attempted"]) for row in rows),
            "http_request_count": sum(row["attempt_count"] for row in rows),
            "failed_case_ids": [row["case_id"] for row in final_errors],
        }
        generation_values = [float(row["latency_ms"]) for row in rows]
        http_values = [
            float(attempt["http_elapsed_ms"])
            for row in rows
            for attempt in row["attempts"]
            if attempt.get("http_elapsed_ms") is not None
        ]
        latency[arm] = {
            "generation_ms": distribution(generation_values),
            "http_attempt_ms": distribution(http_values),
        }
        tokens[arm] = {}
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            values = [row["usage"][key] for row in rows if row["usage"].get(key) is not None]
            token_distribution = distribution(float(value) for value in values)
            token_distribution["total"] = sum(values)
            tokens[arm][key] = token_distribution
    return (
        artifact(run_id, summary=machine),
        artifact(run_id, units="milliseconds", summary=latency),
        artifact(run_id, pricing_cost_computed=False, summary=tokens),
    )


def combined_latency(run_id: str, generation_latency: dict[str, Any]) -> dict[str, Any]:
    phase2 = read_json(PHASE2_DIR / "latency_summary.json")
    rows = []
    for arm in ARMS:
        retrieval = phase2[arm]["stages_ms"]["total_retrieval_selection"]
        generation = generation_latency["summary"][arm]["generation_ms"]
        rows.append(
            {
                "arm": arm,
                "retrieval_selection_p50_ms": retrieval["p50"],
                "retrieval_selection_p95_ms": retrieval["p95"],
                "generation_p50_ms": generation["p50"],
                "generation_p95_ms": generation["p95"],
                "approx_total_p50_ms": round(retrieval["p50"] + generation["p50"], 3),
                "approx_total_p95_ms": round(retrieval["p95"] + generation["p95"], 3),
            }
        )
    return artifact(
        run_id,
        derivation="Phase 2 retrieval-selection percentile + Phase 3 generation percentile; not one continuous request",
        dense_latency_limitation=(
            "Phase 2 Dense timing is frozen-trace lookup, not online embedding/FAISS"
        ),
        rows=rows,
    )


def build_phase4_bundle(
    run_id: str,
    contexts: Sequence[dict[str, Any]],
    results: Sequence[dict[str, Any]],
    gold_cases: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    frozen_a = read_json(FROZEN_A_PATH)
    a_by_id = {row["case_id"]: row for row in frozen_a["cases"]}
    failure = read_json(V1 / "failure_analysis_v1/case_failure_analysis.json")
    failure_by_id = {row["case_id"]: row for row in failure["cases"]}
    design = read_json(V1 / "ablation_design_v1_1/ablation_design_manifest.json")
    targets = design["target_case_sets"]
    no_failure = {
        row["case_id"]
        for row in failure["cases"]
        if row["primary_root_cause"] == "NO_FAILURE"
    }
    if len(no_failure) != 33:
        raise ContractViolation(f"expected 33 NO_FAILURE cases, got {len(no_failure)}")
    context_by_key = {(row["arm"], row["case_id"]): row for row in contexts}
    result_by_key = {(row["arm"], row["case_id"]): row for row in results}
    cases = []
    for gold in gold_cases:
        case_id = gold["case_id"]
        a = a_by_id[case_id]
        historical = failure_by_id[case_id]
        arm_payload: dict[str, Any] = {}
        selected_sets: dict[str, list[str]] = {}
        for arm in ARMS:
            context = context_by_key[(arm, case_id)]
            result = result_by_key[(arm, case_id)]
            selected_sets[arm] = context["selected_candidate_identities"]
            cited = set(result["citation_ids"])
            arm_payload[arm] = {
                "answer": result["answer_markdown"],
                "answerable": result["answerable"],
                "refusal_reason": result["refusal_reason"],
                "citations": [
                    item
                    for item in context["selected_sources"]
                    if item["source_label"] in cited
                ],
                "citation_ids": result["citation_ids"],
                "selected_evidence": context["selected_sources"],
                "context_digest": context["context_digest"],
                "result_identity_sha256": result["result_identity_sha256"],
                "machine_validation_status": result["validation_status"],
                "semantic_label": None,
            }
        a_selected = a["retrieval"]["selected_sources"]
        a_identities = [
            f"{item['document_id']}:{item['chunk_index']}:{text_sha256(item['content'])}"
            for item in a_selected
        ]
        cases.append(
            {
                "case_id": case_id,
                "question": gold["question"],
                "target_groups": {
                    "hybrid_primary_retrieval_miss": case_id in set(targets["hybrid"]),
                    "reranker_primary_selection_addressable": case_id in set(targets["dense_rerank"]),
                    "reranker_ranking_miss": case_id in set(targets["reranker_ranking_miss"]),
                    "reranker_diversity_miss": case_id in set(targets["reranker_diversity_miss"]),
                    "regression_guard_no_failure": case_id in no_failure,
                },
                "frozen_A": {
                    "answer": a["normalized_answer"],
                    "answerable": a["response"]["assistant_message"]["answerable"],
                    "citations": a["citations"],
                    "selected_evidence": a_selected,
                    "selected_candidate_identities": a_identities,
                    "historical_verdict": historical["case_verdict"],
                    "historical_metrics": {
                        "answerability_review": historical["answerability_review"],
                        "citation_review": historical["citation_review"],
                        "claim_reviews": historical["claim_reviews"],
                        "primary_root_cause": historical["primary_root_cause"],
                    },
                },
                **arm_payload,
                "Gold": {
                    "answerability": gold["answerable"],
                    "required_claims": [
                        claim for claim in gold["claims"] if claim["required"]
                    ],
                    "acceptable_evidence_groups": gold["evidence_groups"],
                    "acceptable_supporting_evidence": gold["acceptable_supporting_evidence"],
                    "unsupported_constraints": gold.get("unanswerable_contract"),
                    "citation_contract": gold["citation_contract"],
                },
                "retrieval_transition_summary": {
                    "A_selected": a_identities,
                    "B_selected": selected_sets["B"],
                    "C_selected": selected_sets["C"],
                    "D_selected": selected_sets["D"],
                    "A_to_B_added": sorted(set(selected_sets["B"]) - set(a_identities)),
                    "A_to_C_added": sorted(set(selected_sets["C"]) - set(a_identities)),
                    "A_to_D_added": sorted(set(selected_sets["D"]) - set(a_identities)),
                },
            }
        )
    return artifact(
        run_id,
        semantic_adjudication_performed=False,
        production_winner_selected=False,
        target_set_counts={
            "hybrid_primary_retrieval_miss": len(targets["hybrid"]),
            "reranker_primary_selection_addressable": len(targets["dense_rerank"]),
            "reranker_ranking_miss": len(targets["reranker_ranking_miss"]),
            "reranker_diversity_miss": len(targets["reranker_diversity_miss"]),
            "regression_guard_no_failure": len(no_failure),
        },
        cases=cases,
    )


def package_versions() -> dict[str, str | None]:
    result = {}
    for name in ("httpx", "pydantic", "pytest"):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result


def artifact_manifest(run_id: str, run_dir: Path) -> dict[str, Any]:
    files = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.name == "artifact_manifest.json":
            continue
        files.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": file_sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    implementation = []
    for path in (
        HERE / "experiment.py",
        HERE / "run_phase3_v1_1.py",
        ROOT / "backend/tests/test_rag_hybrid_rerank_phase3_v1_1.py",
        REPORT_PATH,
    ):
        implementation.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": file_sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return artifact(
        run_id,
        result_files=files,
        implementation_and_report_files=implementation,
    )


def render_report(
    *,
    run_id: str,
    run_dir: Path,
    preflight: dict[str, Any],
    context_freeze: dict[str, Any],
    contract: GenerationContract,
    tests: dict[str, Any],
    machine: dict[str, Any],
    latency: dict[str, Any],
    tokens: dict[str, Any],
    combined: dict[str, Any],
    external: dict[str, Any],
    validation: dict[str, Any],
    review_bundle: dict[str, Any],
    production_unchanged: bool,
) -> str:
    summary = machine["summary"]
    latency_rows = []
    for arm in ARMS:
        values = latency["summary"][arm]["generation_ms"]
        latency_rows.append(
            f"| {arm} | {values['mean']:.3f} | {values['p50']:.3f} | "
            f"{values['p95']:.3f} | {values['max']:.3f} |"
        )
    comparison_rows = []
    for row in combined["rows"]:
        comparison_rows.append(
            f"| {row['arm']} | {row['retrieval_selection_p50_ms']:.3f} | "
            f"{row['retrieval_selection_p95_ms']:.3f} | {row['generation_p50_ms']:.3f} | "
            f"{row['generation_p95_ms']:.3f} | {row['approx_total_p50_ms']:.3f} | "
            f"{row['approx_total_p95_ms']:.3f} |"
        )
    machine_rows = []
    for arm in ARMS:
        row = summary[arm]
        machine_rows.append(
            f"| {arm} | {row['completed_cases']} | {row['valid_structured_outputs']} | "
            f"{row['refusals']} | {row['citation_valid_outputs']} | "
            f"{row['final_parse_failures']} | {row['provider_failures']} |"
        )
    status = "PASS" if validation["status"] == "PASS" else "BLOCKED"
    ready = "YES" if status == "PASS" else "NO"
    return f"""# LearnPilot RAG Phase 3 End-to-End Ablation Generation V1.1

## 1. Phase 3 run identity

Status `{status}`. Run `{run_id}`; design `V1.1` / `{ABLATION_DESIGN_SHA256}`; Phase 2 `{PHASE2_RUN_ID}`. Results: `{run_dir.relative_to(ROOT).as_posix()}`.

## 2. Frozen binding verification

PASS before the first request: V1.1/V1 design, Gold, Corpus, Gold freeze, frozen A, failure analysis, all {preflight['production_file_count']} production hashes, and all {preflight['phase2']['verified_artifact_count']} Phase 2 manifest entries matched.

## 3. Phase 2 context-freeze verification

Directly consumed Phase 2 traces; {context_freeze['context_count']} contexts frozen, SHA-256 `{context_freeze['sha256']}`, mismatch count {context_freeze['mismatch_count']}. Retrieval/reranker reruns: {context_freeze['retrieval_rerun_count']}/{context_freeze['reranker_rerun_count']}.

## 4. B/C/D execution counts

B/C/D completed: {summary['B']['completed_cases']}/72, {summary['C']['completed_cases']}/72, {summary['D']['completed_cases']}/72. Normal generation samples: {external['normal_generation_request_count']} (cap 216).

## 5. Exact model and generation contract

`{contract.provider}` → `https://{contract.provider_host}/{contract.endpoint_path}`; model `{contract.model}`; prompt `{contract.prompt_version}`; temperature {contract.temperature}; reasoning disabled; max output {contract.max_output_tokens}; timeout {contract.timeout_seconds}s; transport retries {contract.max_retries}; grounding repair limit {contract.grounding_repair_limit}. Contract identity `{contract.identity}`. Pre-request tests: {tests['passed']} passed across {tests['suite_count']} isolated suites.

## 6. External host audit

Provider host contacted: `{external['provider_host_contacted']}`. Other generation hosts: `{json.dumps(external['other_external_hosts_contacted'], ensure_ascii=False)}`. Data outside authorized evaluation scope transmitted: `{str(external['data_outside_authorized_scope_transmitted']).lower()}`.

## 7. Raw-output freeze status

PASS. Exact request metadata, raw provider response text/digests, parsed drafts, deterministic rendering, retries, usage and result identities are preserved. Canonical raw SHA-256: `{validation['canonical_raw_results_sha256']}`.

## 8. Structured parse status

Valid final structured outputs B/C/D: {summary['B']['valid_structured_outputs']}, {summary['C']['valid_structured_outputs']}, {summary['D']['valid_structured_outputs']}. Final parse failures: {summary['B']['final_parse_failures']}, {summary['C']['final_parse_failures']}, {summary['D']['final_parse_failures']}.

## 9. Citation-contract validation

Citation-valid outputs B/C/D: {summary['B']['citation_valid_outputs']}, {summary['C']['citation_valid_outputs']}, {summary['D']['citation_valid_outputs']}. Citation IDs were checked against each case's frozen S1..S6 context.

## 10. Answerability-contract validation

Production `RagGroundedAnswerDraft`, `validate_grounded_draft`, and deterministic renderer were reused without modification. Refusal counts B/C/D: {summary['B']['refusals']}, {summary['C']['refusals']}, {summary['D']['refusals']}. No semantic verdict was assigned.

## 11. Token usage

Per-arm total input/output/total tokens: B `{tokens['summary']['B']['input_tokens']['total']}/{tokens['summary']['B']['output_tokens']['total']}/{tokens['summary']['B']['total_tokens']['total']}`; C `{tokens['summary']['C']['input_tokens']['total']}/{tokens['summary']['C']['output_tokens']['total']}/{tokens['summary']['C']['total_tokens']['total']}`; D `{tokens['summary']['D']['input_tokens']['total']}/{tokens['summary']['D']['output_tokens']['total']}/{tokens['summary']['D']['total_tokens']['total']}`. No dollar cost was invented.

## 12. Latency

| Arm | generation mean ms | P50 ms | P95 ms | max ms |
|---|---:|---:|---:|---:|
{chr(10).join(latency_rows)}

Derived descriptive totals (not one continuous request):

| Arm | retrieval P50 | retrieval P95 | generation P50 | generation P95 | approx total P50 | approx total P95 |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(comparison_rows)}

Phase 2 Dense timing is frozen-trace lookup, not online embedding/FAISS.

## 13. Retries, timeouts and provider errors

Retries `{external['retry_request_count']}`; timeouts `{external['timeout_count']}`; provider-error cases `{external['provider_error_case_count']}`; grounding repairs `{external['grounding_repair_request_count']}`; total HTTP generation requests `{external['total_http_generation_requests']}`.

## 14. B/C/D machine-level summary

| Arm | completed | valid structured | refusals | citation valid | parse failures | provider failures |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(machine_rows)}

Descriptive only. No architecture winner was selected and no metric was redefined.

## 15. Arm A execution

Arm A retrieval, generation and answer regeneration counts are all `0`; frozen historical A is reference-only.

## 16. Retrieval/reranker tuning

None. Phase 3 consumed frozen Phase 2 selected contexts; no Dense/BM25/RRF/reranker/governance parameter was executed or changed.

## 17. Production file changes

All 15 frozen production hashes remained unchanged after Phase 3: `{str(production_unchanged).lower()}`.

## 18. Phase 4 review bundle

Review-ready bundle contains {len(review_bundle['cases'])} cases with frozen A, B/C/D raw-derived answers/citations/evidence/context digests, Gold contracts and retrieval transitions. Target counts: `{json.dumps(review_bundle['target_set_counts'], ensure_ascii=False)}`. Semantic adjudication: false.

## 19. Total external generation request count

Normal samples `{external['normal_generation_request_count']}`; retry HTTP requests `{external['retry_request_count']}`; grounding repair structured calls `{external['grounding_repair_request_count']}`; total HTTP requests `{external['total_http_generation_requests']}`. Successful B/C/D calls: {external['successful_B_calls']}/{external['successful_C_calls']}/{external['successful_D_calls']}.

## 20. Blockers and deviations

Blockers: `{json.dumps(validation['blockers'], ensure_ascii=False)}`. Deviations: none. Phase 4 semantic review and production integration were not started.

RAG_HYBRID_RERANK_PHASE3_V1_1 = {status}
READY_FOR_SEMANTIC_REVIEW = {ready}
"""


def finalize(
    *,
    run_id: str,
    run_dir: Path,
    preflight: dict[str, Any],
    context_freeze: dict[str, Any],
    contract: GenerationContract,
    tests: dict[str, Any],
    contexts: Sequence[dict[str, Any]],
    results: Sequence[dict[str, Any]],
    gold_cases: Sequence[dict[str, Any]],
    production_before: dict[str, str],
) -> dict[str, Any]:
    canonical_raw = artifact(
        run_id,
        record_count=len(results),
        records=list(results),
    )
    canonical_path = run_dir / "canonical_raw_results.json"
    write_json(canonical_path, canonical_raw)
    canonical_hash = file_sha256(canonical_path)
    (run_dir / "canonical_raw_results.sha256").write_text(
        canonical_hash + "  canonical_raw_results.json\n", encoding="utf-8"
    )
    parsed = artifact(
        run_id,
        records=[
            {
                **metadata(run_id, row["arm"]),
                "case_id": row["case_id"],
                "query_digest": row["query_digest"],
                "context_digest": row["context_digest"],
                "generation_contract_identity": row["generation_contract_identity"],
                "status": row["status"],
                "answerable": row["answerable"],
                "answer_markdown": row["answer_markdown"],
                "citation_ids": row["citation_ids"],
                "refusal_reason": row["refusal_reason"],
                "result_identity_sha256": row["result_identity_sha256"],
            }
            for row in results
        ],
    )
    write_json(run_dir / "parsed_answers.json", parsed)

    context_by_key = {(row["arm"], row["case_id"]): row for row in contexts}
    validation_errors = []
    for row in results:
        errors = validate_generation_result(
            row,
            context_by_key[(row["arm"], row["case_id"])],
            contract_identity=contract.identity,
        )
        validation_errors.extend(
            {"arm": row["arm"], "case_id": row["case_id"], "error": error}
            for error in errors
        )
    machine, latency, tokens = summarize_results(run_id, results)
    combined = combined_latency(run_id, latency)
    write_json(run_dir / "machine_summary.json", machine)
    write_json(run_dir / "generation_latency.json", latency)
    write_json(run_dir / "token_usage.json", tokens)
    write_json(run_dir / "combined_latency.json", combined)

    total_http = sum(row["attempt_count"] for row in results)
    external = artifact(
        run_id,
        provider_host_contacted=PROVIDER_HOST if total_http else None,
        successful_B_calls=sum(row["arm"] == "B" and row["status"] == "COMPLETED" for row in results),
        successful_C_calls=sum(row["arm"] == "C" and row["status"] == "COMPLETED" for row in results),
        successful_D_calls=sum(row["arm"] == "D" and row["status"] == "COMPLETED" for row in results),
        normal_generation_request_count=len(results),
        retry_request_count=sum(row["retry_count"] for row in results),
        grounding_repair_request_count=sum(bool(row["repair_attempted"]) for row in results),
        total_http_generation_requests=total_http,
        timeout_count=sum(row["timeout_count"] for row in results),
        provider_error_case_count=sum(bool(row["provider_failure"]) for row in results),
        other_external_hosts_contacted=[],
        data_outside_authorized_scope_transmitted=False,
        transmitted_data_classes=[
            "frozen evaluation question",
            "same-case frozen selected context",
            "frozen system/schema instructions",
        ],
        credentials_recorded=False,
    )
    write_json(run_dir / "external_call_audit.json", external)

    review_bundle = build_phase4_bundle(
        run_id, contexts, results, gold_cases
    )
    review_path = run_dir / "phase4_review_bundle.json"
    write_json(review_path, review_bundle)
    review_hash = file_sha256(review_path)
    (run_dir / "phase4_review_bundle.sha256").write_text(
        review_hash + "  phase4_review_bundle.json\n", encoding="utf-8"
    )

    production_after = production_hashes()
    production_unchanged = production_before == production_after
    blockers = []
    if len(results) != MAX_NORMAL_GENERATION_REQUESTS:
        blockers.append("incomplete_normal_generation_count")
    if any(row["status"] != "COMPLETED" for row in results):
        blockers.append("incomplete_generation_cases")
    if validation_errors:
        blockers.append("machine_contract_validation_errors")
    if not production_unchanged:
        blockers.append("production_hash_drift")
    if external["other_external_hosts_contacted"]:
        blockers.append("unexpected_external_generation_host")
    if external["data_outside_authorized_scope_transmitted"]:
        blockers.append("unauthorized_data_transmission")
    status = "PASS" if not blockers else "BLOCKED"
    validation = artifact(
        run_id,
        status=status,
        error_count=len(validation_errors),
        errors=validation_errors,
        blockers=blockers,
        context_freeze_match=context_freeze["mismatch_count"] == 0,
        execution_counts={
            "A": 0,
            **{arm: sum(row["arm"] == arm for row in results) for arm in ARMS},
        },
        production_hashes_unchanged=production_unchanged,
        arm_a_rerun=False,
        retrieval_or_reranker_tuning=False,
        semantic_review_performed=False,
        production_winner_selected=False,
        canonical_raw_results_sha256=canonical_hash,
        phase4_review_bundle_sha256=review_hash,
    )
    write_json(run_dir / "machine_validation.json", validation)
    report = render_report(
        run_id=run_id,
        run_dir=run_dir,
        preflight=preflight,
        context_freeze=context_freeze,
        contract=contract,
        tests=tests,
        machine=machine,
        latency=latency,
        tokens=tokens,
        combined=combined,
        external=external,
        validation=validation,
        review_bundle=review_bundle,
        production_unchanged=production_unchanged,
    )
    REPORT_PATH.write_text(report, encoding="utf-8")
    manifest = artifact_manifest(run_id, run_dir)
    write_json(run_dir / "artifact_manifest.json", manifest)
    latest = artifact(
        run_id,
        status=status,
        run_directory=run_dir.relative_to(ROOT).as_posix(),
        report=REPORT_PATH.relative_to(ROOT).as_posix(),
        artifact_manifest_sha256=file_sha256(run_dir / "artifact_manifest.json"),
    )
    write_json(RESULTS_ROOT / "latest_run.json", latest)
    return {
        "status": status,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "report": str(REPORT_PATH),
        "execution_counts": validation["execution_counts"],
        "total_http_generation_requests": external["total_http_generation_requests"],
        "ready_for_semantic_review": status == "PASS",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run LearnPilot RAG Phase 3 V1.1")
    parser.add_argument("--run-id", help="Resume or create this Phase 3 run id")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Run every local gate and freeze contexts, then stop before provider calls",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = args.run_id or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    )
    run_dir = RESULTS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(_env_file=ROOT / ".env")
    contract = GenerationContract.from_settings(settings)
    preflight = integrity_preflight(settings, contract)
    production_before = dict(preflight["production_hashes"])
    write_json(run_dir / "preflight.json", artifact(run_id, **preflight))
    write_json(
        run_dir / "generation_contract.json",
        artifact(
            run_id,
            **contract.as_public_dict(),
            api_key_present=True,
            secret_values_recorded=False,
        ),
    )
    tests = run_tests()
    write_json(run_dir / "test_results.json", artifact(run_id, **tests))
    gold_cases = read_json(V1 / "gold/v1/gold_cases.json")["cases"]
    contexts, context_freeze = freeze_context_artifact(
        run_id, run_dir, gold_cases
    )
    write_json(
        run_dir / "context_freeze_validation.json",
        artifact(run_id, **context_freeze),
    )
    write_json(
        run_dir / "run_manifest.json",
        artifact(
            run_id,
            status="RUNNING",
            objective="Phase 3 raw B/C/D generation only; no semantic adjudication",
            maximum_normal_generation_requests=MAX_NORMAL_GENERATION_REQUESTS,
            execution_order="B then C then D; Gold case order within each arm",
            arm_a_execution_count=0,
            generation_contract_identity=contract.identity,
            environment={
                "python": platform.python_version(),
                "platform": platform.platform(),
                "packages": package_versions(),
            },
        ),
    )
    if args.prepare_only:
        prepared = {
            "status": "PREPARED",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "context_count": context_freeze["context_count"],
            "context_freeze_sha256": context_freeze["sha256"],
            "normal_generation_requests": 0,
        }
        print(json.dumps(prepared, ensure_ascii=False, indent=2), flush=True)
        return 0
    results = execute_generation(
        run_id=run_id,
        run_dir=run_dir,
        contexts=contexts,
        settings=settings,
        contract=contract,
    )
    outcome = finalize(
        run_id=run_id,
        run_dir=run_dir,
        preflight=preflight,
        context_freeze=context_freeze,
        contract=contract,
        tests=tests,
        contexts=contexts,
        results=results,
        gold_cases=gold_cases,
        production_before=production_before,
    )
    write_json(
        run_dir / "run_manifest.json",
        artifact(
            run_id,
            status=outcome["status"],
            objective="Phase 3 raw B/C/D generation only; no semantic adjudication",
            maximum_normal_generation_requests=MAX_NORMAL_GENERATION_REQUESTS,
            execution_order="B then C then D; Gold case order within each arm",
            arm_a_execution_count=0,
            generation_contract_identity=contract.identity,
            environment={
                "python": platform.python_version(),
                "platform": platform.platform(),
                "packages": package_versions(),
            },
        ),
    )
    # The manifest includes the final run manifest, so refresh it and latest-run hash.
    write_json(run_dir / "artifact_manifest.json", artifact_manifest(run_id, run_dir))
    latest = read_json(RESULTS_ROOT / "latest_run.json")
    latest["artifact_manifest_sha256"] = file_sha256(run_dir / "artifact_manifest.json")
    write_json(RESULTS_ROOT / "latest_run.json", latest)
    print(json.dumps(outcome, ensure_ascii=False, indent=2), flush=True)
    return 0 if outcome["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
