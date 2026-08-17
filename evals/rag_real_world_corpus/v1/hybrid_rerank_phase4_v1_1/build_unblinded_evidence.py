from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
V1 = HERE.parent
ROOT = V1.parents[2]
RUN_ID = "20260814T131417Z-04dfc031"
RUN_DIR = V1 / f"results/hybrid_rerank_phase4_v1_1/{RUN_ID}"
PHASE2_RUN_ID = "20260814T095542Z-1317c6a7"
PHASE3_RUN_ID = "20260814T123142Z-8852712b"
PHASE2_DIR = V1 / f"results/hybrid_rerank_phase2_v1_1/{PHASE2_RUN_ID}"
PHASE3_DIR = V1 / f"results/hybrid_rerank_phase3_v1_1/{PHASE3_RUN_ID}"
FROZEN_A_PATH = V1 / "results/dense_only_baseline_v1/20260814T052007Z-593cd2ac/raw_results.json"
DESIGN_SHA256 = "442bedce1c43b27b3557b0055708342edd278e98bcac0c12a68c1390fe88f655"
PASS1_SHA256 = "0e91fedd1a4b98152e77a093dff1a18ed3f177a92b3d1d4ddc67073b3fcdaf9c"
ARMS = ("A", "B", "C", "D")
EXPERIMENTAL_ARMS = ("B", "C", "D")
PASS_VERDICTS = {"FULL_PASS", "CORRECT_REFUSAL"}
INVALID_CITATIONS = {"VALID_ID_BUT_WEAK_SUPPORT", "MISSING_REQUIRED_CITATION", "MISATTRIBUTED_SUPPORT"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def write_json(path: Path, value: Any) -> None:
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


def rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def group_coverage(gold: dict[str, Any], sources: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(sources)
    documents = {row.get("document_id") for row in rows if row.get("document_id")}
    evidence = {value for row in rows for value in row.get("evidence_ids", [])}
    groups = []
    for group in gold["acceptable_evidence_groups"]:
        if not group["required"]:
            continue
        document_match = bool(documents.intersection(group.get("any_of_document_ids", [])))
        evidence_match = bool(evidence.intersection(group.get("any_of_evidence_ids", [])))
        groups.append(
            {
                "evidence_group_id": group["evidence_group_id"],
                "document_match": document_match,
                "evidence_anchor_match": evidence_match,
                "covered": document_match or evidence_match,
            }
        )
    return {
        "required_group_count": len(groups),
        "document_groups_covered": sum(row["document_match"] for row in groups),
        "anchor_groups_covered": sum(row["evidence_anchor_match"] for row in groups),
        "document_complete": all(row["document_match"] for row in groups),
        "anchor_complete": all(row["evidence_anchor_match"] for row in groups),
        "complete": all(row["evidence_anchor_match"] for row in groups),
        "complete_definition": "frozen claim-required evidence anchor coverage",
        "groups": groups,
    }


def summarize_arm(arm: str, claim_rows: list[dict[str, Any]], verdict_rows: list[dict[str, Any]]) -> dict[str, Any]:
    claims = [row for row in claim_rows if row["arm"] == arm]
    verdicts = [row for row in verdict_rows if row["arm"] == arm]
    states = Counter(row["semantic_state"] for row in claims)
    applicable_citations = [row for row in claims if row["citation_semantic_status"] != "NOT_APPLICABLE_REFUSAL"]
    citation_states = Counter(row["citation_semantic_status"] for row in claims)
    case_counts = Counter(row["case_verdict"] for row in verdicts)
    class_counts = Counter(row["answerability_class"] for row in verdicts)
    expected_coverage = sum(
        row["expected_evidence_group_coverage"]["all_covered"]
        for row in applicable_citations
    )
    fully_correct_cases = case_counts["FULL_PASS"] + case_counts["CORRECT_REFUSAL"]
    return {
        "arm": arm,
        "frozen_claim_count": len(claims),
        "reviewed_correctness": {"count": states["SUPPORTED_CORRECT"], "rate": rate(states["SUPPORTED_CORRECT"], len(claims))},
        "required_claim_coverage": {
            "count": states["SUPPORTED_CORRECT"] + states["SUPPORTED_BUT_INCOMPLETE"],
            "rate": rate(states["SUPPORTED_CORRECT"] + states["SUPPORTED_BUT_INCOMPLETE"], len(claims)),
            "definition": "SUPPORTED_CORRECT or SUPPORTED_BUT_INCOMPLETE; not an Overall Accuracy redefinition",
        },
        "semantic_state_counts": dict(sorted(states.items())),
        "unsupported_claim_count": states["UNSUPPORTED"],
        "contradicted_claim_count": states["CONTRADICTED"],
        "semantic_citation_support": {
            "applicable_claim_count": len(applicable_citations),
            "valid_id_and_support_count": citation_states["VALID_ID_AND_SUPPORT"],
            "valid_id_and_support_rate": rate(citation_states["VALID_ID_AND_SUPPORT"], len(applicable_citations)),
            "status_counts": dict(sorted(citation_states.items())),
        },
        "expected_evidence_group_support": {
            "complete_claim_count": expected_coverage,
            "applicable_claim_count": len(applicable_citations),
            "rate": rate(expected_coverage, len(applicable_citations)),
        },
        "case_count": len(verdicts),
        "case_verdict_counts": dict(sorted(case_counts.items())),
        "answerability_class_counts": dict(sorted(class_counts.items())),
        "fully_correct_case_count": fully_correct_cases,
        "fully_correct_case_rate": rate(fully_correct_cases, len(verdicts)),
        "answerability_accuracy": {
            "count": sum(row["gold_answerability"] == row["response_answerable"] for row in verdicts),
            "rate": rate(sum(row["gold_answerability"] == row["response_answerable"] for row in verdicts), len(verdicts)),
            "correct_refusal": class_counts["CORRECT_REFUSAL"],
            "incorrect_refusal": class_counts["INCORRECT_REFUSAL"],
        },
        "overall_accuracy": None,
        "overall_accuracy_note": "No single Overall Accuracy decision metric is defined in the frozen V1.1 design; fully-correct case rate is reported separately.",
    }


def breakdowns(
    arm: str,
    verdict_rows: list[dict[str, Any]],
    gold_by_id: dict[str, dict[str, Any]],
    failure_by_id: dict[str, dict[str, Any]],
    target_membership: dict[str, list[str]],
) -> dict[str, Any]:
    rows = [row for row in verdict_rows if row["arm"] == arm]
    dimensions: dict[str, dict[str, list[dict[str, Any]]]] = {
        "tier": {}, "case_type": {}, "query_language": {}, "frozen_failure_class": {}, "target_group": {}
    }
    for row in rows:
        case_id = row["case_id"]
        values = {
            "tier": [gold_by_id[case_id]["tier"]],
            "case_type": [gold_by_id[case_id]["case_type"]],
            "query_language": [gold_by_id[case_id]["query_language"]],
            "frozen_failure_class": [failure_by_id[case_id]["primary_root_cause"]],
            "target_group": target_membership.get(case_id) or ["NONE"],
        }
        for dimension, names in values.items():
            for name in names:
                dimensions[dimension].setdefault(name, []).append(row)
    result = {}
    for dimension, groups in dimensions.items():
        result[dimension] = {}
        for name, items in sorted(groups.items()):
            counts = Counter(item["case_verdict"] for item in items)
            result[dimension][name] = {
                "case_count": len(items),
                "case_verdict_counts": dict(sorted(counts.items())),
                "fully_correct_count": sum(value in PASS_VERDICTS for value in (item["case_verdict"] for item in items)),
            }
    return result


def transition(a: dict[str, Any], other: dict[str, Any]) -> str:
    a_pass = a["case_verdict"] in PASS_VERDICTS
    other_pass = other["case_verdict"] in PASS_VERDICTS
    if not a_pass and other_pass:
        return "FIXED_FAILURE"
    if not a_pass and not other_pass:
        return "UNCHANGED_FAILURE"
    if a_pass and not other_pass:
        return "NEW_REGRESSION"
    return "UNCHANGED_PASS"


def candidate_rows_for_a(case: dict[str, Any]) -> list[dict[str, Any]]:
    return case["diagnostic"]["candidates"]


def trace_sources(trace: dict[str, Any], selected: bool) -> list[dict[str, Any]]:
    return [row for row in trace["candidates"] if bool(row.get("selected")) == selected] if selected else trace["candidates"]


def admitted_candidates(trace: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in trace["candidates"] if row.get("governance_input_rank") is not None]


def compact_source(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "identity": row.get("identity") or row.get("chunk_id"),
        "document_id": row.get("document_id"),
        "chunk_index": row.get("chunk_index"),
        "evidence_ids": row.get("evidence_ids", []),
        "dense_rank": row.get("dense_rank"),
        "bm25_rank": row.get("bm25_rank"),
        "fusion_rank": row.get("fusion_rank"),
        "reranker_rank": row.get("reranker_rank"),
        "selected": row.get("selected"),
        "rejection_reason": row.get("rejection_reason"),
    }


def dominant_cause(
    transition_name: str,
    arm: str,
    case_id: str,
    a_candidate: dict[str, Any],
    a_selected: dict[str, Any],
    arm_candidate: dict[str, Any],
    arm_selected: dict[str, Any],
    arm_verdict: dict[str, Any],
    claim_rows: list[dict[str, Any]],
    design_targets: dict[str, Any],
) -> str:
    if transition_name == "FIXED_FAILURE":
        if not a_candidate["complete"] and arm_candidate["complete"]:
            return "RETRIEVAL"
        if not a_selected["complete"] and arm_selected["complete"]:
            if case_id in design_targets["reranker_diversity_miss"]:
                return "SELECTION_DIVERSITY"
            return "RANKING"
        return "GENERATION"
    if a_candidate["complete"] and not arm_candidate["complete"]:
        return "RETRIEVAL"
    if a_selected["complete"] and not arm_selected["complete"]:
        if case_id in design_targets["reranker_diversity_miss"]:
            return "SELECTION_DIVERSITY"
        return "RANKING" if arm in {"C", "D"} else "CONTEXT_BUDGET"
    if arm_verdict["answerability_class"] in {"INCORRECT_REFUSAL", "INCORRECT_ANSWER"}:
        return "ANSWERABILITY"
    rows = [row for row in claim_rows if row["arm"] == arm and row["case_id"] == case_id]
    if any(row["citation_semantic_status"] in INVALID_CITATIONS for row in rows):
        return "CITATION_SEMANTIC_SUPPORT"
    return "GENERATION"


def main() -> int:
    if file_sha256(RUN_DIR / "blinded_adjudication.json") != PASS1_SHA256:
        raise SystemExit("Pass-1 adjudication drift; refusing unblind")
    pass1_freeze = read_json(RUN_DIR / "pass1_freeze.json")
    if not pass1_freeze["frozen_before_unblinding"]:
        raise SystemExit("Pass-1 was not frozen before unblinding")
    mapping_payload = read_json(RUN_DIR / "sealed_blind_mapping.json")
    mapping = {
        (row["case_id"], label): arm
        for row in mapping_payload["mappings"]
        for label, arm in row["response_to_arm"].items()
    }
    if len(mapping) != 288:
        raise SystemExit("sealed mapping cardinality mismatch")
    blind_claims = read_json(RUN_DIR / "blinded_claim_reviews.json")["rows"]
    blind_verdicts = read_json(RUN_DIR / "blinded_case_verdicts.json")["rows"]
    claim_rows = [{**row, "arm": mapping[(row["case_id"], row["response_label"])]} for row in blind_claims]
    verdict_rows = [{**row, "arm": mapping[(row["case_id"], row["response_label"])]} for row in blind_verdicts]
    verdict_by_key = {(row["arm"], row["case_id"]): row for row in verdict_rows}
    claim_by_key = {(row["arm"], row["case_id"], row["claim_id"]): row for row in claim_rows}
    blind_input = read_json(RUN_DIR / "blinded_review_input.json")
    blind_case_by_id = {row["case_id"]: row for row in blind_input["cases"]}
    gold = read_json(V1 / "gold/v1/gold_cases.json")["cases"]
    gold_by_id = {row["case_id"]: row for row in gold}
    failure = read_json(V1 / "failure_analysis_v1/case_failure_analysis.json")["cases"]
    failure_by_id = {row["case_id"]: row for row in failure}
    design = read_json(V1 / "ablation_design_v1_1/ablation_design_manifest.json")
    targets = design["target_case_sets"]
    target_membership: dict[str, list[str]] = {}
    for name in ("hybrid", "dense_rerank", "reranker_ranking_miss", "reranker_diversity_miss", "hybrid_rerank"):
        for case_id in targets[name]:
            target_membership.setdefault(case_id, []).append(name)

    summaries = {arm: summarize_arm(arm, claim_rows, verdict_rows) for arm in ARMS}
    metrics = metadata(
        blinded_review_sha256=PASS1_SHA256,
        unblinded_after_pass1_freeze=True,
        post_unblind_review_corrections=[],
        arms=summaries,
        breakdowns={arm: breakdowns(arm, verdict_rows, gold_by_id, failure_by_id, target_membership) for arm in ARMS},
    )
    write_json(RUN_DIR / "unblinded_metrics.json", metrics)
    write_json(
        RUN_DIR / "unblinding_record.json",
        metadata(
            status="PASS",
            pass1_sha256_verified=PASS1_SHA256,
            mapping_sha256=file_sha256(RUN_DIR / "sealed_blind_mapping.json"),
            mapping_entries=len(mapping),
            unblinded_claim_rows=len(claim_rows),
            unblinded_verdict_rows=len(verdict_rows),
            post_unblind_review_corrections=[],
        ),
    )

    transition_rows = []
    for arm in EXPERIMENTAL_ARMS:
        for case_id in gold_by_id:
            a = verdict_by_key[("A", case_id)]
            other = verdict_by_key[(arm, case_id)]
            name = transition(a, other)
            transition_rows.append(
                {
                    "arm": arm,
                    "case_id": case_id,
                    "transition": name,
                    "a_case_verdict": a["case_verdict"],
                    "arm_case_verdict": other["case_verdict"],
                    "a_answerability_class": a["answerability_class"],
                    "arm_answerability_class": other["answerability_class"],
                    "causal_note_required": name in {"FIXED_FAILURE", "NEW_REGRESSION"},
                }
            )
    transition_summary = {}
    for arm in EXPERIMENTAL_ARMS:
        rows = [row for row in transition_rows if row["arm"] == arm]
        counts = Counter(row["transition"] for row in rows)
        transition_summary[arm] = {
            "counts": {name: counts[name] for name in ("FIXED_FAILURE", "UNCHANGED_FAILURE", "NEW_REGRESSION", "UNCHANGED_PASS")},
            "case_ids": {name: [row["case_id"] for row in rows if row["transition"] == name] for name in ("FIXED_FAILURE", "UNCHANGED_FAILURE", "NEW_REGRESSION", "UNCHANGED_PASS")},
        }
    write_json(RUN_DIR / "case_transitions.json", metadata(summary=transition_summary, rows=transition_rows))

    frozen_a = read_json(FROZEN_A_PATH)
    a_raw_by_id = {row["case_id"]: row for row in frozen_a["cases"]}
    traces = {
        arm: {row["case_id"]: row for row in read_jsonl(PHASE2_DIR / f"arm_{arm}/candidate_traces.jsonl")}
        for arm in EXPERIMENTAL_ARMS
    }
    phase3_bundle = read_json(PHASE3_DIR / "phase4_review_bundle.json")
    bundle_by_id = {row["case_id"]: row for row in phase3_bundle["cases"]}

    coverage: dict[tuple[str, str, str], dict[str, Any]] = {}
    for case_id, blind_case in blind_case_by_id.items():
        coverage[("A", case_id, "candidate")] = group_coverage(blind_case["Gold"], candidate_rows_for_a(a_raw_by_id[case_id]))
        coverage[("A", case_id, "selected")] = group_coverage(blind_case["Gold"], a_raw_by_id[case_id]["retrieval"]["selected_sources"])
        for arm in EXPERIMENTAL_ARMS:
            trace = traces[arm][case_id]
            coverage[(arm, case_id, "candidate")] = group_coverage(blind_case["Gold"], admitted_candidates(trace))
            coverage[(arm, case_id, "selected")] = group_coverage(blind_case["Gold"], [row for row in trace["candidates"] if row.get("selected")])

    hybrid_rows = []
    for case_id in targets["hybrid"]:
        a_candidate = coverage[("A", case_id, "candidate")]
        b_candidate = coverage[("B", case_id, "candidate")]
        a_selected = coverage[("A", case_id, "selected")]
        b_selected = coverage[("B", case_id, "selected")]
        a_verdict = verdict_by_key[("A", case_id)]
        b_verdict = verdict_by_key[("B", case_id)]
        if not a_candidate["complete"] and b_candidate["complete"]:
            mechanism = "retrieval fixed + generation fixed" if b_verdict["case_verdict"] in PASS_VERDICTS else "retrieval fixed + generation still failed"
        elif a_candidate["complete"] and not b_candidate["complete"]:
            mechanism = "retrieval regressed"
        else:
            mechanism = "retrieval unchanged"
        hybrid_rows.append(
            {
                "case_id": case_id,
                "a_candidate_coverage": a_candidate,
                "b_candidate_coverage": b_candidate,
                "a_selected_coverage": a_selected,
                "b_selected_coverage": b_selected,
                "a_candidate_evidence": [compact_source(row) for row in candidate_rows_for_a(a_raw_by_id[case_id])],
                "b_candidate_evidence": [compact_source(row) for row in admitted_candidates(traces["B"][case_id])],
                "a_selected_evidence": bundle_by_id[case_id]["frozen_A"]["selected_candidate_identities"],
                "b_selected_evidence": [row["identity"] for row in traces["B"][case_id]["candidates"] if row.get("selected")],
                "a_final_answer": bundle_by_id[case_id]["frozen_A"]["answer"],
                "b_final_answer": bundle_by_id[case_id]["B"]["answer"],
                "a_case_verdict": a_verdict["case_verdict"],
                "b_case_verdict": b_verdict["case_verdict"],
                "required_claims_recovered": a_verdict["case_verdict"] not in PASS_VERDICTS and b_verdict["case_verdict"] in PASS_VERDICTS,
                "citation_support_recovered": not a_verdict["has_invalid_semantic_citation_support"] and not b_verdict["has_invalid_semantic_citation_support"],
                "case_fixed": transition(a_verdict, b_verdict) == "FIXED_FAILURE",
                "downstream_mechanism": mechanism,
            }
        )

    reranker_rows = []
    for arm in ("C", "D"):
        for case_id in targets["dense_rerank"]:
            subgroup = "SELECTION_RANKING_MISS" if case_id in targets["reranker_ranking_miss"] else "SELECTION_DIVERSITY_MISS"
            a_candidate = coverage[("A", case_id, "candidate")]
            a_selected = coverage[("A", case_id, "selected")]
            arm_candidate = coverage[(arm, case_id, "candidate")]
            arm_selected = coverage[(arm, case_id, "selected")]
            a_verdict = verdict_by_key[("A", case_id)]
            arm_verdict = verdict_by_key[(arm, case_id)]
            if not a_selected["complete"] and arm_selected["complete"]:
                mechanism = "reranker promoted required evidence"
            elif a_selected["complete"] and not arm_selected["complete"]:
                mechanism = "reranker demoted required evidence"
            elif not arm_selected["complete"] and subgroup == "SELECTION_DIVERSITY_MISS":
                mechanism = "diversity still removed evidence"
            elif arm_selected["complete"] and arm_verdict["case_verdict"] not in PASS_VERDICTS:
                mechanism = "generation failed despite sufficient context"
            else:
                mechanism = "context already sufficient"
            reranker_rows.append(
                {
                    "arm": arm,
                    "case_id": case_id,
                    "subgroup": subgroup,
                    "a_candidate_coverage": a_candidate,
                    "arm_candidate_coverage": arm_candidate,
                    "a_selected_coverage": a_selected,
                    "arm_selected_coverage": arm_selected,
                    "a_case_verdict": a_verdict["case_verdict"],
                    "arm_case_verdict": arm_verdict["case_verdict"],
                    "case_transition": transition(a_verdict, arm_verdict),
                    "mechanism": mechanism,
                }
            )
    target_analysis = metadata(
        frozen_target_counts={"hybrid": 9, "reranker_total": 10, "reranker_ranking": 2, "reranker_diversity": 8},
        hybrid_primary_metric={
            "name": "claim_required_evidence_candidate_coverage",
            "frozen_operationalization": "anchor_pass; document_pass retained separately",
            "a_complete": sum(row["a_candidate_coverage"]["complete"] for row in hybrid_rows),
            "b_complete": sum(row["b_candidate_coverage"]["complete"] for row in hybrid_rows),
            "a_document_complete": sum(row["a_candidate_coverage"]["document_complete"] for row in hybrid_rows),
            "b_document_complete": sum(row["b_candidate_coverage"]["document_complete"] for row in hybrid_rows),
            "recovered_case_ids": [row["case_id"] for row in hybrid_rows if not row["a_candidate_coverage"]["complete"] and row["b_candidate_coverage"]["complete"]],
        },
        hybrid_downstream_counts=dict(sorted(Counter(row["downstream_mechanism"] for row in hybrid_rows).items())),
        hybrid_rows=hybrid_rows,
        reranker_primary_metric={
            arm: {
                subgroup: {
                    "case_count": sum(row["arm"] == arm and row["subgroup"] == subgroup for row in reranker_rows),
                    "a_selected_complete": sum(row["arm"] == arm and row["subgroup"] == subgroup and row["a_selected_coverage"]["complete"] for row in reranker_rows),
                    "arm_selected_complete": sum(row["arm"] == arm and row["subgroup"] == subgroup and row["arm_selected_coverage"]["complete"] for row in reranker_rows),
                    "a_selected_document_complete": sum(row["arm"] == arm and row["subgroup"] == subgroup and row["a_selected_coverage"]["document_complete"] for row in reranker_rows),
                    "arm_selected_document_complete": sum(row["arm"] == arm and row["subgroup"] == subgroup and row["arm_selected_coverage"]["document_complete"] for row in reranker_rows),
                    "recovered_case_ids": [row["case_id"] for row in reranker_rows if row["arm"] == arm and row["subgroup"] == subgroup and not row["a_selected_coverage"]["complete"] and row["arm_selected_coverage"]["complete"]],
                }
                for subgroup in ("SELECTION_RANKING_MISS", "SELECTION_DIVERSITY_MISS")
            }
            for arm in ("C", "D")
        },
        reranker_rows=reranker_rows,
    )
    phase2_diagnostics = read_json(PHASE2_DIR / "diagnostics.json")
    expected_target_counts = {
        "B_document": phase2_diagnostics["B_retrieval_miss_targets"]["document_pass_count"],
        "B_anchor": phase2_diagnostics["B_retrieval_miss_targets"]["anchor_pass_count"],
        "C_document": phase2_diagnostics["C_selection_targets"]["document_pass_count"],
        "C_anchor": phase2_diagnostics["C_selection_targets"]["anchor_pass_count"],
        "D_document": phase2_diagnostics["D_selection_targets"]["document_pass_count"],
        "D_anchor": phase2_diagnostics["D_selection_targets"]["anchor_pass_count"],
    }
    observed_target_counts = {
        "B_document": target_analysis["hybrid_primary_metric"]["b_document_complete"],
        "B_anchor": target_analysis["hybrid_primary_metric"]["b_complete"],
        "C_document": sum(target_analysis["reranker_primary_metric"]["C"][group]["arm_selected_document_complete"] for group in ("SELECTION_RANKING_MISS", "SELECTION_DIVERSITY_MISS")),
        "C_anchor": sum(target_analysis["reranker_primary_metric"]["C"][group]["arm_selected_complete"] for group in ("SELECTION_RANKING_MISS", "SELECTION_DIVERSITY_MISS")),
        "D_document": sum(target_analysis["reranker_primary_metric"]["D"][group]["arm_selected_document_complete"] for group in ("SELECTION_RANKING_MISS", "SELECTION_DIVERSITY_MISS")),
        "D_anchor": sum(target_analysis["reranker_primary_metric"]["D"][group]["arm_selected_complete"] for group in ("SELECTION_RANKING_MISS", "SELECTION_DIVERSITY_MISS")),
    }
    if observed_target_counts != expected_target_counts:
        raise SystemExit(f"target coverage does not reproduce frozen Phase 2 diagnostics: {observed_target_counts} != {expected_target_counts}")
    target_analysis["phase2_diagnostics_reproduction"] = {
        "status": "PASS",
        "source_sha256": file_sha256(PHASE2_DIR / "diagnostics.json"),
        "expected": expected_target_counts,
        "observed": observed_target_counts,
    }
    write_json(RUN_DIR / "target_group_analysis.json", target_analysis)

    union_targets = set(targets["hybrid_rerank"])
    unique_d = [
        case_id for case_id in sorted(union_targets)
        if verdict_by_key[("A", case_id)]["case_verdict"] not in PASS_VERDICTS
        and verdict_by_key[("B", case_id)]["case_verdict"] not in PASS_VERDICTS
        and verdict_by_key[("C", case_id)]["case_verdict"] not in PASS_VERDICTS
        and verdict_by_key[("D", case_id)]["case_verdict"] in PASS_VERDICTS
    ]
    complementarity = metadata(
        target_definition="frozen hybrid_rerank union target set",
        target_case_count=len(union_targets),
        d_unique_target_fixes=unique_d,
        d_complementarity_gate="PASS" if unique_d else "FAIL",
    )
    write_json(RUN_DIR / "complementarity.json", complementarity)

    no_failure = {row["case_id"] for row in failure if row["primary_root_cause"] == "NO_FAILURE"}
    severe_rows = []
    for arm in EXPERIMENTAL_ARMS:
        for case_id in sorted(no_failure):
            a_verdict = verdict_by_key[("A", case_id)]
            arm_verdict = verdict_by_key[(arm, case_id)]
            signals = []
            if a_verdict["case_verdict"] in PASS_VERDICTS and arm_verdict["case_verdict"] not in PASS_VERDICTS:
                signals.append("PREVIOUSLY_CORRECT_BECAME_INCORRECT")
            if a_verdict["answerability_class"] in {"CORRECT_ANSWER", "CORRECT_REFUSAL"} and arm_verdict["answerability_class"] in {"INCORRECT_ANSWER", "INCORRECT_REFUSAL"}:
                signals.append("NEW_ANSWERABILITY_ERROR")
            for claim in blind_case_by_id[case_id]["Gold"]["required_claims"]:
                a_claim = claim_by_key[("A", case_id, claim["claim_id"])]
                arm_claim = claim_by_key[(arm, case_id, claim["claim_id"])]
                if a_claim["semantic_state"] == "SUPPORTED_CORRECT" and arm_claim["semantic_state"] in {"UNSUPPORTED", "CONTRADICTED"}:
                    signals.append("SUPPORTED_CLAIM_BECAME_UNSUPPORTED")
                if arm_claim["semantic_state"] in {"UNSUPPORTED", "CONTRADICTED"} and a_claim["semantic_state"] not in {"UNSUPPORTED", "CONTRADICTED"}:
                    signals.append("NEW_MATERIAL_UNSUPPORTED_CLAIM")
                if a_claim["citation_semantic_status"] == "VALID_ID_AND_SUPPORT" and arm_claim["citation_semantic_status"] in INVALID_CITATIONS:
                    signals.append("NEW_INVALID_SEMANTIC_CITATION_SUPPORT")
            severe_rows.append({"arm": arm, "case_id": case_id, "signals": sorted(set(signals)), "severe_regression": bool(signals)})
    severe = metadata(
        frozen_no_failure_case_count=len(no_failure),
        inspected_pair_count=len(severe_rows),
        arms={
            arm: {
                "severe_regression_count": sum(row["arm"] == arm and row["severe_regression"] for row in severe_rows),
                "case_ids": [row["case_id"] for row in severe_rows if row["arm"] == arm and row["severe_regression"]],
            }
            for arm in EXPERIMENTAL_ARMS
        },
        rows=severe_rows,
    )
    write_json(RUN_DIR / "severe_regressions.json", severe)

    causal_rows = []
    for row in transition_rows:
        if row["transition"] not in {"FIXED_FAILURE", "NEW_REGRESSION"}:
            continue
        arm, case_id = row["arm"], row["case_id"]
        a_candidate = coverage[("A", case_id, "candidate")]
        a_selected = coverage[("A", case_id, "selected")]
        arm_candidate = coverage[(arm, case_id, "candidate")]
        arm_selected = coverage[(arm, case_id, "selected")]
        cause = dominant_cause(row["transition"], arm, case_id, a_candidate, a_selected, arm_candidate, arm_selected, verdict_by_key[(arm, case_id)], claim_rows, targets)
        trace = traces[arm][case_id]
        causal_rows.append(
            {
                "arm": arm,
                "case_id": case_id,
                "transition": row["transition"],
                "dominant_cause": cause,
                "human_readable_note": f"{row['transition']}: candidate coverage {a_candidate['complete']}→{arm_candidate['complete']}; selected coverage {a_selected['complete']}→{arm_selected['complete']}; semantic verdict {row['a_case_verdict']}→{row['arm_case_verdict']}; dominant cause {cause}.",
                "candidate_retrieval": {"a": a_candidate, "arm": arm_candidate},
                "branch_admission": {"pipeline": trace["pipeline"], "counts": trace["counts"], "candidate_rows": [compact_source(value) for value in trace["candidates"]]},
                "ordering": {"ordered_for_governance": trace["ordered_for_governance"]},
                "selected_context": {"a": a_selected, "arm": arm_selected, "selected_identities": trace["selected"]},
                "generation_output": bundle_by_id[case_id][arm]["answer"],
                "citation_ids": bundle_by_id[case_id][arm]["citation_ids"],
                "semantic_verdict": verdict_by_key[(arm, case_id)],
            }
        )
    causal = metadata(
        changed_case_arm_count=len(causal_rows),
        dominant_cause_distribution=dict(sorted(Counter(row["dominant_cause"] for row in causal_rows).items())),
        rows=causal_rows,
    )
    write_json(RUN_DIR / "causal_traces.json", causal)

    phase2_latency = read_json(PHASE2_DIR / "latency_summary.json")
    phase3_latency = read_json(PHASE3_DIR / "combined_latency.json")
    reranker_ops = read_json(PHASE2_DIR / "reranker_operations.json")
    memory = read_json(PHASE2_DIR / "memory.json")
    latency_by_arm = {row["arm"]: row for row in phase3_latency["rows"]}
    quality_latency = metadata(
        arms={
            arm: {
                "fully_correct_case_count": summaries[arm]["fully_correct_case_count"],
                "reviewed_correct_claim_count": summaries[arm]["reviewed_correctness"]["count"],
                **latency_by_arm[arm],
            }
            for arm in EXPERIMENTAL_ARMS
        },
        retrieval_selection_source_sha256=file_sha256(PHASE2_DIR / "latency_summary.json"),
        generation_and_derived_source_sha256=file_sha256(PHASE3_DIR / "combined_latency.json"),
        combined_latency_is_derived=True,
        dense_stage_limitation="Phase 2 Dense timing is frozen-trace lookup, not online embedding/FAISS.",
        b_total_limitation="B approximate total is not a production-normalized end-to-end SLO measurement.",
        reranker_operations=reranker_ops,
        memory_measurement=memory,
    )
    write_json(RUN_DIR / "quality_latency.json", quality_latency)

    # New hard-gate signals are computed over all cases relative to the freshly blinded A review.
    hard_signals: dict[str, dict[str, list[str]]] = {}
    for arm in EXPERIMENTAL_ARMS:
        new_unsupported = set()
        new_invalid_citation = set()
        new_answerability = set()
        for case_id, blind_case in blind_case_by_id.items():
            a_v = verdict_by_key[("A", case_id)]
            arm_v = verdict_by_key[(arm, case_id)]
            if a_v["answerability_class"] in {"CORRECT_ANSWER", "CORRECT_REFUSAL"} and arm_v["answerability_class"] in {"INCORRECT_ANSWER", "INCORRECT_REFUSAL"}:
                new_answerability.add(case_id)
            for claim in blind_case["Gold"]["required_claims"]:
                a_c = claim_by_key[("A", case_id, claim["claim_id"])]
                arm_c = claim_by_key[(arm, case_id, claim["claim_id"])]
                if arm_c["semantic_state"] in {"UNSUPPORTED", "CONTRADICTED"} and a_c["semantic_state"] not in {"UNSUPPORTED", "CONTRADICTED"}:
                    new_unsupported.add(case_id)
                if a_c["citation_semantic_status"] == "VALID_ID_AND_SUPPORT" and arm_c["citation_semantic_status"] in INVALID_CITATIONS:
                    new_invalid_citation.add(case_id)
        hard_signals[arm] = {
            "new_unsupported_claim_case_ids": sorted(new_unsupported),
            "new_invalid_semantic_citation_case_ids": sorted(new_invalid_citation),
            "new_answerability_error_case_ids": sorted(new_answerability),
        }

    target_sets = {"B": targets["hybrid"], "C": targets["dense_rerank"], "D": targets["hybrid_rerank"]}
    primary_positive = {
        "B": len(target_analysis["hybrid_primary_metric"]["recovered_case_ids"]),
        "C": sum(len(target_analysis["reranker_primary_metric"]["C"][group]["recovered_case_ids"]) for group in ("SELECTION_RANKING_MISS", "SELECTION_DIVERSITY_MISS")),
        "D": sum(len(target_analysis["reranker_primary_metric"]["D"][group]["recovered_case_ids"]) for group in ("SELECTION_RANKING_MISS", "SELECTION_DIVERSITY_MISS")),
    }
    gate_rows = []
    for arm in EXPERIMENTAL_ARMS:
        target_transition_rows = [row for row in transition_rows if row["arm"] == arm and row["case_id"] in target_sets[arm]]
        fixed = sum(row["transition"] == "FIXED_FAILURE" for row in target_transition_rows)
        regressions = sum(row["transition"] == "NEW_REGRESSION" for row in target_transition_rows)
        gate1 = True
        gate2 = primary_positive[arm] > 0
        severe_count = severe["arms"][arm]["severe_regression_count"]
        signal = hard_signals[arm]
        gate3 = severe_count == 0 and not any(signal.values())
        gate4 = fixed > regressions
        gate5 = True
        additional = complementarity["d_complementarity_gate"] == "PASS" if arm == "D" else True
        gate_rows.append(
            {
                "arm": arm,
                "gate_1_validity": {"pass": gate1, "reason": "Frozen bindings, execution, and 288-response review are complete."},
                "gate_2_own_primary_target": {"pass": gate2, "positive_primary_cases": primary_positive[arm]},
                "gate_3_hard_regression": {"pass": gate3, "severe_regression_count": severe_count, **signal},
                "gate_4_target_balance": {"pass": gate4, "target_fixed_cases": fixed, "target_regressions": regressions},
                "gate_5_operational_evidence": {"pass": gate5, "latency_reproducible": True, "memory_disclosed_unavailable": not memory["reliable"]},
                "additional_d_complementarity": {"pass": additional, "unique_target_fixes": unique_d if arm == "D" else None},
                "eligible_before_pareto": all((gate1, gate2, gate3, gate4, gate5, additional)),
            }
        )

    eligible = [row["arm"] for row in gate_rows if row["eligible_before_pareto"]]
    complexity = {"B": 1, "C": 2, "D": 3}
    frontier = []
    for arm in eligible:
        quality = summaries[arm]["fully_correct_case_count"]
        latency = latency_by_arm[arm]["approx_total_p50_ms"]
        dominated = any(
            other != arm
            and summaries[other]["fully_correct_case_count"] >= quality
            and latency_by_arm[other]["approx_total_p50_ms"] <= latency
            and complexity[other] <= complexity[arm]
            and (
                summaries[other]["fully_correct_case_count"] > quality
                or latency_by_arm[other]["approx_total_p50_ms"] < latency
                or complexity[other] < complexity[arm]
            )
            for other in eligible
        )
        if not dominated:
            frontier.append(arm)
    if not frontier:
        recommendation = "KEEP_A"
    else:
        chosen = min(frontier, key=lambda arm: (complexity[arm], latency_by_arm[arm]["approx_total_p50_ms"], -summaries[arm]["fully_correct_case_count"]))
        recommendation = f"SELECT_{chosen}"
    for row in gate_rows:
        row["gate_6_pareto_frontier"] = {"pass": row["arm"] in frontier, "frontier": frontier}
        row["research_label"] = "RESEARCH_EFFECTIVE_BUT_NOT_PRODUCTION_WORTHY" if primary_positive[row["arm"]] > 0 and not row["eligible_before_pareto"] else None
    gate_matrix = metadata(
        frozen_gate_application=True,
        arms=gate_rows,
        eligible_arms_before_pareto=eligible,
        pareto_frontier=frontier,
        recommendation=recommendation,
    )
    write_json(RUN_DIR / "production_gate_matrix.json", gate_matrix)

    historical_differences = []
    historical_by_id = {row["case_id"]: row for row in failure}
    for case_id in gold_by_id:
        fresh = verdict_by_key[("A", case_id)]["case_verdict"]
        historical = historical_by_id[case_id]["case_verdict"]
        if fresh != historical:
            historical_differences.append({"case_id": case_id, "historical_a_verdict": historical, "phase4_blinded_a_verdict": fresh})
    write_json(
        RUN_DIR / "historical_a_reconciliation.json",
        metadata(
            comparison_only=True,
            pass1_verdicts_not_changed=True,
            difference_count=len(historical_differences),
            differences=historical_differences,
        ),
    )

    recommendation_evidence = metadata(
        recommendation=recommendation,
        rationale=(
            "No experimental arm survives every preregistered hard gate; retain frozen A and do not integrate."
            if recommendation == "KEEP_A"
            else f"{recommendation.removeprefix('SELECT_')} survives the preregistered gates and is the smallest reviewed Pareto-frontier architecture."
        ),
        no_production_integration_started=True,
        phase5_started=False,
        d_complementarity_gate=complementarity["d_complementarity_gate"],
        unresolved_uncertainties=[
            "Reranker memory measurement is unavailable because the frozen Phase 2 OS measurement failed.",
            "Approximate total latency is derived by adding Phase 2 and Phase 3 percentiles, not measured as one continuous production request.",
            f"Fresh blinded A verdict differs from historical failure-analysis verdict on {len(historical_differences)} cases; Pass-1 verdicts were not changed after unblinding.",
        ],
        new_deepseek_calls=0,
        new_generation_calls=0,
        new_retrieval_runs=0,
        new_reranker_runs=0,
        arm_a_reruns=0,
        production_modifications=0,
    )
    write_json(RUN_DIR / "final_recommendation_evidence.json", recommendation_evidence)
    print(
        json.dumps(
            {
                "status": "UNBLINDED_EVIDENCE_COMPLETE",
                "recommendation": recommendation,
                "transition_counts": {arm: transition_summary[arm]["counts"] for arm in EXPERIMENTAL_ARMS},
                "severe_regressions": {arm: severe["arms"][arm]["severe_regression_count"] for arm in EXPERIMENTAL_ARMS},
                "primary_positive": primary_positive,
                "d_unique_target_fixes": unique_d,
                "historical_a_differences": len(historical_differences),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
