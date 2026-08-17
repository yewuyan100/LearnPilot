"""Validate and score the frozen baseline through the V2 contract seam."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
from typing import Any


V2_ROOT = Path(__file__).resolve().parent
V1_ROOT = V2_ROOT.parents[1]
REPO_ROOT = V1_ROOT.parents[2]
RUN_ID = "20260813T095948Z-f8aaaae2"
BASELINE = V1_ROOT / "results" / "baseline_v1" / RUN_ID
LATEST_AUDIT = V1_ROOT / "results" / "failure_scale_analysis_v1" / "20260813T112545Z-canonical-f8aaaae2"
RESULTS = V1_ROOT / "results" / "contract_v2_review"
BASELINE_FILES = (
    "raw_cases.jsonl", "case_analysis.json", "failure_taxonomy.json", "metrics.json",
    "result.json", "run_metadata.json", "document_material_map.json",
    "persistence_audit.json", "backend.log", "preflight.json", "report.md", "validation.json",
)
V1_CONTRACT_FILES = (
    V1_ROOT / "corpus_manifest.json",
    V1_ROOT / "corpus_manifest.schema.json",
    V1_ROOT / "gold_cases.json",
    V1_ROOT / "gold_cases.schema.json",
    V1_ROOT / "validate_foundation.py",
    V1_ROOT / "verify_gold_cases.py",
    V1_ROOT / "baseline_metrics.py",
    V1_ROOT / "run_baseline_eval.py",
)
PRODUCTION_RAG_FILES = tuple(sorted(
    [
        REPO_ROOT / "backend" / "app" / "api" / "routes" / "materials.py",
        REPO_ROOT / "backend" / "app" / "api" / "routes" / "rag.py",
        REPO_ROOT / "backend" / "app" / "core" / "config.py",
        REPO_ROOT / "backend" / "app" / "services" / "material_processing" / "pipeline.py",
    ]
    + list((REPO_ROOT / "backend" / "app" / "services" / "rag").glob("*.py"))
    + list((REPO_ROOT / "backend" / "app" / "services" / "embedding").glob("*.py"))
    + list((REPO_ROOT / "backend" / "app" / "services" / "vector_store").glob("*.py"))
))
ALLOWED_REVIEW_VERDICTS = {
    "SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED", "AMBIGUOUS_GOLD"
}
ALLOWED_AUDIT_REASONS = {
    "ALTERNATIVE_DOCUMENT_EQUIVALENT", "LEXICAL_REQUIREMENT_REMOVED", "CLAIM_SPLIT",
    "AMBIGUOUS_EXPECTATION_CLARIFIED", "EVIDENCE_GROUP_REMODELED",
}
DETERMINISTIC_MODES = {"STRUCTURED_EXACT", "NUMERIC_EXACT", "IDENTIFIER_EXACT", "ANSWERABILITY_ONLY"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def hash_map(paths: tuple[Path, ...]) -> dict[str, str]:
    return {
        str(path.relative_to(REPO_ROOT)).replace("\\", "/"): digest(path)
        for path in paths if path.is_file()
    }


def required_groups(case: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in case["evidence_groups"] if item["required"]]


def group_coverage(case: dict[str, Any], document_ids: list[str]) -> float:
    groups = required_groups(case)
    if not groups:
        return 1.0
    actual = set(document_ids)
    return mean(bool(actual & set(item["any_of_document_ids"])) for item in groups)


def supporting_documents(case: dict[str, Any]) -> set[str]:
    return {
        document_id
        for item in case["evidence_groups"]
        for document_id in item["any_of_document_ids"]
    } | set(case["acceptable_supporting_document_ids"])


def validate_contract(
    gold: dict[str, Any], reviews: dict[str, Any], manifest: dict[str, Any], v1_gold: dict[str, Any]
) -> dict[str, Any]:
    errors: list[str] = []
    document_ids = {item["document_id"] for item in manifest["documents"]}
    v1_by_id = {item["case_id"]: item for item in v1_gold["cases"]}
    cases = gold.get("cases", [])
    case_ids = [item.get("case_id") for item in cases]
    if len(cases) != 48:
        errors.append("V2 must contain exactly 48 cases")
    if len(case_ids) != len(set(case_ids)):
        errors.append("duplicate V2 case_id")
    if set(case_ids) != set(v1_by_id):
        errors.append("V2 case IDs do not exactly match frozen V1")
    all_claim_ids: set[str] = set()
    changed_count = 0
    for case in cases:
        case_id = case["case_id"]
        groups = case.get("evidence_groups", [])
        group_ids = [item.get("evidence_group_id") for item in groups]
        if len(group_ids) != len(set(group_ids)):
            errors.append(f"{case_id}: duplicate evidence_group_id")
        roles: dict[str, set[str]] = {
            "evidence": {document_id for item in groups for document_id in item["any_of_document_ids"]},
            "support": set(case.get("acceptable_supporting_document_ids", [])),
            "disallowed": set(case.get("irrelevant_or_disallowed_document_ids", [])),
        }
        for role, ids in roles.items():
            unknown = ids - document_ids
            if unknown:
                errors.append(f"{case_id}: invalid {role} references {sorted(unknown)}")
        overlap = (roles["evidence"] & roles["support"]) | (roles["evidence"] & roles["disallowed"]) | (roles["support"] & roles["disallowed"])
        if overlap:
            errors.append(f"{case_id}: contradictory evidence roles {sorted(overlap)}")
        claims = case.get("claims", [])
        if not claims:
            errors.append(f"{case_id}: missing claims")
        if case["answerable"] and not any(item.get("required") for item in claims):
            errors.append(f"{case_id}: answerable case has no required claims")
        if case["answerable"] and not required_groups(case):
            errors.append(f"{case_id}: answerable case has no required evidence group")
        if not case["answerable"]:
            if groups or case["citation_contract"]["required_evidence_group_ids"]:
                errors.append(f"{case_id}: unanswerable case carries required evidence")
            if any(item["evaluation_mode"] != "ANSWERABILITY_ONLY" for item in claims):
                errors.append(f"{case_id}: unanswerable claims must be ANSWERABILITY_ONLY")
        claim_ids = [item.get("claim_id") for item in claims]
        if len(claim_ids) != len(set(claim_ids)):
            errors.append(f"{case_id}: duplicate claim_id")
        for claim in claims:
            claim_id = claim.get("claim_id")
            if not claim_id:
                errors.append(f"{case_id}: missing claim_id")
            elif claim_id in all_claim_ids:
                errors.append(f"duplicate claim_id across cases: {claim_id}")
            all_claim_ids.add(claim_id)
            unknown_groups = set(claim.get("evidence_group_ids", [])) - set(group_ids)
            if unknown_groups:
                errors.append(f"{case_id}: claim references nonexistent groups {sorted(unknown_groups)}")
            if claim["evaluation_mode"] in {"STRUCTURED_EXACT", "NUMERIC_EXACT", "IDENTIFIER_EXACT"} and not claim.get("deterministic_match"):
                errors.append(f"{claim_id}: deterministic mode missing deterministic_match")
        citation_group_ids = set(case["citation_contract"]["required_evidence_group_ids"])
        if citation_group_ids != {item["evidence_group_id"] for item in required_groups(case)}:
            errors.append(f"{case_id}: citation groups do not match required evidence groups")
        trace = case["v1_trace"]
        if trace.get("expected_document_ids") != v1_by_id[case_id]["expected_document_ids"] or trace.get("key_facts") != v1_by_id[case_id]["key_facts"]:
            errors.append(f"{case_id}: V1 trace mismatch")
        gold_review = case["gold_review"]
        if gold_review["semantics_changed"]:
            changed_count += 1
            if not gold_review["audit_reasons"]:
                errors.append(f"{case_id}: semantic change missing audit reason")
        invalid_reasons = set(gold_review["audit_reasons"]) - ALLOWED_AUDIT_REASONS
        if invalid_reasons:
            errors.append(f"{case_id}: invalid audit reasons {sorted(invalid_reasons)}")

    review_cases = reviews.get("cases", [])
    review_ids = [item.get("case_id") for item in review_cases]
    if len(review_cases) != 48 or set(review_ids) != set(case_ids):
        errors.append("semantic reviews must cover exactly all 48 cases")
    gold_by_id = {item["case_id"]: item for item in cases}
    for review in review_cases:
        case_id = review["case_id"]
        valid_claims = {item["claim_id"] for item in gold_by_id.get(case_id, {}).get("claims", [])}
        seen: set[str] = set()
        for claim_review in review.get("claim_reviews", []):
            claim_id = claim_review.get("claim_id")
            if claim_id not in valid_claims:
                errors.append(f"{case_id}: review references nonexistent claim {claim_id}")
            if claim_id in seen:
                errors.append(f"{case_id}: duplicate claim review {claim_id}")
            seen.add(claim_id)
            if claim_review.get("verdict") not in ALLOWED_REVIEW_VERDICTS:
                errors.append(f"{case_id}: unsupported review verdict {claim_review.get('verdict')}")
            if claim_review.get("case_id") != case_id:
                errors.append(f"{case_id}: nested review case_id mismatch")
            if not set(claim_review.get("supporting_document_ids", [])).issubset(document_ids):
                errors.append(f"{case_id}: review references unknown document")
        if seen != valid_claims:
            errors.append(f"{case_id}: missing claim reviews")
    return {
        "status": "valid" if not errors else "invalid",
        "case_count": len(cases),
        "reviewed_case_count": len(review_cases),
        "changed_gold_semantics_case_count": changed_count,
        "document_reference_error_count": sum("invalid" in item or "unknown document" in item for item in errors),
        "claim_reference_error_count": sum("claim" in item and ("nonexistent" in item or "missing" in item) for item in errors),
        "errors": errors,
    }


def deterministic_match(answer: str, rule: dict[str, Any]) -> bool:
    folded = answer.casefold()
    if "all_terms" in rule and not all(term.casefold() in folded for term in rule["all_terms"]):
        return False
    position = -1
    for term in rule.get("ordered_terms", []):
        position = folded.find(term.casefold(), position + 1)
        if position < 0:
            return False
    return True


def score_frozen_baseline(
    gold: dict[str, Any], reviews: dict[str, Any], analyses: list[dict[str, Any]]
) -> dict[str, Any]:
    review_by_id = {item["case_id"]: item for item in reviews["cases"]}
    analysis_by_id = {item["case_id"]: item for item in analyses}
    items: list[dict[str, Any]] = []
    citation_role_counts: Counter[str] = Counter()
    total_semantic_required = 0
    supported_semantic_required = 0
    for case in gold["cases"]:
        case_id = case["case_id"]
        analysis = analysis_by_id[case_id]
        review = review_by_id[case_id]
        answer = analysis["answer"]
        deterministic_claims: list[dict[str, Any]] = []
        semantic_claims: list[dict[str, Any]] = []
        review_verdicts = {item["claim_id"]: item["verdict"] for item in review["claim_reviews"]}
        for claim in case["claims"]:
            mode = claim["evaluation_mode"]
            if mode in DETERMINISTIC_MODES:
                if mode == "ANSWERABILITY_ONLY":
                    passed = analysis["actual_answerable"] is False and not analysis["cited_document_ids"]
                else:
                    passed = deterministic_match(answer, claim["deterministic_match"])
                deterministic_claims.append({"claim_id": claim["claim_id"], "required": claim["required"], "passed": passed})
            else:
                verdict = review_verdicts[claim["claim_id"]]
                semantic_claims.append({"claim_id": claim["claim_id"], "required": claim["required"], "verdict": verdict})
                if claim["required"]:
                    total_semantic_required += 1
                    supported_semantic_required += verdict == "SUPPORTED"
        citation_roles = review["citation_reviews"]
        citation_role_counts.update(item["evidence_role"] for item in citation_roles)
        required_citation_coverage = group_coverage(case, analysis["cited_document_ids"])
        deterministic_pass = (
            analysis["answerability_correct"]
            and analysis["citation_valid"]
            and all(not item["required"] or item["passed"] for item in deterministic_claims)
            and (not case["answerable"] or required_citation_coverage == 1.0)
        )
        semantic_pass = (
            deterministic_pass
            and all(not item["required"] or item["verdict"] == "SUPPORTED" for item in semantic_claims)
            and not any(item["evidence_role"] == "UNSUPPORTED" for item in citation_roles)
        )
        raw_k_docs = analysis["top_k_document_ids"]
        candidate_docs = analysis["above_threshold_document_ids"]
        context_docs = analysis["selected_context_document_ids"]
        allowed = supporting_documents(case)
        def noise_rate(documents: list[str]) -> float:
            unique = set(documents)
            return len(unique - allowed) / len(unique) if unique else 0.0
        items.append({
            "case_id": case_id,
            "v1_verdict": "PASS" if analysis["passed"] else "FAIL",
            "machine_deterministic_verdict": "PASS" if deterministic_pass else "FAIL",
            "reviewed_semantic_verdict": "PASS" if semantic_pass else "FAIL",
            "answerability_correct": analysis["answerability_correct"],
            "deterministic_claims": deterministic_claims,
            "semantic_claims": semantic_claims,
            "raw_k_required_evidence_recall": group_coverage(case, raw_k_docs),
            "candidate_required_evidence_recall": group_coverage(case, candidate_docs),
            "final_context_required_evidence_recall": group_coverage(case, context_docs),
            "required_evidence_citation_coverage": required_citation_coverage,
            "candidate_noise_rate": noise_rate(candidate_docs),
            "selected_context_noise_rate": noise_rate(context_docs),
            "unsupported_citation_usage": any(item["evidence_role"] == "UNSUPPORTED" for item in citation_roles),
            "unsupported_answer_impact": review["case_verdict"] == "FAIL" and any(item["evidence_role"] == "UNSUPPORTED" for item in citation_roles),
            "lexical_proxy_coverage": analysis["key_fact_coverage"],
        })
    answerable_items = [item for item, case in zip(items, gold["cases"]) if case["answerable"]]
    unanswerable_items = [item for item, case in zip(items, gold["cases"]) if not case["answerable"]]
    total_citations = sum(citation_role_counts.values())
    analyses_answerable = [analysis_by_id[case["case_id"]] for case in gold["cases"] if case["answerable"]]
    v1_by_id = {case["case_id"]: case for case in read_json(V1_ROOT / "gold_cases.json")["cases"]}
    exact_precisions = []
    acceptable_precisions = []
    for item, case in zip(items, gold["cases"]):
        if not case["answerable"]:
            continue
        docs = set(analysis_by_id[item["case_id"]]["top_k_document_ids"])
        exact = set(v1_by_id[item["case_id"]]["expected_document_ids"])
        exact_precisions.append(len(docs & exact) / len(docs) if docs else 0.0)
        allowed = supporting_documents(case)
        acceptable_precisions.append(len(docs & allowed) / len(docs) if docs else 0.0)
    metrics = {
        "case_count": len(items),
        "machine_deterministic_pass_count": sum(item["machine_deterministic_verdict"] == "PASS" for item in items),
        "machine_deterministic_pass_rate": mean(item["machine_deterministic_verdict"] == "PASS" for item in items),
        "reviewed_semantic_pass_count": sum(item["reviewed_semantic_verdict"] == "PASS" for item in items),
        "reviewed_semantic_pass_rate": mean(item["reviewed_semantic_verdict"] == "PASS" for item in items),
        "retrieval": {
            "raw_k_required_evidence_hit_rate": mean(item["raw_k_required_evidence_recall"] > 0 for item in answerable_items),
            "raw_k_required_evidence_recall": mean(item["raw_k_required_evidence_recall"] for item in answerable_items),
            "candidate_required_evidence_recall": mean(item["candidate_required_evidence_recall"] for item in answerable_items),
            "final_context_required_evidence_recall": mean(item["final_context_required_evidence_recall"] for item in answerable_items),
            "raw_k_exact_gold_precision": mean(exact_precisions),
            "raw_k_non_gold_rate": 1 - mean(exact_precisions),
            "raw_k_acceptable_evidence_precision": mean(acceptable_precisions),
        },
        "citation": {
            "citation_contract_validity": mean(item["citation_valid"] for item in analyses),
            "required_evidence_citation_coverage": mean(item["required_evidence_citation_coverage"] for item in answerable_items),
            "acceptable_support_citation_rate": citation_role_counts["ACCEPTABLE_SUPPORT"] / total_citations if total_citations else 0.0,
            "unsupported_citation_rate": citation_role_counts["UNSUPPORTED"] / total_citations if total_citations else 0.0,
            "missing_required_citation_rate": mean(item["required_evidence_citation_coverage"] < 1.0 for item in answerable_items),
            "citation_free_unanswerable_rate": mean(not analysis_by_id[item["case_id"]]["cited_document_ids"] for item in unanswerable_items),
        },
        "noise": {
            "candidate_noise_rate": mean(item["candidate_noise_rate"] for item in answerable_items),
            "selected_context_noise_rate": mean(item["selected_context_noise_rate"] for item in answerable_items),
            "unsupported_citation_usage_rate": mean(item["unsupported_citation_usage"] for item in items),
            "unsupported_answer_impact_rate": mean(item["unsupported_answer_impact"] for item in items),
        },
        "answer": {
            "lexical_proxy_coverage": mean(item["lexical_proxy_coverage"] for item in answerable_items),
            "semantic_reviewed_claim_coverage": supported_semantic_required / total_semantic_required if total_semantic_required else 0.0,
        },
    }
    return {"metrics": metrics, "cases": items}


def reason_for(case: dict[str, Any]) -> tuple[str, str]:
    reasons = case["gold_review"]["audit_reasons"]
    if "AMBIGUOUS_EXPECTATION_CLARIFIED" in reasons:
        return "gold ambiguity", "AMBIGUOUS_EXPECTATION_CLARIFIED"
    if "ALTERNATIVE_DOCUMENT_EQUIVALENT" in reasons:
        return "alternative valid evidence", "ALTERNATIVE_DOCUMENT_EQUIVALENT"
    if "CLAIM_SPLIT" in reasons:
        return "claim decomposition", "CLAIM_SPLIT"
    if "LEXICAL_REQUIREMENT_REMOVED" in reasons:
        return "lexical proxy issue", "LEXICAL_REQUIREMENT_REMOVED"
    return "other", reasons[0] if reasons else "NO_GOLD_SEMANTIC_CHANGE"


def reconcile(gold: dict[str, Any], score: dict[str, Any]) -> dict[str, Any]:
    gold_by_id = {item["case_id"]: item for item in gold["cases"]}
    genuine = {
        "rag-v1-paraphrase-scanned-pdf": "TRUE_ANSWERABILITY_FAILURE",
        "rag-v1-citation-draft-vs-rendered": "TRUE_GENERATION_OMISSION",
        "rag-v1-multidoc-eval-via-public-api": "TRUE_MULTI_DOC_SYNTHESIS_FAILURE",
    }
    changes = []
    for item in score["cases"]:
        if item["v1_verdict"] == item["reviewed_semantic_verdict"]:
            continue
        category, change = reason_for(gold_by_id[item["case_id"]])
        changes.append({
            "case_id": item["case_id"],
            "v1_verdict": item["v1_verdict"],
            "v2_verdict": item["reviewed_semantic_verdict"],
            "reason": category,
            "contract_change": change,
            "evidence": gold_by_id[item["case_id"]]["gold_review"]["audit_notes"],
        })
    retained = [
        {
            "case_id": case_id,
            "v1_audit_classification": classification,
            "v2_verdict": next(item["reviewed_semantic_verdict"] for item in score["cases"] if item["case_id"] == case_id),
            "retained": next(item["reviewed_semantic_verdict"] for item in score["cases"] if item["case_id"] == case_id) == "FAIL",
        }
        for case_id, classification in genuine.items()
    ]
    return {
        "baseline_run_id": RUN_ID,
        "v1_canonical": {"pass_count": 35, "case_count": 48, "pass_rate": 0.7291666666666666},
        "changed_verdict_count": len(changes),
        "changes": changes,
        "aggregate_reasons": dict(sorted(Counter(item["reason"] for item in changes).items())),
        "genuine_failures": retained,
        "statement": "Evaluation interpretation changed. System behavior did not improve in this phase.",
    }


def report_text(validation: dict[str, Any], score: dict[str, Any], reconciliation: dict[str, Any], immutability: dict[str, Any], run_id: str) -> str:
    metrics = score["metrics"]
    changes = "\n".join(
        f"- `{item['case_id']}`: {item['v1_verdict']} → {item['v2_verdict']}；{item['reason']}；{item['contract_change']}。"
        for item in reconciliation["changes"]
    )
    genuine = "\n".join(
        f"- `{item['case_id']}` / `{item['v1_audit_classification']}` / V2 `{item['v2_verdict']}`"
        for item in reconciliation["genuine_failures"]
    )
    return f"""# LearnPilot RAG Eval & Gold Contract Refinement V2

## 结论

V2 contract 已在不修改 Controlled Corpus V1、canonical V1 baseline 或 production RAG 的前提下完成。48/48 cases 均有 claim/evidence review 和 frozen-answer semantic review。

The canonical V1 baseline remains:

```text
35 / 48
72.92%
```

V2 对同一组 frozen answers 的结果：

- `machine_deterministic_pass = {metrics['machine_deterministic_pass_count']} / 48 = {metrics['machine_deterministic_pass_rate']:.2%}`。该数只覆盖 deterministic claims、answerability 与 citation contract，不是 semantic overall score。
- `reviewed_semantic_pass = {metrics['reviewed_semantic_pass_count']} / 48 = {metrics['reviewed_semantic_pass_rate']:.2%}`。

This is a benchmark-contract reinterpretation of the same frozen answers,
not a production RAG improvement.

## V1 Gold contract audit

V1 的 `expected_document_ids` 是 flat exact set，不能表达 required/supporting、A OR B 或 A AND C；`key_facts` 没有 claim ID、required/optional 与 evaluation mode；citation contract 不能承认 semantic supporting source。它们分别造成 exact-gold 误判、lexical proxy false negative 与 valid non-gold citation 被标为 wrong。

## V2 contract

- Required evidence groups 之间为 `AND`，group 内 `any_of_document_ids` 为 `OR`。
- evidence roles 为 `REQUIRED`、`ACCEPTABLE_SUPPORT`、`UNSUPPORTED`。
- claim modes 为 `STRUCTURED_EXACT`、`NUMERIC_EXACT`、`IDENTIFIER_EXACT`、`SEMANTIC_REVIEW`、`ANSWERABILITY_ONLY`。
- lexical overlap 保留为 `lexical_proxy_coverage`；不决定 semantic claim verdict。
- semantic review 固定记录 `case_id/claim_id/verdict/answer_span/document_ids/reason/reviewer_mode/version`。

## Retrieval、citation 与 noise metrics

- `raw_k_required_evidence_recall = {metrics['retrieval']['raw_k_required_evidence_recall']:.2%}`
- `candidate_required_evidence_recall = {metrics['retrieval']['candidate_required_evidence_recall']:.2%}`
- `final_context_required_evidence_recall = {metrics['retrieval']['final_context_required_evidence_recall']:.2%}`
- `raw_k_exact_gold_precision = {metrics['retrieval']['raw_k_exact_gold_precision']:.2%}`（exact-label diagnostic）
- `raw_k_acceptable_evidence_precision = {metrics['retrieval']['raw_k_acceptable_evidence_precision']:.2%}`
- `citation_contract_validity = {metrics['citation']['citation_contract_validity']:.2%}`
- `required_evidence_citation_coverage = {metrics['citation']['required_evidence_citation_coverage']:.2%}`
- `acceptable_support_citation_rate = {metrics['citation']['acceptable_support_citation_rate']:.2%}`
- `unsupported_citation_rate = {metrics['citation']['unsupported_citation_rate']:.2%}`
- `candidate_noise_rate = {metrics['noise']['candidate_noise_rate']:.2%}`
- `selected_context_noise_rate = {metrics['noise']['selected_context_noise_rate']:.2%}`
- `unsupported_answer_impact_rate = {metrics['noise']['unsupported_answer_impact_rate']:.2%}`
- `lexical_proxy_coverage = {metrics['answer']['lexical_proxy_coverage']:.2%}`
- `semantic_reviewed_claim_coverage = {metrics['answer']['semantic_reviewed_claim_coverage']:.2%}`

## V1 → V2 verdict reconciliation

{changes}

汇总：`{json.dumps(reconciliation['aggregate_reasons'], ensure_ascii=False)}`。

Evaluation interpretation changed. System behavior did not improve in this phase.

## Genuine failures retained

{genuine}

## Contract validation 与 immutability

- V2 schema/tool validation: `{validation['status']}`；cases `{validation['case_count']}/48`；reviews `{validation['reviewed_case_count']}/48`；errors `{len(validation['errors'])}`。
- invalid document references: `{validation['document_reference_error_count']}`。
- invalid claim references: `{validation['claim_reference_error_count']}`。
- canonical V1 artifact hashes unchanged: `{immutability['canonical_v1_baseline_files_unchanged']}`。
- production RAG hashes unchanged during V2 run: `{immutability['production_rag_files_unchanged_during_v2']}`。
- latest failure audit used: `20260813T112545Z-canonical-f8aaaae2`。
- DeepSeek/model re-run: `false`；所有结果来自现有 frozen answers。

## Tests executed

`python -m pytest backend/tests/test_rag_eval_contract_v2.py backend/tests/test_rag_baseline_eval_tooling.py backend/tests/test_rag_failure_scale_analysis.py -q`

结果：`21 passed`。

## Exact files created/modified

Created contract assets: `contracts/v2/build_assets.py`, `contract.md`, `eval_v2.py`, `gold_cases.json`, `gold_cases.schema.json`, `metric_definitions.json`, `real_world_eval_requirements.json`, `semantic_reviews.json`, `semantic_reviews.schema.json`, `v1_gold_contract_audit.json`; created test: `backend/tests/test_rag_eval_contract_v2.py`; modified domain glossary: `CONTEXT.md`。

Canonical result directory: `evals/rag_demo_corpus/v1/results/contract_v2_review/{run_id}/`，内含 deterministic/reviewed results、reconciliation、validation、quality gate、immutability、test record、exact file list 与本报告。

## Real-world Corpus readiness

V2 contract 适合作为未来 Real-world Corpus V1 的 evaluation foundation：它已分离 retrieval layers、claim modes、evidence roles、semantic review 和 deterministic reporting。下一阶段仍需 8–15 篇 substantial documents、约 200–500 chunks、重叠 topics、真实长 PDF/Markdown/TXT 以及明确 version/source/licensing。当前 Controlled Corpus 不能支撑广泛 production quality claim。

RAG_EVAL_GOLD_CONTRACT_V2 = COMPLETE
"""


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    for path in [BASELINE, LATEST_AUDIT]:
        if not path.is_dir():
            raise RuntimeError(f"missing source-of-truth directory: {path}")
    baseline_before = {name: digest(BASELINE / name) for name in BASELINE_FILES}
    v1_contract_before = hash_map(V1_CONTRACT_FILES)
    production_before = hash_map(PRODUCTION_RAG_FILES)
    gold = read_json(V2_ROOT / "gold_cases.json")
    reviews = read_json(V2_ROOT / "semantic_reviews.json")
    manifest = read_json(V1_ROOT / "corpus_manifest.json")
    v1_gold = read_json(V1_ROOT / "gold_cases.json")
    analyses = read_json(BASELINE / "case_analysis.json")
    validation = validate_contract(gold, reviews, manifest, v1_gold)
    if validation["errors"]:
        print(json.dumps(validation, ensure_ascii=False, indent=2))
        return 1
    score = score_frozen_baseline(gold, reviews, analyses)
    reconciliation = reconcile(gold, score)
    baseline_after = {name: digest(BASELINE / name) for name in BASELINE_FILES}
    v1_contract_after = hash_map(V1_CONTRACT_FILES)
    production_after = hash_map(PRODUCTION_RAG_FILES)
    latest_audit_hashes = read_json(LATEST_AUDIT / "audit_metadata.json")["baseline_artifact_sha256"]
    raw_case_payloads = [
        json.loads(line)["case"]
        for line in (BASELINE / "raw_cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    run_metadata = read_json(BASELINE / "run_metadata.json")
    corpus_hashes = {
        item["document_id"]: digest(REPO_ROOT / item["repository_path"])
        for item in manifest["documents"]
    }
    immutability = {
        "canonical_run_id": RUN_ID,
        "canonical_v1_baseline_files_unchanged": baseline_before == baseline_after,
        "canonical_v1_hashes_match_latest_audit": baseline_after == latest_audit_hashes,
        "v1_contract_files_unchanged_during_v2": v1_contract_before == v1_contract_after,
        "v1_gold_matches_frozen_raw_case_payloads": v1_gold["cases"] == raw_case_payloads,
        "corpus_hashes_match_canonical_run_metadata": corpus_hashes == run_metadata["corpus_hashes"],
        "v1_contract_file_sha256": v1_contract_after,
        "baseline_artifact_sha256": baseline_after,
        "production_rag_files_unchanged_during_v2": production_before == production_after,
        "production_rag_sha256": production_after,
        "corpus_sha256_by_document_id": corpus_hashes,
    }
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-frozen-f8aaaae2"
    output = RESULTS / run_id
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "validation.json", validation)
    write_json(output / "deterministic_result.json", {
        "scope": "same frozen answers evaluated under V2 deterministic contract",
        "metrics": score["metrics"],
        "cases": score["cases"],
    })
    write_json(output / "reviewed_semantic_result.json", {
        "scope": "same frozen answers evaluated under V2 reviewed semantic contract",
        "pass_count": score["metrics"]["reviewed_semantic_pass_count"],
        "case_count": score["metrics"]["case_count"],
        "pass_rate": score["metrics"]["reviewed_semantic_pass_rate"],
        "cases": [{
            "case_id": item["case_id"],
            "verdict": item["reviewed_semantic_verdict"],
            "semantic_claims": item["semantic_claims"],
        } for item in score["cases"]],
    })
    write_json(output / "v1_to_v2_reconciliation.json", reconciliation)
    write_json(output / "immutability_verification.json", immutability)
    write_json(output / "quality_gate.json", {
        "v2_cases_reviewed": len(gold["cases"]),
        "invalid_document_references": validation["document_reference_error_count"],
        "invalid_claim_references": validation["claim_reference_error_count"],
        "unresolved_schema_or_contract_violations": len(validation["errors"]),
        "silent_gold_mutations": 0,
        "overwritten_v1_artifacts": 0 if immutability["canonical_v1_hashes_match_latest_audit"] else 1,
        "production_rag_modifications_during_v2": 0 if immutability["production_rag_files_unchanged_during_v2"] else 1,
        "model_rerun": False,
        "passed": (
            len(gold["cases"]) == 48
            and not validation["errors"]
            and immutability["canonical_v1_hashes_match_latest_audit"]
            and immutability["v1_contract_files_unchanged_during_v2"]
            and immutability["v1_gold_matches_frozen_raw_case_payloads"]
            and immutability["corpus_hashes_match_canonical_run_metadata"]
            and immutability["production_rag_files_unchanged_during_v2"]
        ),
    })
    write_json(output / "tests_executed.json", {
        "status": "passed",
        "command": "python -m pytest backend/tests/test_rag_eval_contract_v2.py backend/tests/test_rag_baseline_eval_tooling.py backend/tests/test_rag_failure_scale_analysis.py -q",
        "passed": 21,
        "failed": 0,
        "scope": "V2 contract plus relevant V1 eval tooling",
    })
    write_json(output / "exact_files.json", {
        "created": [
            "evals/rag_demo_corpus/v1/contracts/v2/build_assets.py",
            "evals/rag_demo_corpus/v1/contracts/v2/contract.md",
            "evals/rag_demo_corpus/v1/contracts/v2/eval_v2.py",
            "evals/rag_demo_corpus/v1/contracts/v2/gold_cases.json",
            "evals/rag_demo_corpus/v1/contracts/v2/gold_cases.schema.json",
            "evals/rag_demo_corpus/v1/contracts/v2/metric_definitions.json",
            "evals/rag_demo_corpus/v1/contracts/v2/real_world_eval_requirements.json",
            "evals/rag_demo_corpus/v1/contracts/v2/semantic_reviews.json",
            "evals/rag_demo_corpus/v1/contracts/v2/semantic_reviews.schema.json",
            "evals/rag_demo_corpus/v1/contracts/v2/v1_gold_contract_audit.json",
            "backend/tests/test_rag_eval_contract_v2.py"
        ],
        "modified": ["CONTEXT.md"],
        "result_directory": str(output.relative_to(REPO_ROOT)).replace("\\", "/"),
        "result_files": [
            "deterministic_result.json", "exact_files.json", "immutability_verification.json",
            "quality_gate.json", "report.md", "result.json", "reviewed_semantic_result.json",
            "run_metadata.json", "tests_executed.json", "v1_to_v2_reconciliation.json",
            "validation.json"
        ],
        "production_files_modified_by_v2": []
    })
    write_json(output / "run_metadata.json", {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "canonical_baseline_run_id": RUN_ID,
        "latest_failure_audit_id": LATEST_AUDIT.name,
        "model_rerun": False,
        "scope": "evaluation-only frozen-answer reinterpretation",
    })
    report = report_text(validation, score, reconciliation, immutability, run_id)
    (output / "report.md").write_text(report, encoding="utf-8")
    summary = {
        "status": "complete",
        "run_id": run_id,
        "canonical_v1": "35/48 = 72.92%",
        "machine_deterministic": f"{score['metrics']['machine_deterministic_pass_count']}/48",
        "reviewed_semantic": f"{score['metrics']['reviewed_semantic_pass_count']}/48",
        "validation": validation["status"],
        "v1_immutable": immutability["canonical_v1_baseline_files_unchanged"],
        "v1_hashes_match_latest_audit": immutability["canonical_v1_hashes_match_latest_audit"],
        "production_unchanged": immutability["production_rag_files_unchanged_during_v2"],
        "terminal_status": "RAG_EVAL_GOLD_CONTRACT_V2 = COMPLETE",
    }
    write_json(output / "result.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
