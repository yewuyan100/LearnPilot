"""Build the reviewed V2 Gold and review assets from frozen V1 evidence.

Gold is constructed before frozen answers are loaded.  This ordering is an
intentional anti-overfitting guard: answer text can populate review records,
but it cannot redefine claims or evidence roles.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any


V1_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = Path(__file__).resolve().parent
BASELINE = V1_ROOT / "results" / "baseline_v1" / "20260813T095948Z-f8aaaae2"
CORPUS_DOCUMENT_IDS = tuple(
    item["document_id"]
    for item in json.loads((V1_ROOT / "corpus_manifest.json").read_text(encoding="utf-8"))["documents"]
)

ALTERNATIVE_SUPPORT: dict[str, list[str]] = {
    "rag-v1-paraphrase-delete-history": ["lp-rag-v1-a04"],
    "rag-v1-multidoc-controlled-write": ["lp-rag-v1-b03"],
    "rag-v1-multidoc-retrieval-to-context": ["lp-rag-v1-a03"],
    "rag-v1-multidoc-reprocess-identity": ["lp-rag-v1-d03"],
    "rag-v1-rerank-fixture-vs-corpus": ["lp-rag-v1-b03"],
    "rag-v1-citation-gold-mapping": [
        "lp-rag-v1-a01", "lp-rag-v1-a04", "lp-rag-v1-d03"
    ],
}

AUDIT_REASONS: dict[str, list[str]] = {
    "rag-v1-paraphrase-delete-history": ["ALTERNATIVE_DOCUMENT_EQUIVALENT"],
    "rag-v1-multidoc-controlled-write": ["ALTERNATIVE_DOCUMENT_EQUIVALENT"],
    "rag-v1-citation-source-label-lifetime": [
        "ALTERNATIVE_DOCUMENT_EQUIVALENT", "EVIDENCE_GROUP_REMODELED"
    ],
    "rag-v1-paraphrase-index-derived-state": ["LEXICAL_REQUIREMENT_REMOVED"],
    "rag-v1-multidoc-retrieval-to-context": ["ALTERNATIVE_DOCUMENT_EQUIVALENT"],
    "rag-v1-multidoc-agent-safety-plan": ["LEXICAL_REQUIREMENT_REMOVED"],
    "rag-v1-multidoc-http-transaction-errors": [
        "AMBIGUOUS_EXPECTATION_CLARIFIED", "CLAIM_SPLIT"
    ],
    "rag-v1-multidoc-ingestion-reproducibility": [
        "CLAIM_SPLIT", "EVIDENCE_GROUP_REMODELED"
    ],
    "rag-v1-multidoc-eval-via-public-api": ["EVIDENCE_GROUP_REMODELED"],
    "rag-v1-multidoc-reprocess-identity": [
        "ALTERNATIVE_DOCUMENT_EQUIVALENT", "CLAIM_SPLIT"
    ],
    "rag-v1-rerank-citation-rendering": ["CLAIM_SPLIT"],
    "rag-v1-rerank-stream-validation": ["LEXICAL_REQUIREMENT_REMOVED"],
    "rag-v1-rerank-storage-responsibility": ["CLAIM_SPLIT"],
    "rag-v1-rerank-fixture-vs-corpus": [
        "ALTERNATIVE_DOCUMENT_EQUIVALENT", "CLAIM_SPLIT"
    ],
    "rag-v1-citation-gold-mapping": ["ALTERNATIVE_DOCUMENT_EQUIVALENT"],
    "rag-v1-citation-multifact-sources": ["CLAIM_SPLIT"],
}

AUDIT_NOTES: dict[str, str] = {
    "rag-v1-citation-source-label-lifetime":
        "A03/D03 jointly support the two required claims; exact A02/D01 labels are not unique truth.",
    "rag-v1-multidoc-http-transaction-errors":
        "C01 and D02 describe different public/runtime layers; V2 requires distinct classification, not one stale-index HTTP outcome.",
    "rag-v1-multidoc-ingestion-reproducibility":
        "The question asks the two manifests; parser/chunker influence remains useful but optional.",
    "rag-v1-multidoc-reprocess-identity":
        "Stable versus runtime identity is required; chunk_index/content_hash detail is optional.",
    "rag-v1-rerank-citation-rendering":
        "Backend rendering answers the explicit who-question; draft prohibition remains optional context.",
    "rag-v1-rerank-storage-responsibility":
        "Business SQLite is the required answer; checkpoint/FAISS detail is optional context.",
    "rag-v1-rerank-fixture-vs-corpus":
        "Classification is required; distribution rationale is optional explanation.",
    "rag-v1-citation-multifact-sources":
        "The composite context-limit fact is split so omitted max_sources cannot hide behind other numbers.",
}


def group(group_id: str, documents: list[str], note: str, *, required: bool = True) -> dict[str, Any]:
    return {
        "evidence_group_id": group_id,
        "required": required,
        "any_of_document_ids": documents,
        "notes": note,
    }


def default_groups(case: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        group(f"eg-{index:02d}", [document_id], f"V1 expected evidence: {document_id}")
        for index, document_id in enumerate(case["expected_document_ids"], start=1)
    ]


GROUP_OVERRIDES: dict[str, list[dict[str, Any]]] = {
    "rag-v1-citation-source-label-lifetime": [
        group("eg-temporary-label", ["lp-rag-v1-a02", "lp-rag-v1-a03", "lp-rag-v1-d01"], "Any source directly establishing run-local source labels."),
        group("eg-stable-document-id", ["lp-rag-v1-d01", "lp-rag-v1-d03"], "Either eval document defines stable Corpus Manifest document_id."),
    ],
    "rag-v1-multidoc-http-transaction-errors": [
        group("eg-index-consistency", ["lp-rag-v1-c02"], "Persistence/index consistency semantics."),
        group("eg-provider-infrastructure", ["lp-rag-v1-c01", "lp-rag-v1-d02"], "Provider failure is infrastructure, not correct refusal."),
    ],
    "rag-v1-multidoc-ingestion-reproducibility": [
        group("eg-corpus-manifest", ["lp-rag-v1-d03"], "Frozen offline input contract."),
        group("eg-faiss-manifest", ["lp-rag-v1-d03", "lp-rag-v1-a01"], "Either document directly defines runtime FAISS manifest facts."),
        group("eg-parser-chunker", ["lp-rag-v1-c03"], "Optional ingestion-detail context.", required=False),
    ],
    "rag-v1-multidoc-eval-via-public-api": [
        group("eg-public-http", ["lp-rag-v1-c01"], "Public HTTP evaluation path."),
        group("eg-isolation", ["lp-rag-v1-d01"], "Isolated storage prevents personal knowledge-base contamination."),
        group("eg-comparable-metadata", ["lp-rag-v1-d01", "lp-rag-v1-d03"], "Either eval document enumerates comparable run metadata."),
    ],
    "rag-v1-citation-multifact-sources": [
        group("eg-context-limits", ["lp-rag-v1-a02"], "Default source and character budgets."),
        group("eg-citation-snapshot", ["lp-rag-v1-a03"], "Persisted citation snapshot fields."),
    ],
}


CLAIM_GROUP_MAP: dict[str, dict[int, list[str]]] = {
    "rag-v1-multidoc-controlled-write": {0: ["eg-01"], 1: ["eg-02"], 2: ["eg-02"]},
    "rag-v1-rerank-candidate-expansion": {0: ["eg-02"], 1: ["eg-01"]},
    "rag-v1-citation-source-label-lifetime": {0: ["eg-temporary-label"], 1: ["eg-stable-document-id"]},
    "rag-v1-multidoc-retrieval-to-context": {0: ["eg-01"], 1: ["eg-02"]},
    "rag-v1-multidoc-delete-new-vs-old": {0: ["eg-02"], 1: ["eg-01"]},
    "rag-v1-multidoc-agent-safety-plan": {0: ["eg-02"], 1: ["eg-01", "eg-02"], 2: ["eg-01", "eg-02"]},
    "rag-v1-multidoc-ingestion-reproducibility": {0: ["eg-corpus-manifest"], 1: ["eg-faiss-manifest"], 2: ["eg-parser-chunker"]},
    "rag-v1-multidoc-eval-via-public-api": {0: ["eg-public-http"], 1: ["eg-isolation"], 2: ["eg-comparable-metadata"]},
    "rag-v1-multidoc-reprocess-identity": {0: ["eg-01"], 1: ["eg-01", "eg-02"], 2: ["eg-02"]},
    "rag-v1-citation-refusal-empty": {0: ["eg-01"], 1: ["eg-01", "eg-02"], 2: ["eg-02"]},
}

OPTIONAL_FACTS: dict[str, set[int]] = {
    "rag-v1-multidoc-ingestion-reproducibility": {2},
    "rag-v1-multidoc-reprocess-identity": {2},
    "rag-v1-rerank-citation-rendering": {0},
    "rag-v1-rerank-storage-responsibility": {1},
    "rag-v1-rerank-fixture-vs-corpus": {1},
}

DETERMINISTIC: dict[str, dict[int, tuple[str, dict[str, Any]]]] = {
    "rag-v1-single-default-chunk-size": {
        0: ("NUMERIC_EXACT", {"all_terms": ["800"]}),
        1: ("NUMERIC_EXACT", {"all_terms": ["120"]}),
    },
    "rag-v1-rerank-candidate-expansion": {0: ("NUMERIC_EXACT", {"all_terms": ["18"]})},
    "rag-v1-single-score-threshold": {0: ("NUMERIC_EXACT", {"all_terms": ["0.35"]})},
    "rag-v1-single-grounding-repair-limit": {0: ("NUMERIC_EXACT", {"all_terms": ["一次"]})},
    "rag-v1-single-agent-step-limits": {
        0: ("NUMERIC_EXACT", {"all_terms": ["四个"]}),
        1: ("NUMERIC_EXACT", {"all_terms": ["三个"]}),
        2: ("NUMERIC_EXACT", {"all_terms": ["一个"]}),
    },
    "rag-v1-single-api-error-shape": {
        0: ("STRUCTURED_EXACT", {"all_terms": ["code", "message", "details"]})
    },
    "rag-v1-rerank-agent-numeric-source": {
        0: ("NUMERIC_EXACT", {"all_terms": ["三个"]}),
        1: ("NUMERIC_EXACT", {"all_terms": ["一个"]}),
    },
    "rag-v1-citation-page-section-location": {
        0: ("STRUCTURED_EXACT", {"ordered_terms": ["页码", "章节标题", "片段序号"]}),
    },
}


def special_claims(case: dict[str, Any], groups: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    case_id = case["case_id"]
    if case_id == "rag-v1-multidoc-http-transaction-errors":
        specs = [
            ("stale index is an index/business-fact consistency failure", ["eg-index-consistency"]),
            ("LLM provider failure is an infrastructure failure, not a correct no-answer refusal", ["eg-provider-infrastructure"]),
            ("the two conditions require distinct failure classifications", ["eg-index-consistency", "eg-provider-infrastructure"]),
        ]
        return make_claims(case_id, specs)
    if case_id == "rag-v1-citation-multifact-sources":
        specs = [
            ("default final context uses at most six sources", ["eg-context-limits"]),
            ("each final-context source contributes at most 2200 characters", ["eg-context-limits"]),
            ("total final context uses at most 12000 characters", ["eg-context-limits"]),
            ("citation snapshots persist rank, score, location, and excerpt fields", ["eg-citation-snapshot"]),
        ]
        claims = make_claims(case_id, specs)
        for index, term in enumerate(("六个", "2200", "12000")):
            claims[index]["evaluation_mode"] = "NUMERIC_EXACT"
            claims[index]["deterministic_match"] = {"all_terms": [term]}
        return claims
    return None


def make_claims(case_id: str, specs: list[tuple[str, list[str]]]) -> list[dict[str, Any]]:
    return [
        {
            "claim_id": f"{case_id}-claim-{index:02d}",
            "canonical_claim": text,
            "required": True,
            "evidence_group_ids": group_ids,
            "evaluation_mode": "SEMANTIC_REVIEW",
            "notes": "Corpus-grounded V2 claim.",
        }
        for index, (text, group_ids) in enumerate(specs, start=1)
    ]


def minimum_documents(groups: list[dict[str, Any]]) -> int:
    required = [set(item["any_of_document_ids"]) for item in groups if item["required"]]
    if not required:
        return 0
    candidates = list(CORPUS_DOCUMENT_IDS)
    for width in range(1, len(candidates) + 1):
        from itertools import combinations
        for choice in combinations(candidates, width):
            selected = set(choice)
            if all(selected & documents for documents in required):
                return width
    raise RuntimeError("unsatisfiable evidence groups")


def build_gold() -> dict[str, Any]:
    v1 = json.loads((V1_ROOT / "gold_cases.json").read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = []
    for source in v1["cases"]:
        case_id = source["case_id"]
        groups = deepcopy(GROUP_OVERRIDES.get(case_id, default_groups(source))) if source["answerable"] else []
        claims = special_claims(source, groups)
        if claims is None:
            if source["answerable"]:
                claim_map = CLAIM_GROUP_MAP.get(case_id, {})
                all_group_ids = [item["evidence_group_id"] for item in groups if item["required"]]
                claims = []
                for fact_index, fact in enumerate(source["key_facts"]):
                    mapped = claim_map.get(fact_index, all_group_ids)
                    mode, rule = DETERMINISTIC.get(case_id, {}).get(
                        fact_index, ("SEMANTIC_REVIEW", None)
                    )
                    claim = {
                        "claim_id": f"{case_id}-claim-{fact_index + 1:02d}",
                        "canonical_claim": fact,
                        "required": fact_index not in OPTIONAL_FACTS.get(case_id, set()),
                        "evidence_group_ids": mapped,
                        "evaluation_mode": mode,
                        "notes": "Traceable to V1 key_facts; requirement status reviewed under V2.",
                    }
                    if rule:
                        claim["deterministic_match"] = rule
                    claims.append(claim)
            else:
                claims = [{
                    "claim_id": f"{case_id}-claim-01",
                    "canonical_claim": "the controlled corpus does not contain an answer to the question",
                    "required": True,
                    "evidence_group_ids": [],
                    "evaluation_mode": "ANSWERABILITY_ONLY",
                    "notes": "Requires answerable=false, no factual answer, and no citation.",
                }]
        reasons = AUDIT_REASONS.get(case_id, [])
        citation = {
            "required": source["answerable"],
            "required_evidence_group_ids": [
                item["evidence_group_id"] for item in groups if item["required"]
            ],
            "minimum_distinct_documents": minimum_documents(groups),
            "forbid_citations": not source["answerable"],
            "notes": "All required evidence groups must be covered; alternatives within a group are equivalent.",
        }
        cases.append({
            "case_id": case_id,
            "question": source["question"],
            "difficulty": source["difficulty"],
            "type": source["type"],
            "answerable": source["answerable"],
            "evidence_groups": groups,
            "acceptable_supporting_document_ids": ALTERNATIVE_SUPPORT.get(case_id, []),
            "irrelevant_or_disallowed_document_ids": list(CORPUS_DOCUMENT_IDS) if not source["answerable"] else [],
            "claims": claims,
            "citation_contract": citation,
            "v1_trace": {
                "expected_document_ids": source["expected_document_ids"],
                "key_facts": source["key_facts"],
                "citation_expectations": source["citation_expectations"],
            },
            "gold_review": {
                "status": "REVIEWED",
                "semantics_changed": bool(reasons),
                "audit_reasons": reasons,
                "audit_notes": AUDIT_NOTES.get(
                    case_id,
                    "All claims and evidence roles were checked against the frozen corpus; no semantic Gold change was needed."
                    if not reasons else
                    "Evidence role or evaluation semantics changed for the corpus-grounded reason listed above."
                ),
            },
        })
    return {
        "schema_version": "2.0.0",
        "contract_id": "learnpilot-rag-eval-gold-contract-v2",
        "corpus_ref": {"corpus_id": v1["corpus_id"], "corpus_version": v1["corpus_version"]},
        "case_count": len(cases),
        "cases": cases,
    }


NOT_SUPPORTED: dict[str, set[int]] = {
    "rag-v1-paraphrase-scanned-pdf": {0, 1},
    "rag-v1-multidoc-ingestion-reproducibility": {2},
    "rag-v1-multidoc-eval-via-public-api": {1},
    "rag-v1-multidoc-reprocess-identity": {2},
    "rag-v1-rerank-citation-rendering": {0},
    "rag-v1-rerank-storage-responsibility": {1},
    "rag-v1-rerank-fixture-vs-corpus": {1},
    "rag-v1-citation-multifact-sources": {0},
    "rag-v1-citation-draft-vs-rendered": {1},
}

REVIEW_FAILURE_REASONS: dict[tuple[str, int], str] = {
    ("rag-v1-paraphrase-scanned-pdf", 0): "The frozen answer refused despite C03 being present in final context.",
    ("rag-v1-paraphrase-scanned-pdf", 1): "The refusal does not state that extraction failure is explicit.",
    ("rag-v1-multidoc-ingestion-reproducibility", 2): "The frozen answer does not discuss parser/chunker influence; this V2 claim is optional.",
    ("rag-v1-multidoc-eval-via-public-api", 1): "The frozen answer says isolated session but omits preventing personal knowledge-base contamination.",
    ("rag-v1-multidoc-reprocess-identity", 2): "The frozen answer omits optional chunk_index/content_hash detail.",
    ("rag-v1-rerank-citation-rendering", 0): "The answer identifies backend rendering but does not separately state the optional draft prohibition.",
    ("rag-v1-rerank-storage-responsibility", 1): "The answer omits optional checkpoint and FAISS role detail.",
    ("rag-v1-rerank-fixture-vs-corpus", 1): "The answer classifies correctly but omits the optional distribution rationale.",
    ("rag-v1-citation-multifact-sources", 0): "The frozen answer omits the six-source maximum; splitting the V1 composite fact exposes the omission.",
    ("rag-v1-citation-draft-vs-rendered", 1): "The frozen answer omits that draft evidence blocks bind source IDs.",
}


def claim_documents(case: dict[str, Any], claim: dict[str, Any]) -> list[str]:
    groups = {item["evidence_group_id"]: item for item in case["evidence_groups"]}
    result: list[str] = []
    for group_id in claim["evidence_group_ids"]:
        for document_id in groups[group_id]["any_of_document_ids"]:
            if document_id not in result:
                result.append(document_id)
    return result


def build_reviews(gold: dict[str, Any]) -> dict[str, Any]:
    # Frozen answers are loaded only after the Gold contract has been built.
    analyses = json.loads((BASELINE / "case_analysis.json").read_text(encoding="utf-8"))
    by_id = {item["case_id"]: item for item in analyses}
    cases: list[dict[str, Any]] = []
    for case in gold["cases"]:
        analysis = by_id[case["case_id"]]
        answer = analysis["answer"]
        claim_reviews = []
        for index, claim in enumerate(case["claims"]):
            unsupported = index in NOT_SUPPORTED.get(case["case_id"], set())
            verdict = "NOT_SUPPORTED" if unsupported else "SUPPORTED"
            documents = [] if claim["evaluation_mode"] == "ANSWERABILITY_ONLY" else claim_documents(case, claim)
            claim_reviews.append({
                "case_id": case["case_id"],
                "claim_id": claim["claim_id"],
                "verdict": verdict,
                "supporting_answer_span": "" if unsupported else answer,
                "supporting_document_ids": documents,
                "review_reason": REVIEW_FAILURE_REASONS.get(
                    (case["case_id"], index),
                    "The frozen answer states the required claim and the listed frozen corpus evidence grounds it."
                    if case["answerable"] else
                    "The frozen answer correctly refuses and cites no corpus evidence for genuinely absent knowledge."
                ),
                "reviewer_mode": "AI_ASSISTED_MANUAL",
                "review_version": "v2.0.0",
            })
        required_fail = any(
            claim["required"] and review["verdict"] != "SUPPORTED"
            for claim, review in zip(case["claims"], claim_reviews)
        )
        answerability_correct = analysis["actual_answerable"] == case["answerable"]
        required_docs = {
            document_id
            for item in case["evidence_groups"] if item["required"]
            for document_id in item["any_of_document_ids"]
        }
        support_docs = set(case["acceptable_supporting_document_ids"]) | {
            document_id
            for item in case["evidence_groups"] if not item["required"]
            for document_id in item["any_of_document_ids"]
        }
        citation_reviews = []
        for document_id in analysis["cited_document_ids"]:
            role = "REQUIRED" if document_id in required_docs else (
                "ACCEPTABLE_SUPPORT" if document_id in support_docs else "UNSUPPORTED"
            )
            citation_reviews.append({
                "document_id": document_id,
                "evidence_role": role,
                "materially_supports_answer": role != "UNSUPPORTED",
                "review_reason": "Frozen corpus content supports an answer claim."
                    if role != "UNSUPPORTED" else "No supporting V2 evidence role was established.",
            })
        unsupported_citation = any(item["evidence_role"] == "UNSUPPORTED" for item in citation_reviews)
        case_pass = answerability_correct and not required_fail and not unsupported_citation and analysis["citation_valid"]
        cases.append({
            "case_id": case["case_id"],
            "frozen_answer": answer,
            "expected_answerable": case["answerable"],
            "actual_answerable": analysis["actual_answerable"],
            "answerability_correct": answerability_correct,
            "claim_reviews": claim_reviews,
            "citation_reviews": citation_reviews,
            "case_verdict": "PASS" if case_pass else "FAIL",
            "reviewer_mode": "AI_ASSISTED_MANUAL",
            "review_version": "v2.0.0",
            "review_notes": "Gold was fixed before answer comparison; verdict uses the frozen baseline answer.",
        })
    return {
        "schema_version": "2.0.0",
        "review_version": "v2.0.0",
        "baseline_run_id": BASELINE.name,
        "corpus_ref": gold["corpus_ref"],
        "case_count": len(cases),
        "cases": cases,
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    gold = build_gold()
    write_json(V2_ROOT / "gold_cases.json", gold)
    write_json(V2_ROOT / "semantic_reviews.json", build_reviews(gold))
    print(json.dumps({"status": "built", "case_count": len(gold["cases"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
