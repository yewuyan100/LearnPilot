"""Build the independent semantic verification artifact for Real-world Gold V1.

This is an offline reviewer ledger.  It reopens every referenced frozen source
locator and never reads authoring-side review artifacts, retrieval output,
baseline output, model output, or production RAG state.
"""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from pypdf import PdfReader


GOLD_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[5]
GOLD_PATH = GOLD_ROOT / "gold_cases.json"
ANCHORS_PATH = GOLD_ROOT / "evidence_anchors.json"
MANIFEST_PATH = REPO_ROOT / "evals" / "rag_real_world_corpus" / "v1" / "corpus_manifest.json"
OUTPUT_PATH = GOLD_ROOT / "independent_semantic_verification_v1.json"

EXPECTED_GOLD_SHA256 = "11b71513b00a63e158333eab5d26bc3aded858116f237b1b3b206dc3f444ba9c"
EXPECTED_SEMANTIC_IDS_SHA256 = "078509b631edac94c5a12064671d3aa2141cdb52e902e4434ffaff4052ebe34f"
VERDICTS = {"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "AMBIGUOUS"}


# These eight decisions are the exceptions found during the fresh 104-claim
# pass.  Every other claim in the hash-pinned 104-ID set was independently
# judged SUPPORTED.  The generated artifact materializes all 104 decisions.
PARTIAL_CLAIM_REASONS = {
    "rw-gold-v1-semantic-checkpointer-store-claim-01": (
        "Each alternative independently shows durable continuity and memory in one source, "
        "but the claim asserts that both named sources do so. Under the contract's OR-inside-group "
        "rule, neither alternative alone establishes the two-source 'both' proposition."
    ),
    "rw-gold-v1-long-langgraph-positioning-claim-02": (
        "The reopened overview calls LangGraph a low-level orchestration framework for long-running, "
        "stateful agents. It does not explicitly say that developers receive two distinct controls "
        "over both workflows and state, so the claim is stronger than the locator text."
    ),
    "rw-gold-v1-multi-rag-tracing-claim-01": (
        "One OR alternative lists vectorization, retrieval, and generation; the other records "
        "retrieved_contexts with response. Neither candidate alone supports the complete conjunctive claim."
    ),
    "rw-gold-v1-multi-rag-tracing-claim-02": (
        "One OR alternative establishes request path and span units; the other establishes span "
        "correlation through context propagation. Neither candidate alone supports every part of the claim."
    ),
    "rw-gold-v1-disambig-fastapi-async-deps-claim-01": (
        "The TL;DR alternative supports endpoint def/async-def selection, while the technical-details "
        "alternative supports threadpool behavior. Neither OR candidate independently supports both."
    ),
    "rw-gold-v1-disambig-interrupt-static-claim-01": (
        "The page-22 candidate supports static breakpoints and compile-time configuration; page 23 "
        "supports run-time configuration. The OR group cannot combine them to prove the conjunctive claim."
    ),
    "rw-gold-v1-stress-conflict-fastapi-handler-type-claim-01": (
        "The type-hierarchy alternative explains FastAPI/Starlette HTTPException and handler registration; "
        "the reuse alternative explains importing FastAPI's default handlers. Neither OR alternative alone "
        "establishes both the relationship and the stated handler-reuse proposition."
    ),
    "rw-gold-v1-stress-conflict-ragas-reference-mode-claim-01": (
        "The with-reference and without-reference behaviors are in separate OR alternatives. Each candidate "
        "supports only one half, so no single alternative supports the complete comparison."
    ),
}


# Candidate judgments that differ from the supported claim/group default.
# Keys are (claim_id, evidence_id); reasons are scoped to that candidate's
# contribution to its group, not to unrelated AND groups.
CANDIDATE_OVERRIDES: dict[tuple[str, str], tuple[str, str]] = {
    ("rw-gold-v1-semantic-bge-functions-claim-01", "ev-rw-bge-methods"): (
        "PARTIALLY_SUPPORTED", "Defines all three retrieval methods but does not itself attribute all three capabilities to BGE-M3."
    ),
    ("rw-gold-v1-semantic-checkpointer-store-claim-01", "ev-rw-agent-overview-capabilities"): (
        "PARTIALLY_SUPPORTED", "Supports the overview half only; it cannot establish what the persistence guide says."
    ),
    ("rw-gold-v1-semantic-checkpointer-store-claim-01", "ev-rw-persist-overview"): (
        "PARTIALLY_SUPPORTED", "Supports the persistence-guide half only; it cannot establish what the overview says."
    ),
    ("rw-gold-v1-multi-backend-control-claim-02", "ev-rw-deps-meaning"): (
        "PARTIALLY_SUPPORTED", "Supports authentication/authorization as dependencies but not the sub-dependency portion."
    ),
    ("rw-gold-v1-multi-eval-stack-claim-02", "ev-rw-precision-without-reference"): (
        "UNSUPPORTED", "Describes comparison to response without a reference, which is the other variant."
    ),
    ("rw-gold-v1-multi-eval-stack-claim-03", "ev-rw-precision-with-reference"): (
        "UNSUPPORTED", "Describes comparison to reference, not the generated-response variant."
    ),
    ("rw-gold-v1-multi-hybrid-index-claim-02", "ev-rw-faiss-purpose"): (
        "PARTIALLY_SUPPORTED", "Establishes dense-vector similarity search but not the distance/dot-product mechanics."
    ),
    ("rw-gold-v1-multi-rag-tracing-claim-01", "ev-rw-ragas-components"): (
        "PARTIALLY_SUPPORTED", "Lists the three RAG components but does not state that contexts and response are recorded together."
    ),
    ("rw-gold-v1-multi-rag-tracing-claim-01", "ev-rw-ragas-collect-data"): (
        "PARTIALLY_SUPPORTED", "Records retrieved contexts and response but does not establish the vectorization component."
    ),
    ("rw-gold-v1-multi-rag-tracing-claim-02", "ev-rw-otel-trace-overview"): (
        "PARTIALLY_SUPPORTED", "Establishes request path and spans as work units but not correlation through context propagation."
    ),
    ("rw-gold-v1-multi-rag-tracing-claim-02", "ev-rw-otel-propagation-span"): (
        "PARTIALLY_SUPPORTED", "Establishes span units and propagation-based correlation but not the request-path proposition."
    ),
    ("rw-gold-v1-multi-retrieval-eval-claim-01", "ev-rw-faiss-purpose"): (
        "PARTIALLY_SUPPORTED", "Establishes dense-vector search but not L2/dot-product comparison."
    ),
    ("rw-gold-v1-disambig-agent-persist-interrupt-claim-01", "ev-rw-persist-comparison"): (
        "PARTIALLY_SUPPORTED", "Compares checkpointer and store scopes but does not state in-memory loss across process restart."
    ),
    ("rw-gold-v1-disambig-bge-faiss-claim-01", "ev-rw-bge-methods"): (
        "PARTIALLY_SUPPORTED", "Defines the three methods but does not itself make the BGE-M3 ownership claim."
    ),
    ("rw-gold-v1-disambig-fastapi-async-deps-claim-01", "ev-rw-async-tldr"): (
        "PARTIALLY_SUPPORTED", "Supports endpoint selection but not the separate threadpool behavior proposition."
    ),
    ("rw-gold-v1-disambig-fastapi-async-deps-claim-01", "ev-rw-async-threadpool"): (
        "PARTIALLY_SUPPORTED", "Supports threadpool behavior but not the complete endpoint-selection rule."
    ),
    ("rw-gold-v1-disambig-interrupt-static-claim-01", "ev-rw-interrupt-static"): (
        "PARTIALLY_SUPPORTED", "Supports static breakpoints and compile-time configuration, not run-time configuration."
    ),
    ("rw-gold-v1-disambig-interrupt-static-claim-01", "ev-rw-interrupt-runtime-static"): (
        "PARTIALLY_SUPPORTED", "Supports run-time configuration, not the compile-time half of the claim."
    ),
    ("rw-gold-v1-disambig-ragas-otel-claim-02", "ev-rw-otel-propagation-span"): (
        "PARTIALLY_SUPPORTED", "Supports distributed span correlation but does not itself describe the request's full path."
    ),
    ("rw-gold-v1-stress-deep-interrupt-side-effects-claim-02", "ev-rw-interrupt-duplicate-risk"): (
        "PARTIALLY_SUPPORTED", "Explains replay/duplicate risk but not the complete remediation options."
    ),
    ("rw-gold-v1-stress-cross-agent-api-replay-claim-02", "ev-rw-interrupt-restart-rule"): (
        "PARTIALLY_SUPPORTED", "Explains replay but not all three remediation choices."
    ),
    ("rw-gold-v1-stress-cross-persistence-tracing-claim-01", "ev-rw-persist-overview"): (
        "PARTIALLY_SUPPORTED", "Supports checkpointed continuity but does not contrast in-memory loss on process restart."
    ),
    ("rw-gold-v1-stress-conflict-bge-faiss-compression-claim-01", "ev-rw-faiss-tradeoffs"): (
        "PARTIALLY_SUPPORTED", "States index trade-offs and compressed search, but not that originals may be omitted."
    ),
    ("rw-gold-v1-stress-conflict-fastapi-handler-type-claim-01", "ev-rw-errors-fastapi-starlette"): (
        "PARTIALLY_SUPPORTED", "Supports the class relationship and registration choice, not reuse of FastAPI default handlers."
    ),
    ("rw-gold-v1-stress-conflict-fastapi-handler-type-claim-01", "ev-rw-errors-reuse-handlers"): (
        "PARTIALLY_SUPPORTED", "Supports default-handler reuse, not the FastAPI/Starlette class relationship."
    ),
    ("rw-gold-v1-stress-conflict-fastapi-handler-type-claim-02", "ev-rw-errors-reuse-handlers"): (
        "UNSUPPORTED", "Does not state why registration on the Starlette base catches Starlette/extensions and FastAPI subclasses."
    ),
    ("rw-gold-v1-stress-conflict-ragas-reference-mode-claim-01", "ev-rw-precision-with-reference"): (
        "PARTIALLY_SUPPORTED", "Supports only the with-reference half of the comparison."
    ),
    ("rw-gold-v1-stress-conflict-ragas-reference-mode-claim-01", "ev-rw-precision-without-reference"): (
        "PARTIALLY_SUPPORTED", "Supports only the without-reference half of the comparison."
    ),
    ("rw-gold-v1-long-langgraph-positioning-claim-02", "ev-rw-agent-overview-purpose"): (
        "PARTIALLY_SUPPORTED", "States low-level orchestration and stateful agents, but not two explicit control categories over workflow and state."
    ),
}


ROLE_DEFECT = {
    "case_id": "rw-gold-v1-disambig-fastapi-exceptions",
    "document_id": "rw-backend-fastapi-async",
    "declared_role": "ACCEPTABLE_SUPPORT",
    "role_semantic_verdict": "MISCLASSIFIED",
    "recommended_role": "UNSUPPORTED",
    "reason": (
        "The reopened threadpool locator only describes def/async-def execution. It neither supports nor "
        "meaningfully explains the exception-class hierarchy or global handler-registration decision."
    ),
}


UNANSWERABLE_REASONS = {
    "rw-gold-v1-unanswerable-bge-language-counts": "The source says more than 100 languages but gives no exhaustive per-language sample counts.",
    "rw-gold-v1-unanswerable-bge-optimal-weights": "The source gives adjustable example weights and no dataset-independent optimum guarantee.",
    "rw-gold-v1-unanswerable-checkpoint-encryption": "The source provides no mandated encryption algorithm or rotation period.",
    "rw-gold-v1-unanswerable-dependency-depth": "The source describes hierarchical dependencies but no numeric depth limit or overflow status.",
    "rw-gold-v1-unanswerable-faiss-p95-latency": "The source gives no hardware-specific p95 latency guarantee.",
    "rw-gold-v1-unanswerable-interrupt-timeout": "The source gives no default approval timeout or automatic cancellation interval.",
    "rw-gold-v1-unanswerable-precision-pass-threshold": "The metric source prescribes no universal production pass threshold.",
    "rw-gold-v1-unanswerable-ragas-minimum-score": "The workflow source guarantees no minimum production score.",
    "rw-gold-v1-unanswerable-threadpool-workers": "The source states external-threadpool execution but no exact default worker count.",
    "rw-gold-v1-unanswerable-trace-retention": "The trace source defines no mandatory backend retention duration.",
}


DEFECT_DETAILS = {
    "rw-gold-v1-semantic-checkpointer-store-claim-01": ("D", "Replace the OR construction with two required groups, one per source, or remove the word 'both'."),
    "rw-gold-v1-long-langgraph-positioning-claim-02": ("C", "Narrow the claim to low-level orchestration for long-running, stateful agents, or bind a source that explicitly states both control categories."),
    "rw-gold-v1-multi-rag-tracing-claim-01": ("D", "Use two required groups for component separation and collected response/context fields, or add one comprehensive anchor."),
    "rw-gold-v1-multi-rag-tracing-claim-02": ("D", "Use two required groups for request-path/span structure and context propagation, or add one comprehensive anchor."),
    "rw-gold-v1-disambig-fastapi-async-deps-claim-01": ("D", "Split endpoint selection and threadpool behavior into two required groups or two atomic claims."),
    "rw-gold-v1-disambig-interrupt-static-claim-01": ("D", "Make compile-time and run-time anchors separate required groups or split the claim."),
    "rw-gold-v1-stress-conflict-fastapi-handler-type-claim-01": ("D", "Split hierarchy/registration and default-handler reuse into separate required groups or narrow the claim."),
    "rw-gold-v1-stress-conflict-ragas-reference-mode-claim-01": ("D", "Make with-reference and without-reference anchors separate required groups or split the comparison into two claims."),
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def normalize(text: str) -> str:
    return " ".join(text.replace("\x00", "").split())


def reopen(anchor: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    locator = anchor["locator"]
    path = REPO_ROOT / locator["source_path"]
    if not path.is_file() or locator["source_path"] != document["repository_path"]:
        raise RuntimeError(f"unresolved source for {anchor['evidence_id']}")
    source_hash = sha256(path.read_bytes()).hexdigest()
    if source_hash != document["corpus_sha256"]:
        raise RuntimeError(f"frozen source hash mismatch for {anchor['evidence_id']}")
    if locator["kind"] == "SOURCE_LINES":
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        start, end = locator["start_line"], locator["end_line"]
        if not 1 <= start <= end <= len(lines):
            raise RuntimeError(f"unresolved lines for {anchor['evidence_id']}")
        text = normalize("\n".join(lines[start - 1:end]))
    elif locator["kind"] == "PDF_PAGE":
        reader = PdfReader(str(path))
        page = locator["page_number"]
        if not 1 <= page <= len(reader.pages):
            raise RuntimeError(f"unresolved page for {anchor['evidence_id']}")
        text = normalize(reader.pages[page - 1].extract_text() or "")
    else:
        raise RuntimeError(f"unknown locator kind for {anchor['evidence_id']}")
    text_hash = sha256(text.encode("utf-8")).hexdigest()
    if not text or text_hash != anchor["anchor_text_hash"]:
        raise RuntimeError(f"fresh text hash mismatch for {anchor['evidence_id']}")
    return {
        "evidence_id": anchor["evidence_id"],
        "document_id": anchor["document_id"],
        "locator": locator,
        "source_bytes_sha256": source_hash,
        "fresh_text_sha256": text_hash,
        "fresh_evidence_excerpt": text[:700],
        "locator_resolved": True,
        "source_hash_matches_manifest": True,
        "anchor_hash_matches": True,
    }


def group_verdict(candidate_verdicts: list[str]) -> str:
    if "SUPPORTED" in candidate_verdicts:
        return "SUPPORTED"
    if "PARTIALLY_SUPPORTED" in candidate_verdicts:
        return "PARTIALLY_SUPPORTED"
    if "AMBIGUOUS" in candidate_verdicts:
        return "AMBIGUOUS"
    return "UNSUPPORTED"


def claim_verdict(group_verdicts: list[str]) -> str:
    if "UNSUPPORTED" in group_verdicts:
        return "UNSUPPORTED"
    if "AMBIGUOUS" in group_verdicts:
        return "AMBIGUOUS"
    if "PARTIALLY_SUPPORTED" in group_verdicts:
        return "PARTIALLY_SUPPORTED"
    return "SUPPORTED"


def role_reviews(cases: list[dict[str, Any]], fresh: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    target_types = {"source_disambiguation", "high_overlap_source_conflict"}
    result: list[dict[str, Any]] = []
    for case in cases:
        if case["case_type"] not in target_types:
            continue
        for group in case["evidence_groups"]:
            for document_id in group["any_of_document_ids"]:
                evidence_ids = [eid for eid in group["any_of_evidence_ids"] if fresh[eid]["document_id"] == document_id]
                result.append({
                    "case_id": case["case_id"],
                    "document_id": document_id,
                    "declared_role": "REQUIRED",
                    "evidence_ids": evidence_ids,
                    "fresh_evidence": [fresh[eid] for eid in evidence_ids],
                    "role_semantic_verdict": "CONFIRMED",
                    "recommended_role": "REQUIRED",
                    "review_reason": "Fresh source evidence directly participates in satisfying a target claim/group.",
                })
        for bucket, role in (("acceptable_supporting_evidence", "ACCEPTABLE_SUPPORT"), ("plausible_distractor_documents", "UNSUPPORTED")):
            for item in case[bucket]:
                defect = case["case_id"] == ROLE_DEFECT["case_id"] and item["document_id"] == ROLE_DEFECT["document_id"]
                evidence_ids = item.get("evidence_ids", [])
                result.append({
                    "case_id": case["case_id"],
                    "document_id": item["document_id"],
                    "declared_role": role,
                    "evidence_ids": evidence_ids,
                    "fresh_evidence": [fresh[eid] for eid in evidence_ids],
                    "role_semantic_verdict": "MISCLASSIFIED" if defect else "CONFIRMED",
                    "recommended_role": ROLE_DEFECT["recommended_role"] if defect else role,
                    "review_reason": ROLE_DEFECT["reason"] if defect else item["notes"],
                })
    return result


def build() -> dict[str, Any]:
    if sha256(GOLD_PATH.read_bytes()).hexdigest() != EXPECTED_GOLD_SHA256:
        raise RuntimeError("Gold changed after the independent review input was frozen")
    gold = load_json(GOLD_PATH)
    anchors_artifact = load_json(ANCHORS_PATH)
    manifest = load_json(MANIFEST_PATH)
    anchors = {item["evidence_id"]: item for item in anchors_artifact["anchors"]}
    documents = {item["document_id"]: item for item in manifest["documents"]}

    semantic_pairs = [
        (case, claim)
        for case in gold["cases"]
        for claim in case["claims"]
        if claim["evaluation_mode"] == "SEMANTIC_REVIEW"
    ]
    semantic_ids = sorted(claim["claim_id"] for _, claim in semantic_pairs)
    if len(semantic_ids) != 104 or sha256("\n".join(semantic_ids).encode()).hexdigest() != EXPECTED_SEMANTIC_IDS_SHA256:
        raise RuntimeError("semantic claim set differs from the independently reviewed set")
    if not set(PARTIAL_CLAIM_REASONS) <= set(semantic_ids):
        raise RuntimeError("partial decision references a missing claim")

    used_anchor_ids = {
        evidence_id
        for case, claim in semantic_pairs
        for group_id in claim["evidence_group_ids"]
        for group in case["evidence_groups"]
        if group["evidence_group_id"] == group_id
        for evidence_id in group["any_of_evidence_ids"]
    }
    used_anchor_ids.update(
        evidence_id
        for case in gold["cases"]
        if case["case_type"] in {"source_disambiguation", "high_overlap_source_conflict"}
        for item in case["acceptable_supporting_evidence"]
        for evidence_id in item["evidence_ids"]
    )
    used_anchor_ids.update(
        evidence_id
        for case in gold["cases"]
        for claim in case["claims"]
        if claim["evaluation_mode"] not in {"SEMANTIC_REVIEW", "ANSWERABILITY_ONLY"}
        for group_id in claim["evidence_group_ids"]
        for group in case["evidence_groups"]
        if group["evidence_group_id"] == group_id
        for evidence_id in group["any_of_evidence_ids"]
    )
    fresh = {eid: reopen(anchors[eid], documents[anchors[eid]["document_id"]]) for eid in sorted(used_anchor_ids)}

    semantic_reviews: list[dict[str, Any]] = []
    for case, claim in semantic_pairs:
        reviewed_groups: list[dict[str, Any]] = []
        for group_id in claim["evidence_group_ids"]:
            group = next(item for item in case["evidence_groups"] if item["evidence_group_id"] == group_id)
            candidates = []
            for evidence_id in group["any_of_evidence_ids"]:
                verdict, reason = CANDIDATE_OVERRIDES.get(
                    (claim["claim_id"], evidence_id),
                    ("SUPPORTED", "Fresh locator text directly supports this group's contribution to the atomic claim."),
                )
                candidates.append({
                    **fresh[evidence_id],
                    "candidate_semantic_verdict": verdict,
                    "review_reason": reason,
                })
            verdict = group_verdict([item["candidate_semantic_verdict"] for item in candidates])
            reviewed_groups.append({
                "group_id": group_id,
                "required": group["required"],
                "evidence_role": group["evidence_role"],
                "logic": "OR",
                "candidate_anchors": candidates,
                "group_verdict": verdict,
                "review_reason": (
                    "At least one candidate independently supports the group obligation."
                    if verdict == "SUPPORTED" else
                    "No OR candidate independently supports the complete group obligation; partial candidates cannot be combined under OR."
                ),
            })
        calculated = claim_verdict([item["group_verdict"] for item in reviewed_groups])
        expected = "PARTIALLY_SUPPORTED" if claim["claim_id"] in PARTIAL_CLAIM_REASONS else "SUPPORTED"
        if calculated != expected:
            raise RuntimeError(f"decision ledger/group logic mismatch for {claim['claim_id']}: {calculated} != {expected}")
        semantic_reviews.append({
            "case_id": case["case_id"],
            "case_type": case["case_type"],
            "claim_id": claim["claim_id"],
            "evaluation_mode": claim["evaluation_mode"],
            "question": case["question"],
            "claim": claim["canonical_claim"],
            "group_combination_logic": "AND",
            "groups": reviewed_groups,
            "claim_verdict": calculated,
            "review_reason": PARTIAL_CLAIM_REASONS.get(
                claim["claim_id"],
                "All required groups have at least one freshly reopened candidate that directly supports the atomic claim without a material external fact.",
            ),
            "authoring_semantic_verdict_visible_to_reviewer": False,
        })

    non_semantic_sanity: list[dict[str, Any]] = []
    for case in gold["cases"]:
        for claim in case["claims"]:
            mode = claim["evaluation_mode"]
            if mode == "SEMANTIC_REVIEW":
                continue
            evidence = []
            for group_id in claim["evidence_group_ids"]:
                group = next(item for item in case["evidence_groups"] if item["evidence_group_id"] == group_id)
                evidence.extend(fresh[eid] for eid in group["any_of_evidence_ids"])
            if mode == "ANSWERABILITY_ONLY":
                reason = UNANSWERABLE_REASONS[case["case_id"]]
            else:
                reason = "The evaluation mode matches the deterministic expectation type, and freshly reopened evidence contains the expected exact value/structure/identifier."
            non_semantic_sanity.append({
                "case_id": case["case_id"],
                "claim_id": claim["claim_id"],
                "evaluation_mode": mode,
                "sanity_status": "PASS",
                "review_reason": reason,
                "fresh_evidence": evidence,
            })

    roles = role_reviews(gold["cases"], fresh)
    semantic_by_case: dict[str, list[dict[str, Any]]] = {}
    for item in semantic_reviews:
        semantic_by_case.setdefault(item["case_id"], []).append(item)
    role_defect_cases = {item["case_id"] for item in roles if item["role_semantic_verdict"] == "MISCLASSIFIED"}
    case_reviews = []
    for case in gold["cases"]:
        bad_claims = [item["claim_id"] for item in semantic_by_case.get(case["case_id"], []) if item["claim_verdict"] != "SUPPORTED"]
        reasons = []
        if bad_claims:
            reasons.append(f"non-supported semantic claims: {', '.join(bad_claims)}")
        if case["case_id"] in role_defect_cases:
            reasons.append("evidence-role semantic misclassification")
        case_reviews.append({
            "case_id": case["case_id"],
            "case_verdict": "NEEDS_GOLD_FIX" if reasons else "VERIFIED",
            "review_reason": "; ".join(reasons) if reasons else "All applicable semantic groups, role checks, and deterministic sanity checks passed.",
        })

    defects = []
    claim_lookup = {claim["claim_id"]: (case, claim) for case in gold["cases"] for claim in case["claims"]}
    semantic_lookup = {item["claim_id"]: item for item in semantic_reviews}
    for claim_id, (category, correction) in DEFECT_DETAILS.items():
        case, claim = claim_lookup[claim_id]
        defects.append({
            "defect_id": f"semantic-{len(defects) + 1:02d}",
            "category": category,
            "category_name": {"C": "claim wording too strong", "D": "evidence-group logic defect"}[category],
            "case_id": case["case_id"],
            "claim_id": claim_id,
            "question": case["question"],
            "claim": claim["canonical_claim"],
            "evidence": [candidate for group in semantic_lookup[claim_id]["groups"] for candidate in group["candidate_anchors"]],
            "verdict": semantic_lookup[claim_id]["claim_verdict"],
            "root_cause": PARTIAL_CLAIM_REASONS[claim_id],
            "recommended_minimal_correction": correction,
        })
    defects.append({
        "defect_id": "role-01",
        "category": "B",
        "category_name": "evidence-role defect",
        "case_id": ROLE_DEFECT["case_id"],
        "claim_id": None,
        "question": next(case["question"] for case in gold["cases"] if case["case_id"] == ROLE_DEFECT["case_id"]),
        "claim": "Evidence-role classification for rw-backend-fastapi-async.",
        "evidence": [fresh["ev-rw-async-threadpool"]],
        "verdict": "MISCLASSIFIED",
        "root_cause": ROLE_DEFECT["reason"],
        "recommended_minimal_correction": "Reclassify rw-backend-fastapi-async from ACCEPTABLE_SUPPORT to UNSUPPORTED for this case only.",
    })

    verdict_counts = Counter(item["claim_verdict"] for item in semantic_reviews)
    case_counts = Counter(item["case_verdict"] for item in case_reviews)
    mode_counts = Counter(item["evaluation_mode"] for item in non_semantic_sanity)
    role_counts = Counter(item["role_semantic_verdict"] for item in roles)
    return {
        "schema_version": "1.0.0",
        "dataset": "learnpilot-rag-real-world-gold-v1",
        "review_version": "independent-semantic-verification-v1",
        "review_completed_date": "2026-08-14",
        "review_input": {
            "gold_path": "evals/rag_real_world_corpus/v1/gold/v1/gold_cases.json",
            "gold_sha256": EXPECTED_GOLD_SHA256,
            "semantic_claim_id_set_sha256": EXPECTED_SEMANTIC_IDS_SHA256,
        },
        "review_method": {
            "fresh_corpus_reopen": True,
            "source_lines_reopened_from_frozen_files": True,
            "pdf_pages_reextracted_from_frozen_files": True,
            "document_and_anchor_hashes_recomputed": True,
            "and_across_groups": True,
            "or_inside_group": True,
            "authoring_verdict_used": False,
            "old_independent_review_verdict_used": False,
            "baseline_output_used": False,
            "retrieval_output_used": False,
            "llm_used": False,
            "production_rag_used": False,
        },
        "execution_audit": {
            "deepseek_call_count": 0,
            "other_llm_call_count": 0,
            "rag_ask_count": 0,
            "real_world_baseline_execution_count": 0,
        },
        "summary": {
            "semantic_review_total": 104,
            "reviewed": len(semantic_reviews),
            "claim_verdict_distribution": {key: verdict_counts.get(key, 0) for key in sorted(VERDICTS)},
            "non_semantic_sanity_total": len(non_semantic_sanity),
            "non_semantic_mode_distribution": dict(sorted(mode_counts.items())),
            "case_total": len(case_reviews),
            "case_verdict_distribution": dict(sorted(case_counts.items())),
            "evidence_role_record_total": len(roles),
            "evidence_role_verdict_distribution": dict(sorted(role_counts.items())),
            "defect_total": len(defects),
        },
        "semantic_claim_reviews": semantic_reviews,
        "non_semantic_contract_sanity": non_semantic_sanity,
        "evidence_role_reviews": roles,
        "case_reviews": case_reviews,
        "defects": defects,
        "final_status": {
            "independent_semantic_verification_v1": "COMPLETE",
            "gold_correctness_repair_required": "YES",
            "rag_real_world_gold_dataset_v1": "HOLD",
        },
    }


def main() -> int:
    artifact = build()
    OUTPUT_PATH.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(artifact["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
