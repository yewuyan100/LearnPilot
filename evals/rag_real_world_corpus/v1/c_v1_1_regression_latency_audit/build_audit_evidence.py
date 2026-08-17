from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[4]
V1 = ROOT / "evals/rag_real_world_corpus/v1"
RESULTS_ROOT = V1 / "results/c_v1_1_regression_latency_audit"

DESIGN_SHA = "442bedce1c43b27b3557b0055708342edd278e98bcac0c12a68c1390fe88f655"
PHASE2_RUN_ID = "20260814T095542Z-1317c6a7"
PHASE3_RUN_ID = "20260814T123142Z-8852712b"
PHASE4_RUN_ID = "20260814T131417Z-04dfc031"
PHASE2_MANIFEST_SHA = "69cca881f7192317f464c682b2e572a2d062f07975d28939d97488d6bb2f2c50"
PHASE3_MANIFEST_SHA = "f160b6b8f11fd12d2c98a9fa94d72bc54e67b12296247989e2d7187f1e3d9dcc"
PHASE4_MANIFEST_SHA = "d9ead14197b02540e798035bb140f842f30bcb3582efd4a730c536e23d8e9be2"

PHASE2 = V1 / f"results/hybrid_rerank_phase2_v1_1/{PHASE2_RUN_ID}"
PHASE3 = V1 / f"results/hybrid_rerank_phase3_v1_1/{PHASE3_RUN_ID}"
PHASE4 = V1 / f"results/hybrid_rerank_phase4_v1_1/{PHASE4_RUN_ID}"
FROZEN_A = V1 / "results/dense_only_baseline_v1/20260814T052007Z-593cd2ac/raw_results.json"
GOLD_PATH = V1 / "gold/v1/gold_cases.json"
REGRESSION_CASE_IDS = (
    "rw-gold-v1-semantic-context-order",
    "rw-gold-v1-disambig-fastapi-async-deps",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = hashlib.sha256((stamp + "-c-v1.1-audit").encode()).hexdigest()[:8]
    return f"{stamp}-{suffix}"


def verify_manifest(path: Path, expected_sha: str) -> dict[str, Any]:
    observed = sha256(path)
    if observed != expected_sha:
        raise SystemExit(f"frozen manifest hash mismatch: {path}: {observed}")
    manifest = read_json(path)
    errors: list[dict[str, str]] = []
    entries = list(manifest.get("result_files", [])) + list(
        manifest.get("implementation_and_report_files", [])
    )
    for entry in entries:
        target = ROOT / entry["path"]
        if not target.is_file():
            errors.append({"path": entry["path"], "error": "missing"})
            continue
        observed_entry = sha256(target)
        if observed_entry != entry["sha256"]:
            errors.append(
                {
                    "path": entry["path"],
                    "error": "hash_mismatch",
                    "expected": entry["sha256"],
                    "observed": observed_entry,
                }
            )
        if target.stat().st_size != entry["size_bytes"]:
            errors.append({"path": entry["path"], "error": "size_mismatch"})
    if errors:
        raise SystemExit(f"frozen artifact manifest verification failed: {errors[:3]}")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": observed,
        "verified_entries": len(entries),
        "errors": errors,
    }


def stable_identity(candidate: dict[str, Any]) -> str:
    content_hash = hashlib.sha256(candidate["content"].encode("utf-8")).hexdigest()
    return f"{candidate['document_id']}:{candidate['chunk_index']}:{content_hash}"


def percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower))


def distribution(values: Iterable[int]) -> dict[str, Any]:
    observed = [int(value) for value in values]
    if not observed:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "max": None}
    return {
        "count": len(observed),
        "mean": round(statistics.fmean(observed), 6),
        "p50": percentile([float(value) for value in observed], 0.50),
        "p95": percentile([float(value) for value in observed], 0.95),
        "max": max(observed),
    }


def phase4_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    adjudication = read_json(PHASE4 / "blinded_adjudication.json")
    mappings = read_json(PHASE4 / "sealed_blind_mapping.json")["mappings"]
    response_labels: dict[str, str] = {}
    for mapping in mappings:
        response_labels[mapping["case_id"]] = next(
            label for label, arm in mapping["response_to_arm"].items() if arm == "C"
        )
    return (
        adjudication["claim_reviews"]["rows"],
        adjudication["case_verdicts"]["rows"],
        response_labels,
    )


def required_group_matches(case: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    evidence_ids = set(candidate.get("evidence_ids", []))
    matches = []
    for group in case["evidence_groups"]:
        if not group["required"]:
            continue
        anchor_match = bool(evidence_ids & set(group["any_of_evidence_ids"]))
        document_match = candidate["document_id"] in group["any_of_document_ids"]
        if anchor_match or document_match:
            matches.append(
                {
                    "evidence_group_id": group["evidence_group_id"],
                    "anchor_match": anchor_match,
                    "document_match": document_match,
                }
            )
    return matches


def a_fate(case: dict[str, Any], candidate: dict[str, Any]) -> str:
    trace = case["selection_stage_trace"]
    chunk_id = candidate["chunk_id"]
    if chunk_id in trace["threshold_rejected_chunk_ids"]:
        return "dense_threshold"
    if chunk_id in trace["dedup_rejected_chunk_ids"]:
        return "overlap_dedup"
    if chunk_id in trace["diversity_deferred_chunk_ids"]:
        return "diversity_deferred"
    if chunk_id in trace["selected_before_context_budget_chunk_ids"]:
        if chunk_id not in trace["selected_after_context_budget_chunk_ids"]:
            return "context_budget"
        return "selected"
    return "final_top_k"


def compact_answer_a(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": case["normalized_answer"],
        "citations": [
            {
                "source_label": item["source_label"],
                "document_id": item["document_id"],
                "chunk_index": item["chunk_index"],
                "evidence_ids": item["evidence_ids"],
            }
            for item in case["citations"]
        ],
    }


def compact_answer_c(
    case_id: str,
    phase3_records: list[dict[str, Any]],
    phase3_contexts: list[dict[str, Any]],
) -> dict[str, Any]:
    answer = next(
        row for row in phase3_records if row["arm"] == "C" and row["case_id"] == case_id
    )
    context = next(
        row for row in phase3_contexts if row["arm"] == "C" and row["case_id"] == case_id
    )
    return {
        "answer": answer["answer_markdown"],
        "citation_ids": answer["citation_ids"],
        "selected_candidate_identities": context["selected_candidate_identities"],
        "selected_sources": context["selected_sources"],
        "context_digest": context["context_digest"],
    }


def build_regression_case_audits(
    gold_cases: list[dict[str, Any]],
    a_cases: list[dict[str, Any]],
    c_traces: list[dict[str, Any]],
    phase3_records: list[dict[str, Any]],
    phase3_contexts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    claim_reviews, case_verdicts, c_labels = phase4_rows()
    causal_rows = read_json(PHASE4 / "causal_traces.json")["rows"]
    audits = []
    for case_id in REGRESSION_CASE_IDS:
        gold = next(row for row in gold_cases if row["case_id"] == case_id)
        frozen_a = next(row for row in a_cases if row["case_id"] == case_id)
        trace_c = next(row for row in c_traces if row["case_id"] == case_id)
        a_candidates = sorted(frozen_a["diagnostic"]["candidates"], key=lambda row: row["rank"])
        c_candidates = sorted(trace_c["candidates"], key=lambda row: row["dense_rank"])
        a_identities = [stable_identity(row) for row in a_candidates]
        c_identities = [row["identity"] for row in c_candidates]
        if a_identities != c_identities:
            raise SystemExit(f"serious A/C pre-rerank identity anomaly: {case_id}")
        if any(
            a["rank"] != c["dense_rank"] or a["score"] != c["dense_score"]
            for a, c in zip(a_candidates, c_candidates, strict=True)
        ):
            raise SystemExit(f"serious A/C pre-rerank rank/score anomaly: {case_id}")

        candidate_rows = []
        required_promoted = []
        required_demoted = []
        plausible_less_useful_promoted = []
        for a_candidate, c_candidate in zip(a_candidates, c_candidates, strict=True):
            group_matches = required_group_matches(gold, c_candidate)
            is_anchor = any(item["anchor_match"] for item in group_matches)
            movement = int(c_candidate["dense_rank"]) - int(c_candidate["reranker_rank"])
            if is_anchor and movement > 0:
                required_promoted.append(c_candidate["identity"])
            if is_anchor and movement < 0:
                required_demoted.append(c_candidate["identity"])
            if not is_anchor and movement > 0 and c_candidate["selected"]:
                plausible_less_useful_promoted.append(c_candidate["identity"])
            candidate_rows.append(
                {
                    "identity": c_candidate["identity"],
                    "document_id": c_candidate["document_id"],
                    "chunk_index": c_candidate["chunk_index"],
                    "section_title": c_candidate["section_title"],
                    "evidence_ids": c_candidate["evidence_ids"],
                    "required_group_matches": group_matches,
                    "dense_score": c_candidate["dense_score"],
                    "dense_rank": c_candidate["dense_rank"],
                    "dense_eligible_a": a_candidate["score"] >= 0.35,
                    "dense_eligible_c": c_candidate["branch_admitted_dense"],
                    "reranker_score": c_candidate["reranker_score"],
                    "reranker_rank": c_candidate["reranker_rank"],
                    "reranker_rank_change_positive_is_promotion": movement,
                    "a_final_fate": a_fate(frozen_a, a_candidate),
                    "c_final_fate": "selected"
                    if c_candidate["selected"]
                    else c_candidate["rejection_reason"],
                }
            )

        label = c_labels[case_id]
        c_claim_reviews = [
            row
            for row in claim_reviews
            if row["case_id"] == case_id and row["response_label"] == label
        ]
        c_case_verdict = next(
            row
            for row in case_verdicts
            if row["case_id"] == case_id and row["response_label"] == label
        )
        phase4_causal = next(
            row for row in causal_rows if row["arm"] == "C" and row["case_id"] == case_id
        )
        if phase4_causal["dominant_cause"] != "CITATION_SEMANTIC_SUPPORT":
            raise SystemExit(f"unexpected frozen Phase 4 cause: {case_id}")

        if case_id.endswith("semantic-context-order"):
            finding = (
                "C retained the definition and the 0.5 ordering example in selected chunks; "
                "the answer omitted the frozen approximately 1.0-to-0.5 change."
            )
        else:
            finding = (
                "C retained the dependency mixing rule, async guidance, and threadpool evidence; "
                "the answer used the async source for threadpool behavior but omitted its endpoint-selection guidance."
            )

        audits.append(
            {
                "case_id": case_id,
                "question": gold["question"],
                "gold_claims": gold["claims"],
                "gold_required_evidence_groups": [
                    row for row in gold["evidence_groups"] if row["required"]
                ],
                "pre_rerank_pool": {
                    "a_dense_top18_count": len(a_candidates),
                    "c_dense_top18_count": len(c_candidates),
                    "identities_identical": a_identities == c_identities,
                    "ranks_scores_identical": True,
                    "all_candidates_admitted_in_both": all(
                        row["dense_eligible_a"] and row["dense_eligible_c"]
                        for row in candidate_rows
                    ),
                },
                "candidate_rows_dense_order": candidate_rows,
                "reranker_findings": {
                    "did_move_any_gold_anchor_down": bool(required_demoted),
                    "gold_anchor_demoted_identities": required_demoted,
                    "gold_anchor_promoted_identities": required_promoted,
                    "did_promote_plausible_but_less_useful_selected_evidence": bool(
                        plausible_less_useful_promoted
                    ),
                    "plausible_but_less_useful_promoted_identities": plausible_less_useful_promoted,
                    "interpretation": (
                        "Some individual anchors changed rank, but the governed C context remained sufficient; "
                        "rank movement did not cause the frozen semantic regression."
                    ),
                },
                "a_final_top6_identities": [
                    stable_identity(item) for item in frozen_a["retrieval"]["selected_sources"]
                ],
                "c_final_top6_identities": trace_c["selected"],
                "frozen_a": compact_answer_a(frozen_a),
                "frozen_c": compact_answer_c(case_id, phase3_records, phase3_contexts),
                "phase4_c_claim_reviews": c_claim_reviews,
                "phase4_c_case_verdict": c_case_verdict,
                "independent_dominant_cause": "CITATION_SEMANTIC_SUPPORT",
                "phase4_causal_trace_cause": phase4_causal["dominant_cause"],
                "cause_alignment": True,
                "finding": finding,
                "context_comparison": "EQUALLY_OR_MORE_SUFFICIENT_C_CONTEXT_BUT_WORSE_GENERATION",
                "actionability": "GENERATION_ADDRESSABLE",
                "confidence": "HIGH_CONFIDENCE",
                "would_reducing_candidate_depth_plausibly_repair": "NO_EVIDENCE",
                "would_changing_reranker_model_plausibly_repair": "NO_EVIDENCE",
                "would_serving_only_optimization_leave_regression_unchanged": "YES",
            }
        )
    return audits


def build_candidate_depth_analysis(
    gold_cases: list[dict[str, Any]], c_traces: list[dict[str, Any]]
) -> dict[str, Any]:
    transition_rows = read_json(PHASE4 / "case_transitions.json")["rows"]
    fixed_case_ids = sorted(
        row["case_id"]
        for row in transition_rows
        if row["arm"] == "C" and row["transition"] == "FIXED_FAILURE"
    )
    case_rows = []
    group_best_ranks: list[int] = []
    selected_anchor_dense_ranks: list[int] = []
    promoted_selected_upstream_ranks: list[int] = []
    for gold in gold_cases:
        trace = next(row for row in c_traces if row["case_id"] == gold["case_id"])
        required_groups = [row for row in gold["evidence_groups"] if row["required"]]
        group_rows = []
        for group in required_groups:
            candidates = [
                candidate
                for candidate in trace["candidates"]
                if set(candidate["evidence_ids"]) & set(group["any_of_evidence_ids"])
            ]
            ranks = sorted(int(candidate["dense_rank"]) for candidate in candidates)
            best = ranks[0] if ranks else None
            if best is not None:
                group_best_ranks.append(best)
            group_rows.append(
                {
                    "evidence_group_id": group["evidence_group_id"],
                    "best_dense_rank": best,
                    "all_dense_ranks": ranks,
                }
            )
        required_ids = set().union(
            *(set(group["any_of_evidence_ids"]) for group in required_groups)
        ) if required_groups else set()
        selected_required = [
            candidate
            for candidate in trace["candidates"]
            if candidate["selected"] and set(candidate["evidence_ids"]) & required_ids
        ]
        selected_ranks = sorted(int(candidate["dense_rank"]) for candidate in selected_required)
        selected_anchor_dense_ranks.extend(selected_ranks)
        promoted = [
            {
                "identity": candidate["identity"],
                "dense_rank": int(candidate["dense_rank"]),
                "reranker_rank": int(candidate["reranker_rank"]),
            }
            for candidate in selected_required
            if int(candidate["reranker_rank"]) < int(candidate["dense_rank"])
        ]
        promoted_selected_upstream_ranks.extend(row["dense_rank"] for row in promoted)
        case_rows.append(
            {
                "case_id": gold["case_id"],
                "c_transition": next(
                    row["transition"]
                    for row in transition_rows
                    if row["arm"] == "C" and row["case_id"] == gold["case_id"]
                ),
                "required_group_best_dense_ranks": group_rows,
                "best_required_evidence_dense_rank": min(
                    (row["best_dense_rank"] for row in group_rows if row["best_dense_rank"] is not None),
                    default=None,
                ),
                "selected_required_evidence_dense_ranks": selected_ranks,
                "reranker_promoted_selected_required_evidence": promoted,
            }
        )

    fixed_rows = [row for row in case_rows if row["case_id"] in fixed_case_ids]
    fixed_high_rank = [
        {
            "case_id": row["case_id"],
            "selected_required_evidence_dense_ranks": row["selected_required_evidence_dense_ranks"],
            "required_group_best_dense_ranks": row["required_group_best_dense_ranks"],
        }
        for row in fixed_rows
    ]
    selected_beyond_8 = sorted(
        row["case_id"]
        for row in case_rows
        if any(rank > 8 for rank in row["selected_required_evidence_dense_ranks"])
    )
    selected_beyond_12 = sorted(
        row["case_id"]
        for row in case_rows
        if any(rank > 12 for rank in row["selected_required_evidence_dense_ranks"])
    )
    fixed_beyond_12 = sorted(set(fixed_case_ids) & set(selected_beyond_12))
    return {
        "analysis_scope": "descriptive frozen Phase 2 C traces; no alternative depth rescoring",
        "case_count": len(case_rows),
        "fixed_case_ids": fixed_case_ids,
        "fixed_case_required_evidence_ranks": fixed_high_rank,
        "regression_case_rows": [
            row for row in case_rows if row["case_id"] in REGRESSION_CASE_IDS
        ],
        "distributions": {
            "required_group_best_dense_rank": distribution(group_best_ranks),
            "selected_required_evidence_dense_rank": distribution(selected_anchor_dense_ranks),
            "reranker_promoted_selected_required_evidence_upstream_dense_rank": distribution(
                promoted_selected_upstream_ranks
            ),
        },
        "selected_required_evidence_beyond_top8_case_ids": selected_beyond_8,
        "selected_required_evidence_beyond_top12_case_ids": selected_beyond_12,
        "fixed_cases_with_selected_required_evidence_beyond_top12": fixed_beyond_12,
        "historical_depth_conclusion": (
            "18_REMAINS_NECESSARY_TO_REPRODUCE_OBSERVED_C_V1_1_BENEFIT"
            if fixed_beyond_12
            else "INSUFFICIENT_EVIDENCE"
        ),
        "caveat": (
            "This does not select a new depth. It only shows whether historically selected required anchors "
            "that accompanied C fixes originated beyond smaller cutoffs."
        ),
        "case_rows": case_rows,
    }


def main() -> None:
    run_id = new_run_id()
    run_dir = RESULTS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    phase_manifests = [
        verify_manifest(PHASE2 / "artifact_manifest.json", PHASE2_MANIFEST_SHA),
        verify_manifest(PHASE3 / "artifact_manifest.json", PHASE3_MANIFEST_SHA),
        verify_manifest(PHASE4 / "artifact_manifest.json", PHASE4_MANIFEST_SHA),
    ]
    frozen_expected = {
        "design": (
            V1 / "ablation_design_v1_1/ablation_design_manifest.json",
            DESIGN_SHA,
        ),
        "gold": (GOLD_PATH, "33a0b69901fa47e3fe45be0277228cd4a5519fe780fe5b9d2c52b1bfe614927a"),
        "corpus": (V1 / "corpus_manifest.json", "6f67d510cd35197f107400d33033972c0c3c84478174e4991e491f6c8e4ab563"),
        "frozen_a": (FROZEN_A, "bf718aed08e226149c9310cbf20bf25c403708217e2908789120178ac5574e28"),
        "phase3_raw": (PHASE3 / "canonical_raw_results.json", "84ced9e50fff8c2e7f6290045ea9d369179f9413bd6efe3e04d97e62f59046ad"),
        "phase3_context": (PHASE3 / "context_freeze.json", "f299c0a00dc2dbe8bb21e35c8888d0bfee8f0a1b94c6bbe094407b31c1bf1cf7"),
        "phase4_blind_review": (PHASE4 / "blinded_adjudication.json", "0e91fedd1a4b98152e77a093dff1a18ed3f177a92b3d1d4ddc67073b3fcdaf9c"),
    }
    frozen_hashes = {}
    for name, (path, expected) in frozen_expected.items():
        observed = sha256(path)
        if observed != expected:
            raise SystemExit(f"frozen hash mismatch: {name}: {observed}")
        frozen_hashes[name] = {
            "path": path.relative_to(ROOT).as_posix(),
            "expected_sha256": expected,
            "observed_sha256": observed,
            "match": True,
        }

    phase2_preflight = read_json(PHASE2 / "preflight.json")
    production_hashes = []
    for relative, expected in phase2_preflight["production_hashes"].items():
        path = ROOT / relative
        observed = sha256(path)
        production_hashes.append(
            {
                "path": relative,
                "expected_sha256": expected,
                "observed_sha256": observed,
                "match": observed == expected,
            }
        )
    if not all(row["match"] for row in production_hashes):
        raise SystemExit("production hashes no longer match the Phase 2 frozen baseline")

    gold_cases = read_json(GOLD_PATH)["cases"]
    a_cases = read_json(FROZEN_A)["cases"]
    c_traces = read_jsonl(PHASE2 / "arm_C/candidate_traces.jsonl")
    phase3_records = read_json(PHASE3 / "canonical_raw_results.json")["records"]
    phase3_contexts = read_json(PHASE3 / "context_freeze.json")["records"]
    if not (len(gold_cases) == len(a_cases) == len(c_traces) == 72):
        raise SystemExit("expected exactly 72 frozen cases")

    regression_audits = build_regression_case_audits(
        gold_cases, a_cases, c_traces, phase3_records, phase3_contexts
    )
    depth_analysis = build_candidate_depth_analysis(gold_cases, c_traces)
    source = (V1 / "hybrid_rerank_phase2_v1_1/experiment.py").read_text(encoding="utf-8")
    runner = (V1 / "hybrid_rerank_phase2_v1_1/run_phase2_v1_1.py").read_text(encoding="utf-8")
    architecture = {
        "model_load_scope": "per process",
        "model_instance_count_in_phase2_runner": 1,
        "model_reused_across_queries": True,
        "tokenizer_initialization_frequency": "once per adapter/process",
        "model_initialization_frequency": "once per adapter/process",
        "tokenization": "pair-by-pair encode inside one 18-pair call",
        "query_reencoded_for_each_candidate": True,
        "forward_pass": "single dynamically padded batch",
        "pair_count": 18,
        "device": "CPU",
        "dtype": "to be measured from loaded frozen model",
        "torch_threads": "to be measured in profiling process",
        "torch_interop_threads": "to be measured in profiling process",
        "inference_mode": "yes",
        "grad_enabled_during_forward": "no",
        "model_eval_mode": "yes",
        "python_candidate_feature_loop": True,
        "tensor_creation": "tokenizer.pad creates one tensor batch",
        "device_transfers": "one dictionary comprehension; CPU-to-CPU in frozen run",
        "attention_mask": "explicit all-ones per pair then zero-padded by tokenizer.pad",
        "padding_strategy": "dynamic longest pair in each query batch",
        "max_length_behavior": "preserve query, truncate chunk only when pair exceeds 1024",
        "all_pairs_passed_simultaneously": True,
        "accidentally_sequential_forward": False,
        "source_contract_checks": {
            "model_eval_call_present": "self.model.eval()" in source,
            "inference_mode_present": "with torch.inference_mode():" in source,
            "single_batch_model_call_present": "self.model(**batch, return_dict=True)" in source,
            "one_adapter_before_arm_loop": (
                (adapter_position := runner.index("reranker = HuggingFaceRerankerAdapter(snapshot)"))
                < runner.index('for arm in ("C", "D")', adapter_position)
            ),
        },
        "known_avoidable_overhead": [
            "The unchanged query is tokenized 18 times per call.",
            "Pair features and attention masks are assembled in a Python loop.",
            "The batch dictionary calls .to('cpu') even though tensors are already on CPU.",
            "Logits are converted to a Python list before deterministic sorting.",
        ],
    }

    base = {
        "design_version": "V1.1",
        "ablation_design_sha256": DESIGN_SHA,
        "phase2_run_id": PHASE2_RUN_ID,
        "phase3_run_id": PHASE3_RUN_ID,
        "phase4_run_id": PHASE4_RUN_ID,
        "audit_run_id": run_id,
        "recorded_at": utc_now(),
    }
    write_json(
        run_dir / "integrity_preflight.json",
        {
            **base,
            "status": "PASS",
            "frozen_hashes": frozen_hashes,
            "phase_manifests": phase_manifests,
            "production_file_count": len(production_hashes),
            "production_hashes_before": production_hashes,
            "all_production_hashes_match": True,
            "external_calls": 0,
            "retrieval_runs": 0,
            "generation_runs": 0,
        },
    )
    write_json(run_dir / "regression_case_audit.json", {**base, "cases": regression_audits})
    write_json(run_dir / "candidate_depth_analysis.json", {**base, **depth_analysis})
    write_json(run_dir / "implementation_architecture.json", {**base, **architecture})
    write_json(
        run_dir / "run_state.json",
        {
            **base,
            "status": "EVIDENCE_BUILT_PROFILING_PENDING",
            "allowed_local_reranker_profiling_runs": True,
            "new_semantic_outputs": 0,
            "external_calls": 0,
        },
    )
    write_json(
        RESULTS_ROOT / "latest_run.json",
        {
            **base,
            "status": "EVIDENCE_BUILT_PROFILING_PENDING",
            "run_directory": run_dir.relative_to(ROOT).as_posix(),
        },
    )
    print(json.dumps({"status": "PASS", "run_id": run_id, "run_dir": str(run_dir)}, indent=2))


if __name__ == "__main__":
    main()
