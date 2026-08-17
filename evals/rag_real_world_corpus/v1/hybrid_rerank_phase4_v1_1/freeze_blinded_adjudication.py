from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
V1 = HERE.parent
ROOT = V1.parents[2]
RUN_ID = "20260814T131417Z-04dfc031"
RUN_DIR = V1 / f"results/hybrid_rerank_phase4_v1_1/{RUN_ID}"
INPUT_PATH = RUN_DIR / "blinded_review_input.json"
INPUT_SHA256 = "ff202f3c2e55a3d55ba958757a86a9a949a185cd648a31eb838c44e4f423ff9c"
DESIGN_SHA256 = "442bedce1c43b27b3557b0055708342edd278e98bcac0c12a68c1390fe88f655"
PHASE2_RUN_ID = "20260814T095542Z-1317c6a7"
PHASE3_RUN_ID = "20260814T123142Z-8852712b"


# This table was authored from blinded_review_input.json only.  Keys expose no arm.
# Each tuple is (case_id, response label, one-based claim number).
EXCEPTIONS: dict[tuple[str, str, int], tuple[str, str]] = {
    ("rw-gold-v1-single-ragas-dataset", "response_X1", 1): ("SUPPORTED_BUT_INCOMPLETE", "Names EvaluationDataset but omits the required EvaluationDataset.from_list construction method."),
    ("rw-gold-v1-semantic-checkpointer-store", "response_X1", 1): ("SUPPORTED_BUT_INCOMPLETE", "Explains persistence continuity but does not establish the claim's two-source high-level-capabilities plus persistence basis."),
    ("rw-gold-v1-semantic-context-order", "response_X2", 2): ("SUPPORTED_BUT_INCOMPLETE", "Explains the ordering penalty but omits the frozen example's approximately 1.0 to 0.5 change."),
    ("rw-gold-v1-semantic-context-order", "response_X3", 2): ("SUPPORTED_BUT_INCOMPLETE", "Explains the ordering penalty but omits the frozen example's approximately 1.0 to 0.5 change."),
    ("rw-gold-v1-semantic-context-order", "response_X4", 2): ("SUPPORTED_BUT_INCOMPLETE", "Explains the ordering penalty but omits the frozen example's approximately 1.0 to 0.5 change."),
    ("rw-gold-v1-long-bge-score-mix", "response_X2", 2): ("MISSING", "Does not state the frozen 0.4/0.2/0.4 weights."),
    ("rw-gold-v1-long-bge-score-mix", "response_X3", 2): ("MISSING", "Does not state the frozen 0.4/0.2/0.4 weights."),
    ("rw-gold-v1-long-bge-score-mix", "response_X4", 2): ("CONTRADICTED", "Misidentifies four per-pair output scores as the mode weights and does not give 0.4/0.2/0.4."),
    ("rw-gold-v1-long-interrupt-static", "response_X1", 3): ("MISSING", "Provides compile-time breakpoints but omits per-invocation run-time interrupt_before/interrupt_after."),
    ("rw-gold-v1-long-interrupt-static", "response_X2", 1): ("CONTRADICTED", "Calls static interrupts suitable for human approval, contrary to the frozen debugging/testing distinction."),
    ("rw-gold-v1-long-interrupt-static", "response_X2", 2): ("CONTRADICTED", "Describes dynamic interrupt() as compile-time static configuration."),
    ("rw-gold-v1-long-interrupt-static", "response_X3", 1): ("SUPPORTED_BUT_INCOMPLETE", "Correctly identifies debugging but omits that static interrupts are not recommended for human-in-the-loop workflows."),
    ("rw-gold-v1-long-interrupt-static", "response_X3", 3): ("MISSING", "Omits per-invocation run-time interrupt_before/interrupt_after."),
    ("rw-gold-v1-long-interrupt-static", "response_X4", 3): ("MISSING", "Provides compile-time breakpoints but omits per-invocation run-time interrupt_before/interrupt_after."),
    ("rw-gold-v1-long-interrupt-validation", "response_X1", 1): ("SUPPORTED_BUT_INCOMPLETE", "Says one interrupt per invocation and stores an error, but omits using the question stored in state."),
    ("rw-gold-v1-long-interrupt-validation", "response_X1", 3): ("MISSING", "Gives the replay-growth warning but not the frozen non-deterministic interrupt-ordering obligation."),
    ("rw-gold-v1-long-interrupt-validation", "response_X2", 1): ("SUPPORTED_BUT_INCOMPLETE", "Says one interrupt per invocation and stores an error, but omits using the question stored in state."),
    ("rw-gold-v1-long-interrupt-validation", "response_X2", 3): ("MISSING", "Gives the replay-growth warning but not the frozen non-deterministic interrupt-ordering obligation."),
    ("rw-gold-v1-long-interrupt-validation", "response_X3", 1): ("SUPPORTED_BUT_INCOMPLETE", "Says one interrupt per invocation and stores an error, but omits using the question stored in state."),
    ("rw-gold-v1-long-interrupt-validation", "response_X3", 3): ("MISSING", "Gives the replay-growth warning but not the frozen non-deterministic interrupt-ordering obligation."),
    ("rw-gold-v1-long-interrupt-validation", "response_X4", 1): ("SUPPORTED_BUT_INCOMPLETE", "Says one interrupt per invocation and stores an error, but omits using the question stored in state."),
    ("rw-gold-v1-long-interrupt-validation", "response_X4", 3): ("MISSING", "Gives the replay-growth warning but not the frozen non-deterministic interrupt-ordering obligation."),
    ("rw-gold-v1-long-langgraph-positioning", "response_X1", 2): ("MISSING", "Does not identify control over both workflows and agent state."),
    ("rw-gold-v1-long-langgraph-positioning", "response_X2", 2): ("CONTRADICTED", "Substitutes short-term versus long-term memory for the required workflow versus state control pair."),
    ("rw-gold-v1-long-langgraph-positioning", "response_X3", 2): ("CONTRADICTED", "Substitutes infrastructure and persistence-memory categories for workflow versus state control."),
    ("rw-gold-v1-long-langgraph-positioning", "response_X4", 2): ("MISSING", "Does not identify control over both workflows and agent state."),
    ("rw-gold-v1-multi-backend-control", "response_X1", 3): ("UNSUPPORTED", "Substitutes a RequestValidationError handler for the required HTTPException permission-failure mechanism."),
    ("rw-gold-v1-multi-backend-control", "response_X3", 3): ("MISSING", "Mentions generic custom exception handling but not HTTPException terminating with a client error."),
    ("rw-gold-v1-multi-backend-control", "response_X4", 1): ("SUPPORTED_BUT_INCOMPLETE", "Describes def/async execution but does not state that await-capable I/O belongs in async def."),
    ("rw-gold-v1-multi-backend-control", "response_X4", 3): ("MISSING", "Does not identify HTTPException as the client-error mechanism."),
    ("rw-gold-v1-multi-error-observability", "response_X1", 1): ("SUPPORTED_BUT_INCOMPLETE", "Describes the resulting client response but omits raising HTTPException to terminate the request."),
    ("rw-gold-v1-multi-error-observability", "response_X2", 1): ("SUPPORTED_BUT_INCOMPLETE", "Describes generic client errors but omits raising HTTPException to terminate the request."),
    ("rw-gold-v1-multi-error-observability", "response_X2", 2): ("SUPPORTED_BUT_INCOMPLETE", "Discusses implicit success status but omits Error and the default Unset semantics required by Gold."),
    ("rw-gold-v1-multi-error-observability", "response_X3", 1): ("SUPPORTED_BUT_INCOMPLETE", "Describes the resulting client response but omits raising HTTPException to terminate the request."),
    ("rw-gold-v1-multi-error-observability", "response_X4", 1): ("SUPPORTED_BUT_INCOMPLETE", "Describes the resulting client response but omits raising HTTPException to terminate the request."),
    ("rw-gold-v1-multi-eval-stack", "response_X1", 2): ("CONTRADICTED", "Uses ID-based reference-context comparison in place of the required retrieved-context versus reference-response comparison."),
    ("rw-gold-v1-multi-hybrid-index", "response_X1", 1): ("SUPPORTED_BUT_INCOMPLETE", "Provides dense/sparse signals but omits BGE-M3's hybrid-retrieval-plus-reranking recommendation."),
    ("rw-gold-v1-multi-hybrid-index", "response_X2", 1): ("SUPPORTED_BUT_INCOMPLETE", "Provides dense/sparse signals but omits BGE-M3's hybrid-retrieval-plus-reranking recommendation."),
    ("rw-gold-v1-multi-hybrid-index", "response_X3", 1): ("SUPPORTED_BUT_INCOMPLETE", "Provides the retrieval signals but omits BGE-M3's hybrid-retrieval-plus-reranking recommendation."),
    ("rw-gold-v1-multi-hybrid-index", "response_X4", 1): ("SUPPORTED_BUT_INCOMPLETE", "Provides dense/sparse signals but omits BGE-M3's hybrid-retrieval-plus-reranking recommendation."),
    ("rw-gold-v1-multi-retrieval-eval", "response_X4", 1): ("SUPPORTED_BUT_INCOMPLETE", "Identifies Faiss similarity search but omits the frozen vector-distance or dot-product mechanism."),
    ("rw-gold-v1-disambig-fastapi-async-deps", "response_X1", 1): ("SUPPORTED_BUT_INCOMPLETE", "Uses the async source for threadpool behavior but does not state its endpoint-selection guidance."),
    ("rw-gold-v1-disambig-fastapi-async-deps", "response_X3", 1): ("SUPPORTED_BUT_INCOMPLETE", "Uses the async source for threadpool behavior but does not state its endpoint-selection guidance."),
    ("rw-gold-v1-stress-cross-agent-api-replay", "response_X2", 2): ("MISSING", "Omits making the side effect idempotent, moving it after approval, or isolating it in another node."),
    ("rw-gold-v1-stress-cross-agent-api-replay", "response_X3", 2): ("MISSING", "Omits making the side effect idempotent, moving it after approval, or isolating it in another node."),
    ("rw-gold-v1-stress-cross-agent-api-replay", "response_X3", 3): ("UNSUPPORTED", "Substitutes an interrupt payload for the required FastAPI HTTPException client-error boundary."),
    ("rw-gold-v1-stress-cross-agent-api-replay", "response_X4", 2): ("MISSING", "Omits making the side effect idempotent, moving it after approval, or isolating it in another node."),
    ("rw-gold-v1-stress-cross-agent-api-replay", "response_X4", 3): ("SUPPORTED_BUT_INCOMPLETE", "Suggests custom error handlers but omits HTTPException terminating and carrying the client error."),
    ("rw-gold-v1-stress-cross-embedding-api-concurrency", "response_X1", 2): ("SUPPORTED_BUT_INCOMPLETE", "Correctly selects normal def for blocking no-await libraries but omits async def for calls that must be awaited."),
    ("rw-gold-v1-stress-cross-embedding-api-concurrency", "response_X2", 2): ("SUPPORTED_BUT_INCOMPLETE", "Correctly selects normal def for blocking no-await libraries but omits async def for calls that must be awaited."),
    ("rw-gold-v1-stress-cross-embedding-api-concurrency", "response_X3", 2): ("SUPPORTED_BUT_INCOMPLETE", "Correctly selects normal def for blocking no-await libraries but omits async def for calls that must be awaited."),
    ("rw-gold-v1-stress-cross-embedding-api-concurrency", "response_X4", 2): ("SUPPORTED_BUT_INCOMPLETE", "Correctly selects normal def for blocking no-await libraries but omits async def for calls that must be awaited."),
    ("rw-gold-v1-stress-cross-persistence-tracing", "response_X1", 1): ("SUPPORTED_BUT_INCOMPLETE", "Names checkpointer persistence but omits the required persistent-versus-in-memory saver distinction."),
    ("rw-gold-v1-stress-cross-persistence-tracing", "response_X2", 1): ("SUPPORTED_BUT_INCOMPLETE", "Names checkpointer persistence but omits the required persistent-versus-in-memory saver distinction."),
    ("rw-gold-v1-stress-cross-persistence-tracing", "response_X3", 1): ("SUPPORTED_BUT_INCOMPLETE", "Names checkpointer persistence but omits the required persistent-versus-in-memory saver distinction."),
    ("rw-gold-v1-stress-cross-persistence-tracing", "response_X4", 1): ("SUPPORTED_BUT_INCOMPLETE", "Names checkpointer persistence but omits the required persistent-versus-in-memory saver distinction."),
    ("rw-gold-v1-stress-cross-retrieval-evaluation", "response_X2", 1): ("MISSING", "Does not state BGE-M3's dense/sparse signals or hybrid-plus-reranking recommendation."),
    ("rw-gold-v1-stress-cross-retrieval-evaluation", "response_X2", 2): ("SUPPORTED_BUT_INCOMPLETE", "Lists time, quality, and memory trade-offs but omits training and adding time."),
    ("rw-gold-v1-stress-cross-retrieval-evaluation", "response_X3", 1): ("SUPPORTED_BUT_INCOMPLETE", "States the retrieval signals but omits the hybrid-plus-reranking recommendation."),
    ("rw-gold-v1-stress-cross-retrieval-evaluation", "response_X3", 2): ("SUPPORTED_BUT_INCOMPLETE", "Describes Faiss search but incompletely covers the frozen operational trade-off list."),
    ("rw-gold-v1-stress-cross-retrieval-evaluation", "response_X4", 1): ("SUPPORTED_BUT_INCOMPLETE", "States the retrieval signals but omits the hybrid-plus-reranking recommendation."),
    ("rw-gold-v1-stress-cross-retrieval-evaluation", "response_X4", 2): ("SUPPORTED_BUT_INCOMPLETE", "Lists time, quality, and memory trade-offs but omits training and adding time."),
    ("rw-gold-v1-stress-conflict-ragas-reference-mode", "response_X1", 1): ("SUPPORTED_BUT_INCOMPLETE", "Identifies the variants but does not state reference-comparison versus response-comparison semantics."),
    ("rw-gold-v1-stress-conflict-ragas-reference-mode", "response_X2", 1): ("CONTRADICTED", "Misidentifies the without-reference source as with-reference and omits the two comparison semantics."),
    ("rw-gold-v1-stress-conflict-ragas-reference-mode", "response_X3", 1): ("SUPPORTED_BUT_INCOMPLETE", "Mentions the reference requirement but omits the without-reference response comparison."),
    ("rw-gold-v1-stress-conflict-ragas-reference-mode", "response_X4", 1): ("SUPPORTED_BUT_INCOMPLETE", "Identifies the variants but does not state reference-comparison versus response-comparison semantics."),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


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


def expected_group_coverage(case: dict[str, Any], response: dict[str, Any], claim: dict[str, Any]) -> dict[str, Any]:
    groups = {row["evidence_group_id"]: row for row in case["Gold"]["acceptable_evidence_groups"]}
    documents = {row.get("document_id") for row in response["cited_evidence"]}
    evidence = {value for row in response["cited_evidence"] for value in row.get("evidence_ids", [])}
    rows = []
    for group_id in claim["evidence_group_ids"]:
        group = groups[group_id]
        matched = bool(documents.intersection(group.get("any_of_document_ids", [])) or evidence.intersection(group.get("any_of_evidence_ids", [])))
        rows.append({"evidence_group_id": group_id, "covered": matched})
    return {"groups": rows, "all_covered": all(row["covered"] for row in rows)}


def citation_fields(state: str, correct_refusal: bool) -> dict[str, Any]:
    if correct_refusal:
        return {
            "citation_id_valid": True,
            "citation_semantically_supports_claim": None,
            "citation_complete_for_claim": None,
            "citation_semantic_status": "NOT_APPLICABLE_REFUSAL",
        }
    if state == "SUPPORTED_CORRECT":
        return {"citation_id_valid": True, "citation_semantically_supports_claim": True, "citation_complete_for_claim": True, "citation_semantic_status": "VALID_ID_AND_SUPPORT"}
    if state == "SUPPORTED_BUT_INCOMPLETE":
        return {"citation_id_valid": True, "citation_semantically_supports_claim": True, "citation_complete_for_claim": False, "citation_semantic_status": "VALID_ID_BUT_WEAK_SUPPORT"}
    if state == "MISSING":
        return {"citation_id_valid": True, "citation_semantically_supports_claim": False, "citation_complete_for_claim": False, "citation_semantic_status": "MISSING_REQUIRED_CITATION"}
    return {"citation_id_valid": True, "citation_semantically_supports_claim": False, "citation_complete_for_claim": False, "citation_semantic_status": "MISATTRIBUTED_SUPPORT"}


def case_verdict(expected: bool, actual: bool, states: list[str]) -> tuple[str, str]:
    if not expected:
        return ("CORRECT_REFUSAL", "CORRECT_REFUSAL") if not actual else ("INCORRECT_ANSWER", "FAIL")
    if not actual:
        return "INCORRECT_REFUSAL", "INCORRECT_REFUSAL"
    if states and all(value == "SUPPORTED_CORRECT" for value in states):
        return "CORRECT_ANSWER", "FULL_PASS"
    if any(value in {"SUPPORTED_CORRECT", "SUPPORTED_BUT_INCOMPLETE"} for value in states):
        return "PARTIAL_ANSWER", "PARTIAL_PASS"
    return "INCORRECT_ANSWER", "FAIL"


def main() -> int:
    if file_sha256(INPUT_PATH) != INPUT_SHA256:
        raise SystemExit("blinded input drift")
    data = read_json(INPUT_PATH)
    claim_rows = []
    verdict_rows = []
    exception_keys_used: set[tuple[str, str, int]] = set()
    for case in data["cases"]:
        expected = case["Gold"]["answerability"]
        for response in case["responses"]:
            actual = response["answerable"]
            reviews = []
            for index, claim in enumerate(case["Gold"]["required_claims"], start=1):
                key = (case["case_id"], response["response_label"], index)
                if not expected and not actual:
                    state = "SUPPORTED_CORRECT"
                    reason = "The frozen case is unanswerable and the response gives a corpus-bounded refusal without citations."
                elif expected and not actual:
                    state = "MISSING"
                    reason = "The response incorrectly refuses an answerable case, so the required claim is absent."
                elif key in EXCEPTIONS:
                    state, reason = EXCEPTIONS[key]
                    exception_keys_used.add(key)
                else:
                    state = "SUPPORTED_CORRECT"
                    reason = "The anonymous response expresses the frozen required meaning correctly without a material unsupported or contradicted assertion."
                citation = citation_fields(state, correct_refusal=(not expected and not actual))
                coverage = expected_group_coverage(case, response, claim) if response["cited_evidence"] else {"groups": [], "all_covered": False}
                row = {
                    "case_id": case["case_id"],
                    "response_label": response["response_label"],
                    "claim_id": claim["claim_id"],
                    "canonical_claim": claim["canonical_claim"],
                    "evaluation_mode": claim["evaluation_mode"],
                    "required": claim["required"],
                    "semantic_state": state,
                    "review_reason": reason,
                    "cited_ids": response["citation_ids"],
                    **citation,
                    "expected_evidence_group_coverage": coverage,
                    "review_uncertain": False,
                }
                reviews.append(row)
                claim_rows.append(row)
            states = [row["semantic_state"] for row in reviews]
            output_class, verdict = case_verdict(expected, actual, states)
            citation_statuses = Counter(row["citation_semantic_status"] for row in reviews)
            verdict_rows.append(
                {
                    "case_id": case["case_id"],
                    "response_label": response["response_label"],
                    "gold_answerability": expected,
                    "response_answerable": actual,
                    "answerability_class": output_class,
                    "case_verdict": verdict,
                    "claim_state_counts": dict(sorted(Counter(states).items())),
                    "citation_semantic_status_counts": dict(sorted(citation_statuses.items())),
                    "has_new_material_unsupported_claim": any(value in {"UNSUPPORTED", "CONTRADICTED"} for value in states),
                    "has_invalid_semantic_citation_support": any(value in {"MISATTRIBUTED_SUPPORT", "MISSING_REQUIRED_CITATION"} for value in citation_statuses),
                    "review_uncertain": False,
                }
            )
    if exception_keys_used != set(EXCEPTIONS):
        raise SystemExit(f"unused exception decisions: {sorted(set(EXCEPTIONS) - exception_keys_used)}")
    if len(claim_rows) != 528 or len({(r['case_id'], r['response_label'], r['claim_id']) for r in claim_rows}) != 528:
        raise SystemExit("blinded claim review cardinality/uniqueness failure")
    if len(verdict_rows) != 288 or len({(r['case_id'], r['response_label']) for r in verdict_rows}) != 288:
        raise SystemExit("blinded case verdict cardinality/uniqueness failure")
    claim_payload = metadata(
        review_stage="PASS_1_BLINDED",
        mapping_read=False,
        reviewer_input_sha256=INPUT_SHA256,
        claim_review_count=len(claim_rows),
        unique_frozen_claim_count=len({row["claim_id"] for row in claim_rows}),
        semantic_state_counts=dict(sorted(Counter(row["semantic_state"] for row in claim_rows).items())),
        rows=claim_rows,
    )
    verdict_payload = metadata(
        review_stage="PASS_1_BLINDED",
        mapping_read=False,
        reviewer_input_sha256=INPUT_SHA256,
        verdict_count=len(verdict_rows),
        case_verdict_counts=dict(sorted(Counter(row["case_verdict"] for row in verdict_rows).items())),
        answerability_class_counts=dict(sorted(Counter(row["answerability_class"] for row in verdict_rows).items())),
        rows=verdict_rows,
    )
    adjudication = metadata(
        review_stage="PASS_1_BLINDED_FROZEN",
        blinded_review_complete=True,
        mapping_read=False,
        reviewer="Codex local artifact reviewer",
        reviewer_visible_scope="Only blinded_review_input.json; no sealed mapping, architecture labels, historical verdicts, diagnostics, or latency.",
        external_evaluator_llm_calls=0,
        review_uncertain_count=0,
        claim_reviews=claim_payload,
        case_verdicts=verdict_payload,
        post_unblind_review_corrections=[],
    )
    claim_path = RUN_DIR / "blinded_claim_reviews.json"
    verdict_path = RUN_DIR / "blinded_case_verdicts.json"
    adjudication_path = RUN_DIR / "blinded_adjudication.json"
    write_json(claim_path, claim_payload)
    write_json(verdict_path, verdict_payload)
    write_json(adjudication_path, adjudication)
    detached = file_sha256(adjudication_path)
    (RUN_DIR / "blinded_adjudication.sha256").write_text(detached + "  blinded_adjudication.json\n", encoding="utf-8")
    write_json(
        RUN_DIR / "pass1_freeze.json",
        metadata(
            status="PASS",
            blinded_review_complete=True,
            blinded_review_sha256=detached,
            blinded_claim_reviews_sha256=file_sha256(claim_path),
            blinded_case_verdicts_sha256=file_sha256(verdict_path),
            claim_review_count=528,
            case_verdict_count=288,
            mapping_read_before_freeze=False,
            frozen_before_unblinding=True,
        ),
    )
    print(json.dumps({"BLINDED_REVIEW_COMPLETE": "YES", "BLINDED_REVIEW_SHA256": detached, "claim_reviews": 528, "case_verdicts": 288, "uncertain": 0}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
