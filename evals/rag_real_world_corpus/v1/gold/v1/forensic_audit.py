"""Independent reconstruction for the final Real-world Gold V1 forensic audit.

The script reads the final Gold and frozen corpus directly. It does not call a
retriever, answer model, baseline, network service, or production RAG path.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
import re
from typing import Any

from pypdf import PdfReader

from gold_common import GOLD_ROOT, REPO_ROOT, read_json, write_json


CORPUS_ROOT = REPO_ROOT / "evals" / "rag_real_world_corpus" / "v1"
COMPLETION_REPORT = REPO_ROOT / "RAG_REAL_WORLD_GOLD_V1_REPORT.md"
SAMPLE_CASE_IDS = [
    "rw-gold-v1-semantic-checkpointer-store",
    "rw-gold-v1-semantic-context-order",
    "rw-gold-v1-multi-backend-control",
    "rw-gold-v1-multi-agent-resume",
    "rw-gold-v1-disambig-bge-long",
    "rw-gold-v1-disambig-agent-memory",
    "rw-gold-v1-unanswerable-faiss-p95-latency",
    "rw-gold-v1-unanswerable-threadpool-workers",
    "rw-gold-v1-stress-deep-bge-mldr-comparison",
    "rw-gold-v1-stress-cross-retrieval-evaluation",
    "rw-gold-v1-stress-conflict-ragas-reference-mode",
]

UNANSWERABLE_FINDINGS = {
    "rw-gold-v1-unanswerable-bge-language-counts": "The BGE source says more than 100 languages but does not enumerate them or give per-language sample counts.",
    "rw-gold-v1-unanswerable-bge-optimal-weights": "The BGE source gives adjustable example weights and pipeline advice, not a dataset-independent optimum guarantee.",
    "rw-gold-v1-unanswerable-checkpoint-encryption": "The persistence source discusses saver scope and persistence, not a mandated encryption algorithm or rotation period.",
    "rw-gold-v1-unanswerable-dependency-depth": "The dependency source shows hierarchical sub-dependencies but states no numeric depth limit or overflow status.",
    "rw-gold-v1-unanswerable-faiss-p95-latency": "The Faiss source discusses scale and trade-offs but provides no hardware-specific p95 guarantee.",
    "rw-gold-v1-unanswerable-interrupt-timeout": "The interrupts source explains pause/resume routing but sets no default approval timeout or automatic cancel interval.",
    "rw-gold-v1-unanswerable-precision-pass-threshold": "The metric source defines and illustrates context precision but prescribes no universal production threshold.",
    "rw-gold-v1-unanswerable-ragas-minimum-score": "The workflow source explains evaluation execution but guarantees no minimum production score.",
    "rw-gold-v1-unanswerable-threadpool-workers": "The FastAPI source states external-threadpool execution but guarantees no exact default worker count.",
    "rw-gold-v1-unanswerable-trace-retention": "The trace source defines trace structure and propagation but no mandatory backend retention duration.",
}

ROLE_FINDINGS = {
    "rw-gold-v1-disambig-agent-memory": "Persistence directly owns checkpointer/store scope; interrupts owns pause/resume; overview is useful high-level background only; OTel cannot answer the LangGraph state question.",
    "rw-gold-v1-disambig-agent-persist-interrupt": "Persistence directly owns restart durability and interrupts owns Command resume; overview is high-level only; OTel spans cannot replace either contract.",
    "rw-gold-v1-disambig-bge-faiss": "BGE directly owns retrieval signal capabilities and Faiss directly owns index comparison mechanics; context precision owns neither.",
    "rw-gold-v1-disambig-bge-long": "BGE directly states sequence length; Faiss supplies vector-search background but no token limit; context precision cannot answer model capacity.",
    "rw-gold-v1-disambig-fastapi-async-deps": "The async and dependency documents directly own separate execution rules; error handling does not define either rule.",
    "rw-gold-v1-disambig-fastapi-errors": "Error handling directly owns HTTPException payload/status; dependency execution is useful setup only; concurrency guidance cannot answer the response contract.",
    "rw-gold-v1-disambig-fastapi-exceptions": "Error handling directly owns the FastAPI/Starlette type relationship; async execution context is background only and cannot answer independently; dependency injection cannot answer the type hierarchy.",
    "rw-gold-v1-disambig-interrupt-static": "Interrupts directly owns static breakpoint configuration; overview and persistence provide general debugging/state context only; FastAPI async cannot answer graph breakpoints.",
    "rw-gold-v1-disambig-ragas-metrics": "Workflow directly owns evaluation-record construction and context precision owns ranking semantics; OTel tracing owns neither.",
    "rw-gold-v1-disambig-ragas-otel": "Context precision directly owns ranking quality and OTel owns distributed request paths; workflow is broader evaluation background only; Faiss cannot answer both claims.",
    "rw-gold-v1-stress-conflict-bge-faiss-compression": "Faiss directly owns index compression/storage trade-offs; BGE explains embedding production only; context precision cannot establish storage behavior.",
    "rw-gold-v1-stress-conflict-fastapi-handler-type": "Error handling directly owns handler type selection; dependency execution is limited background; async guidance cannot establish the exception hierarchy.",
    "rw-gold-v1-stress-conflict-interrupt-persistence-resume": "Interrupts directly owns Command resume semantics; persistence supports checkpoint continuity only; overview cannot replace the detailed resume contract.",
    "rw-gold-v1-stress-conflict-ragas-reference-mode": "Context precision directly owns with/without-reference variants; workflow supplies relevant field background only; OTel cannot answer metric input modes.",
}

PRECHANGE_SHA256 = {
    "RAG_REAL_WORLD_GOLD_V1_REPORT.md": "dc113e3b7335350354abee5134ad7d8154088869dd6bd1bee5831c01177ba4b5",
    "evals/rag_real_world_corpus/v1/gold/v1/independent_review.py": "9e87a3ca0e5d79ba77218b1f4cfd696eba9361e364b18f6808661bfc7e941940",
    "evals/rag_real_world_corpus/v1/gold/v1/independent_reviews.schema.json": "3c4bfa3b005ede44a52de9a76b9e85544461483a18d2cd4d1340cdd5aec7a6d5",
    "evals/rag_real_world_corpus/v1/gold/v1/independent_reviews.json": "9485573dd03217627fda1de1c2b8fa4e7d2ba072a776d29827ff39f3a2442d9b",
    "evals/rag_real_world_corpus/v1/gold/v1/independent_review_summary.json": "285f4cd3d92cedfaef7d5fcbed0e625bfee1155bd05cba034c0976d26cb8cf1a",
    "evals/rag_real_world_corpus/v1/gold/v1/finalize_gold.py": "052ca2c8e515e42b57ab1d5c2425a06dd7906d2cb2846148a3505f9593afff00",
    "evals/rag_real_world_corpus/v1/gold/v1/validate_gold.py": "c8fbf11067c3bf3fc92eaa857124e47c9106cbad6a5aa8178fff25f38c24b0ab",
    "evals/rag_real_world_corpus/v1/gold/v1/gold_cases.json": "40b2c3e6ca793f74014fbe8fbd2203a3f06a987b84dc708dfeb558e705632dc3",
    "evals/rag_real_world_corpus/v1/gold/v1/evaluation_manifest.json": "5acd9c55fa9e6f8d9ca25de6e57496b54f31f400fe641852d492fff55a30b6dd",
    "evals/rag_real_world_corpus/v1/gold/v1/distribution_audit.json": "b6294795b8e73cc56335c3ef3fa1a71335b7782de89b04fa82c3cd0e2635b3a7",
    "evals/rag_real_world_corpus/v1/gold/v1/final_validation.json": "25364176a606f749e122846820857e1f806f419476c6501fe82e78cd5fe3d5a7",
    "backend/tests/test_rag_real_world_gold_v1.py": "f24b8c3b2171fcdd87efb49f354487b0ed7a06bc175e0bbae9508ac9cc39893e",
}


def normalize(text: str) -> str:
    return " ".join(text.replace("\x00", "").split())


def required_documents(case: dict[str, Any]) -> set[str]:
    return {
        document_id
        for group in case["evidence_groups"]
        if group["required"]
        for document_id in group["any_of_document_ids"]
    }


def required_anchor_ids(case: dict[str, Any]) -> set[str]:
    return {
        evidence_id
        for group in case["evidence_groups"]
        if group["required"]
        for evidence_id in group["any_of_evidence_ids"]
    }


def minimum_hitting_count(groups: list[dict[str, Any]]) -> int:
    if not groups:
        return 0
    documents = sorted({doc for group in groups for doc in group["any_of_document_ids"]})
    for size in range(1, len(documents) + 1):
        for chosen in combinations(documents, size):
            if all(set(chosen) & set(group["any_of_document_ids"]) for group in groups):
                return size
    raise RuntimeError("required groups have no hitting set")


def recompute_anchor(anchor: dict[str, Any], document: dict[str, Any]) -> tuple[dict[str, Any], str]:
    locator = anchor["locator"]
    path = REPO_ROOT / locator["source_path"]
    errors: list[str] = []
    if not path.is_file():
        errors.append("document path missing")
        text = ""
    elif locator["source_path"] != document["repository_path"]:
        errors.append("locator path differs from corpus manifest")
        text = ""
    elif locator["kind"] == "SOURCE_LINES":
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        start, end = locator["start_line"], locator["end_line"]
        if not 1 <= start <= end <= len(lines):
            errors.append("source line range does not resolve")
            text = ""
        else:
            text = normalize("\n".join(lines[start - 1:end]))
        if not locator.get("section_title", "").strip():
            errors.append("section title is empty")
    elif locator["kind"] == "PDF_PAGE":
        reader = PdfReader(str(path))
        page_number = locator["page_number"]
        if not 1 <= page_number <= len(reader.pages):
            errors.append("PDF page does not resolve")
            text = ""
        else:
            text = normalize(reader.pages[page_number - 1].extract_text() or "")
        if not text:
            errors.append("PDF page text is empty")
    else:
        errors.append("unknown locator kind")
        text = ""
    source_bytes_hash = sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    anchor_text_hash = sha256(text.encode("utf-8")).hexdigest()
    if source_bytes_hash != document["corpus_sha256"]:
        errors.append("source bytes differ from corpus manifest")
    if anchor_text_hash != anchor["anchor_text_hash"]:
        errors.append("anchor text hash mismatch")
    excerpt_prefix = anchor["excerpt"].removesuffix("...").strip()
    if not excerpt_prefix or not text.startswith(excerpt_prefix):
        errors.append("stored excerpt is not a prefix of resolved text")
    serialized_ids = f"{anchor['evidence_id']} {anchor['document_id']}"
    if re.search(r"(?i)(material[_-]?id|materialchunk|chunk[_-]?id|\bS[12][-_][A-Za-z0-9]+)", serialized_ids):
        errors.append("runtime ID pattern found")
    return ({
        "evidence_id": anchor["evidence_id"],
        "document_id": anchor["document_id"],
        "locator": locator,
        "document_resolves": path.is_file(),
        "manifest_path_matches": locator["source_path"] == document["repository_path"],
        "source_bytes_sha256": source_bytes_hash,
        "source_bytes_match_manifest": source_bytes_hash == document["corpus_sha256"],
        "recomputed_anchor_text_sha256": anchor_text_hash,
        "anchor_hash_matches": anchor_text_hash == anchor["anchor_text_hash"],
        "section_or_page_check": (
            "NONEMPTY_SECTION_LABEL_AND_RESOLVED_LINE_RANGE"
            if locator["kind"] == "SOURCE_LINES" else
            "RESOLVED_NONEMPTY_PDF_PAGE_TEXT"
        ),
        "runtime_id_leakage": False if not any("runtime ID" in item for item in errors) else True,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
    }, text)


def question_fingerprint(text: str) -> set[str]:
    compact = re.sub(r"\s+", "", text.casefold())
    grams = {"c:" + compact[index:index + 3] for index in range(max(0, len(compact) - 2))}
    words = {"w:" + item for item in re.findall(r"[a-z0-9_]+", text.casefold()) if len(item) > 2}
    return grams | words


def near_duplicate(left: str, right: str) -> bool:
    a, b = question_fingerprint(left), question_fingerprint(right)
    return bool(a and b and len(a & b) / len(a | b) >= 0.82)


def build_sample(
    case: dict[str, Any],
    anchors: dict[str, dict[str, Any]],
    anchor_texts: dict[str, str],
    review: dict[str, Any],
) -> dict[str, Any]:
    group_ids = {group["evidence_group_id"] for group in case["evidence_groups"]}
    evidence_ids = required_anchor_ids(case)
    evidence_ids |= {
        evidence_id
        for record in case["acceptable_supporting_evidence"]
        for evidence_id in record["evidence_ids"]
    }
    if not case["answerable"]:
        evidence_ids |= set(case["unanswerable_contract"]["near_boundary_evidence_ids"])
    groups = []
    for group in case["evidence_groups"]:
        groups.append({
            "group_id": group["evidence_group_id"],
            "composition": "AND with every other required group; OR within this group",
            "required_documents": group["any_of_document_ids"],
            "anchor_ids": group["any_of_evidence_ids"],
        })
    minimum_docs = minimum_hitting_count(case["evidence_groups"])
    return {
        "case_id": case["case_id"],
        "case_type": case["case_type"],
        "difficulty": case["difficulty"],
        "query_language": case["query_language"],
        "topic": case["primary_topic"],
        "secondary_topics": case["secondary_topics"],
        "question": case["question"],
        "atomic_claims": [{
            "claim_id": claim["claim_id"],
            "evaluation_mode": claim["evaluation_mode"],
            "expected_semantic_requirement": claim["canonical_claim"],
            "evidence_group_ids": claim["evidence_group_ids"],
        } for claim in case["claims"]],
        "evidence_groups": groups,
        "evidence_roles": {
            "REQUIRED": sorted(required_documents(case)),
            "ACCEPTABLE_SUPPORT": case["acceptable_supporting_evidence"],
            "UNSUPPORTED": case["plausible_distractor_documents"],
        },
        "anchors": [{
            "anchor_id": evidence_id,
            "document_id": anchors[evidence_id]["document_id"],
            "locator": anchors[evidence_id]["locator"],
            "actual_frozen_corpus_evidence_excerpt": anchor_texts[evidence_id][:500],
        } for evidence_id in sorted(evidence_ids)],
        "minimum_distinct_documents_to_cover_all_required_groups": minimum_docs,
        "why_multiple_documents_are_needed": (
            f"All {len(group_ids)} groups compose with AND and their alternatives require a minimum hitting set of {minimum_docs} distinct documents."
            if minimum_docs > 1 else
            "The required-group contract can be satisfied with one document; any additional listed document is an OR alternative or supporting source."
        ),
        "independent_review_result": {
            "verification_status": review["verification_status"],
            "review_reason": review["review_reason"],
            "claim_binding_reviews": review["claim_reviews"],
            "semantic_rejudgment_performed": False,
        },
    }


def main() -> None:
    gold = read_json(GOLD_ROOT / "gold_cases.json")
    cases = gold["cases"]
    manifest = read_json(CORPUS_ROOT / "corpus_manifest.json")
    documents = {item["document_id"]: item for item in manifest["documents"]}
    anchor_artifact = read_json(GOLD_ROOT / "evidence_anchors.json")
    anchors = {item["evidence_id"]: item for item in anchor_artifact["anchors"]}
    reviews_artifact = read_json(GOLD_ROOT / "independent_reviews.json")
    reviews = {item["case_id"]: item for item in reviews_artifact["reviews"]}
    distribution_audit = read_json(GOLD_ROOT / "distribution_audit.json")

    per_case = []
    per_document: dict[str, list[str]] = defaultdict(list)
    for case in cases:
        document_ids = sorted(required_documents(case))
        per_case.append({
            "case_id": case["case_id"],
            "case_type": case["case_type"],
            "unique_required_document_ids": document_ids,
            "required_document_count": len(document_ids),
        })
        for document_id in document_ids:
            per_document[document_id].append(case["case_id"])
    left = sum(item["required_document_count"] for item in per_case)
    right = sum(len(case_ids) for case_ids in per_document.values())

    anchor_records = []
    anchor_texts = {}
    for evidence_id, anchor in anchors.items():
        record, text = recompute_anchor(anchor, documents[anchor["document_id"]])
        anchor_records.append(record)
        anchor_texts[evidence_id] = text

    evaluation_modes = Counter(
        claim["evaluation_mode"] for case in cases for claim in case["claims"]
    )
    computed_distribution = {
        "case_count": len(cases),
        "tier_distribution": dict(sorted(Counter(case["tier"] for case in cases).items())),
        "case_type_distribution": dict(sorted(Counter(case["case_type"] for case in cases).items())),
        "topic_distribution": dict(sorted(Counter(case["primary_topic"] for case in cases).items())),
        "query_language_distribution": dict(sorted(Counter(case["query_language"] for case in cases).items())),
        "difficulty_distribution": dict(sorted(Counter(case["difficulty"] for case in cases).items())),
        "claim_count": sum(len(case["claims"]) for case in cases),
        "evaluation_mode_distribution": dict(sorted(evaluation_modes.items())),
        "required_evidence_group_count": sum(len(case["evidence_groups"]) for case in cases),
        "required_anchor_reference_count": sum(len(required_anchor_ids(case)) for case in cases),
        "acceptable_support_record_count": sum(len(case["acceptable_supporting_evidence"]) for case in cases),
        "unsupported_distractor_record_count": sum(len(case["plausible_distractor_documents"]) for case in cases),
        "pdf_required_case_count": sum(
            any(anchors[evidence_id]["locator"]["kind"] == "PDF_PAGE" for evidence_id in required_anchor_ids(case))
            for case in cases
        ),
        "txt_required_or_acceptable_case_count": sum(
            any(
                documents[document_id]["source_format"] == "txt"
                for document_id in required_documents(case) | {
                    item["document_id"] for item in case["acceptable_supporting_evidence"]
                }
            )
            for case in cases
        ),
        "multi_document_case_count": sum(len(required_documents(case)) >= 2 for case in cases),
        "cross_topic_case_count": sum(
            len({documents[doc]["topic_cluster"] for doc in required_documents(case)}) >= 2
            for case in cases
        ),
        "required_document_count_distribution": {
            str(count): case_count
            for count, case_count in sorted(Counter(
                len(required_documents(case)) for case in cases
            ).items())
        },
    }
    audit_comparison = {}
    for key, actual in computed_distribution.items():
        if key == "evaluation_mode_distribution":
            audit_comparison[key] = {"actual": actual, "audit": None, "status": "NOT_RECORDED_IN_DISTRIBUTION_AUDIT"}
        else:
            expected = distribution_audit.get(key)
            audit_comparison[key] = {"actual": actual, "audit": expected, "status": "MATCH" if actual == expected else "MISMATCH"}

    source_texts = []
    for document in documents.values():
        path = REPO_ROOT / document["repository_path"]
        if document["source_format"] in {"md", "txt"}:
            source_texts.append(normalize(path.read_text(encoding="utf-8-sig")).casefold())
    normalized_questions = [normalize(case["question"]).casefold() for case in cases]
    near_pairs = []
    for index, left_case in enumerate(cases):
        for right_case in cases[index + 1:]:
            if near_duplicate(left_case["question"], right_case["question"]):
                near_pairs.append([left_case["case_id"], right_case["case_id"]])
    exact_source_sentence_cases = []
    for case in cases:
        normalized = normalize(case["question"]).casefold().rstrip("?？")
        if len(normalized) >= 24 and any(normalized in source for source in source_texts):
            exact_source_sentence_cases.append(case["case_id"])
    title_only_cases = []
    for case in cases:
        terms = set(re.findall(r"[a-z0-9_-]{4,}", case["question"].casefold()))
        if case["query_language"] == "en" and len(terms) <= 1:
            title_only_cases.append(case["case_id"])
    runtime_pattern = re.compile(r"(?i)(material[_-]?id|materialchunk|chunk[_-]?id|\bS[12][-_][A-Za-z0-9]+)")
    runtime_leakage_cases = [
        case["case_id"] for case in cases
        if runtime_pattern.search(json.dumps(case, ensure_ascii=False))
    ]

    immutability = read_json(GOLD_ROOT / "immutability_baseline.json")
    immutability_result = {}
    for scope in ("frozen_real_world_corpus", "controlled_corpus_v2", "production_rag"):
        mismatches = []
        for relative, expected in immutability[scope].items():
            path = REPO_ROOT / relative
            actual = sha256(path.read_bytes()).hexdigest() if path.is_file() else "MISSING"
            if actual != expected:
                mismatches.append({"path": relative, "expected": expected, "actual": actual})
        immutability_result[scope] = {
            "monitored_file_count": len(immutability[scope]),
            "mismatch_count": len(mismatches),
            "mismatches": mismatches,
        }

    unanswerable_cases = [case for case in cases if case["case_type"] == "unanswerable_near_boundary"]
    unanswerable_audit = [{
        "case_id": case["case_id"],
        "question": case["question"],
        "corpus_bounded_status": "PASS",
        "near_boundary_reason": UNANSWERABLE_FINDINGS[case["case_id"]],
        "citation_safety": "No corpus citation may be emitted because the requested fact is absent; citing the nearby passage would falsely imply support.",
    } for case in unanswerable_cases]

    role_cases = [
        case for case in cases
        if case["case_type"] in {"source_disambiguation", "high_overlap_source_conflict"}
    ]
    role_audit = [{
        "case_id": case["case_id"],
        "case_type": case["case_type"],
        "status": "PASS",
        "finding": ROLE_FINDINGS[case["case_id"]],
        "required_documents": sorted(required_documents(case)),
        "acceptable_supporting_documents": [item["document_id"] for item in case["acceptable_supporting_evidence"]],
        "unsupported_documents": [item["document_id"] for item in case["plausible_distractor_documents"]],
        "unsupported_can_fully_answer": False,
        "acceptable_support_can_independently_satisfy_all_required_claims": False,
    } for case in role_cases]

    report_text = COMPLETION_REPORT.read_text(encoding="utf-8")
    report_tokens = {
        "case_count": "CORE=60",
        "topic_distribution": "`rag_retrieval=17`、`agent_engineering=18`、`ai_app_backend=18`、`evaluation_reliability=19`",
        "language_distribution": "`zh-CN=54`、`en=18`",
        "difficulty_distribution": "`easy=10`、`medium=19`、`hard=31`、`stress=12`",
        "claim_distribution": "`SEMANTIC_REVIEW=104`、`ANSWERABILITY_ONLY=10`、`NUMERIC_EXACT=7`、`STRUCTURED_EXACT=6`、`IDENTIFIER_EXACT=5`",
        "required_document_distribution": "1 文档 41 例、2 文档 18 例、3 文档 3 例",
        "required_document_participation": "均为 86",
        "multi_document_case_count": "21 个案例",
        "anchor_distribution": "65 个 `SOURCE_LINES`、24 个 `PDF_PAGE`",
        "semantic_scope": "`independent_semantic_rejudgment_performed=false`",
    }
    report_comparison = {
        key: {"expected_text": token, "status": "MATCH" if token in report_text else "MISMATCH"}
        for key, token in report_tokens.items()
    }

    samples = [build_sample(
        next(case for case in cases if case["case_id"] == case_id),
        anchors,
        anchor_texts,
        reviews[case_id],
    ) for case_id in SAMPLE_CASE_IDS]

    execution_audit = read_json(GOLD_ROOT / "task_execution_audit.json")
    prechange_comparison = []
    for relative, before_hash in PRECHANGE_SHA256.items():
        path = REPO_ROOT / relative
        after_hash = sha256(path.read_bytes()).hexdigest() if path.is_file() else "MISSING"
        prechange_comparison.append({
            "path": relative,
            "before_forensic_sha256": before_hash,
            "current_sha256": after_hash,
            "changed_by_forensic_pass_or_regeneration": before_hash != after_hash,
        })

    all_pass = (
        left == right
        and all(item["status"] == "PASS" for item in anchor_records)
        and all(item["status"] != "MISMATCH" for item in audit_comparison.values())
        and all(item["status"] == "MATCH" for item in report_comparison.values())
        and not near_pairs
        and not exact_source_sentence_cases
        and not title_only_cases
        and not runtime_leakage_cases
        and all(item["mismatch_count"] == 0 for item in immutability_result.values())
        and reviews_artifact["verification_scope"]["independent_semantic_rejudgment_performed"] is False
        and all(execution_audit[field] == 0 for field in (
            "llm_or_deepseek_call_count", "rag_answer_call_count", "rag_baseline_execution_count",
            "production_rag_write_count", "frozen_corpus_content_write_count", "controlled_v2_write_count",
        ))
    )
    artifact = {
        "schema_version": "1.0.0",
        "audit_id": "learnpilot-rag-real-world-gold-v1-final-forensic-audit",
        "status": "PASS" if all_pass else "FAIL",
        "method": "Local deterministic reconstruction plus explicit manual source-role/answerability judgments; no external LLM or baseline.",
        "gold_dataset_sha256": sha256((GOLD_ROOT / "gold_cases.json").read_bytes()).hexdigest(),
        "totals": {
            "TOTAL_CASES": len(cases),
            "CORE_CASES": sum(case["tier"] == "CORE" for case in cases),
            "STRESS_CASES": sum(case["tier"] == "STRESS" for case in cases),
        },
        "required_document_participation": {
            "per_case": per_case,
            "required_document_count_distribution": {
                str(count): case_count
                for count, case_count in sorted(Counter(
                    item["required_document_count"] for item in per_case
                ).items())
            },
            "per_document_distinct_required_case_count": {
                document_id: {"count": len(case_ids), "case_ids": sorted(case_ids)}
                for document_id, case_ids in sorted(per_document.items())
            },
            "REQUIRED_DOCUMENT_PARTICIPATION_LEFT": left,
            "REQUIRED_DOCUMENT_PARTICIPATION_RIGHT": right,
            "MATCH": left == right,
            "root_cause": {
                "gold_defect": False,
                "distribution_audit_defect": False,
                "report_defect": True,
                "exact_file": "RAG_REAL_WORLD_GOLD_V1_REPORT.md",
                "exact_location": "section 14, manually maintained prose (no report generator function)",
                "stale_values": {"multi_document_case_count": 20, "required_document_count_distribution": {"0": 10, "1": 42, "2": 17, "3": 3}, "participation_total": 85},
                "correct_values": {"multi_document_case_count": 21, "required_document_count_distribution": {"0": 10, "1": 41, "2": 18, "3": 3}, "participation_total": 86},
                "drift_trigger_case": "rw-gold-v1-semantic-checkpointer-store",
                "drift_trigger_documents": ["rw-agent-langgraph-overview", "rw-agent-persistence"],
                "drift_trigger_group_ids": ["eg-rw-semantic-checkpointer-store-01", "eg-rw-semantic-checkpointer-store-02"],
                "duplicate_case_document_counting_found": False,
                "explanation": "The final OR group introduced overview as a second distinct candidate required-group document while persistence remained present in both groups. Per-case set de-duplication correctly counts two documents; the old prose retained the earlier 1-document bucket. finalize_gold.py required_documents() and document exposure already de-duplicate by set membership.",
            },
        },
        "distribution_recomputation": computed_distribution,
        "distribution_audit_comparison": audit_comparison,
        "completion_report_comparison": report_comparison,
        "independent_review_forensic": {
            "exact_inputs": [
                "merged_draft.json",
                "evidence_anchors.json",
                "corpus_manifest.json",
                "frozen corpus files referenced by anchor locator",
                "independent_reviews.schema.json",
            ],
            "inputs_not_read": [
                "gold_cases.json", "authoring_specs/*", "final answers", "baseline outputs", "retrieval outputs",
            ],
            "source_lines_reopened": True,
            "pdf_pages_reopened": True,
            "anchor_hashes_recomputed": True,
            "semantic_verdict_algorithm_before_fix": "answerable ? SUPPORTED : SUPPORTED_BOUNDARY; no claim/evidence semantic comparison",
            "circular_self_validation_found": True,
            "current_verification_scope": reviews_artifact["verification_scope"],
            "semantic_rejudgment_count": 0,
            "verified_count_meaning": "72/72 deterministic structure and frozen-corpus binding checks passed within the declared scope.",
        },
        "forensic_samples": samples,
        "unanswerable_near_boundary_audit": {
            "case_count": len(unanswerable_audit),
            "valid_count": sum(item["corpus_bounded_status"] == "PASS" for item in unanswerable_audit),
            "open_world_defect_case_ids": [],
            "cases": unanswerable_audit,
        },
        "source_role_semantic_audit": {
            "case_count": len(role_audit),
            "pass_count": sum(item["status"] == "PASS" for item in role_audit),
            "unsupported_can_fully_answer_case_ids": [],
            "acceptable_independently_sufficient_case_ids": [],
            "cases": role_audit,
        },
        "evidence_anchor_audit": {
            "anchor_count": len(anchor_records),
            "locator_kind_distribution": dict(sorted(Counter(item["locator"]["kind"] for item in anchor_records).items())),
            "pass_count": sum(item["status"] == "PASS" for item in anchor_records),
            "failure_count": sum(item["status"] != "PASS" for item in anchor_records),
            "source_document_byte_hash_match_count": sum(
                sha256((REPO_ROOT / document["repository_path"]).read_bytes()).hexdigest() == document["corpus_sha256"]
                for document in documents.values()
            ),
            "source_document_count": len(documents),
            "records": anchor_records,
        },
        "duplicate_and_leakage_audit": {
            "distinct_information_need_count": len({case["information_need_key"] for case in cases}),
            "exact_duplicate_question_count": len(normalized_questions) - len(set(normalized_questions)),
            "near_duplicate_question_pair_count": len(near_pairs),
            "near_duplicate_question_pairs": near_pairs,
            "exact_source_sentence_question_count": len(exact_source_sentence_cases),
            "exact_source_sentence_case_ids": exact_source_sentence_cases,
            "title_only_question_risk_count": len(title_only_cases),
            "title_only_question_case_ids": title_only_cases,
            "runtime_id_leakage_count": len(runtime_leakage_cases),
            "runtime_id_leakage_case_ids": runtime_leakage_cases,
            "real_world_baseline_output_files_found": [
                str(path.relative_to(REPO_ROOT)).replace("\\", "/")
                for path in (CORPUS_ROOT / "results").rglob("*baseline*")
            ],
        },
        "immutability_audit": immutability_result,
        "no_execution_audit": {
            "DeepSeek_call_count": execution_audit["llm_or_deepseek_call_count"],
            "other_LLM_call_count": 0,
            "RAG_ask_call_count": execution_audit["rag_answer_call_count"],
            "Real_world_baseline_execution_count": execution_audit["rag_baseline_execution_count"],
            "production_RAG_modification_count": execution_audit["production_rag_write_count"],
            "evidence": "Task execution audit, absence of Real-world baseline result files, monitored production hashes, and forensic changed-file review.",
        },
        "prechange_hash_comparison": prechange_comparison,
    }
    write_json(GOLD_ROOT / "final_forensic_audit.json", artifact)
    print(json.dumps({
        "status": artifact["status"],
        "case_count": len(cases),
        "participation_left": left,
        "participation_right": right,
        "anchor_pass_count": artifact["evidence_anchor_audit"]["pass_count"],
        "sample_count": len(samples),
        "immutability": immutability_result,
    }, ensure_ascii=False, indent=2))
    if artifact["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
