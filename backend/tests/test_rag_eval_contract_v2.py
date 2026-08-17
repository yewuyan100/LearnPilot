from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "evals" / "rag_demo_corpus" / "v1"
V2 = V1 / "contracts" / "v2"
SPEC = importlib.util.spec_from_file_location("rag_eval_v2", V2 / "eval_v2.py")
assert SPEC and SPEC.loader
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)


def load(name: str):
    return json.loads((V2 / name).read_text(encoding="utf-8"))


def contract_inputs():
    return (
        load("gold_cases.json"),
        load("semantic_reviews.json"),
        json.loads((V1 / "corpus_manifest.json").read_text(encoding="utf-8")),
        json.loads((V1 / "gold_cases.json").read_text(encoding="utf-8")),
    )


def case(case_id: str):
    return next(item for item in load("gold_cases.json")["cases"] if item["case_id"] == case_id)


def test_v2_contract_validates_all_48_cases_and_references() -> None:
    validation = TOOL.validate_contract(*contract_inputs())
    assert validation == {
        "status": "valid",
        "case_count": 48,
        "reviewed_case_count": 48,
        "changed_gold_semantics_case_count": 16,
        "document_reference_error_count": 0,
        "claim_reference_error_count": 0,
        "errors": [],
    }


def test_v2_schema_documents_are_json_schema_2020_12() -> None:
    for name in ("gold_cases.schema.json", "semantic_reviews.schema.json"):
        schema = load(name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["type"] == "object"
        assert schema["$id"].startswith("https://learnpilot.local/schemas/")


def test_single_document_or_required_evidence_group() -> None:
    target = case("rag-v1-citation-source-label-lifetime")
    stable = next(item for item in target["evidence_groups"] if item["evidence_group_id"] == "eg-stable-document-id")
    assert stable["required"] is True
    assert set(stable["any_of_document_ids"]) == {"lp-rag-v1-d01", "lp-rag-v1-d03"}
    assert TOOL.group_coverage(target, ["lp-rag-v1-d03", "lp-rag-v1-a03"]) == 1.0


def test_multi_document_and_requirement() -> None:
    target = case("rag-v1-multidoc-eval-via-public-api")
    assert len(TOOL.required_groups(target)) == 3
    assert TOOL.group_coverage(target, ["lp-rag-v1-c01", "lp-rag-v1-d01"]) == 1.0
    assert TOOL.group_coverage(target, ["lp-rag-v1-c01"]) < 1.0
    assert [item["evidence_group_ids"] for item in target["claims"]] == [
        ["eg-public-http"], ["eg-isolation"], ["eg-comparable-metadata"]
    ]


def test_alternative_valid_supporting_document_is_not_wrong() -> None:
    target = case("rag-v1-paraphrase-delete-history")
    assert target["acceptable_supporting_document_ids"] == ["lp-rag-v1-a04"]
    assert "lp-rag-v1-a04" in TOOL.supporting_documents(target)


def test_structured_exact_and_numeric_exact_claims() -> None:
    api = case("rag-v1-single-api-error-shape")["claims"][0]
    chunk = case("rag-v1-single-default-chunk-size")["claims"]
    assert api["evaluation_mode"] == "STRUCTURED_EXACT"
    assert TOOL.deterministic_match('{"error":{"code":"x","message":"m","details":{}}}', api["deterministic_match"])
    assert all(item["evaluation_mode"] == "NUMERIC_EXACT" for item in chunk)
    assert TOOL.deterministic_match("800 and 120", chunk[0]["deterministic_match"])


def test_semantic_review_ignores_lexical_false_negative() -> None:
    review = next(item for item in load("semantic_reviews.json")["cases"] if item["case_id"] == "rag-v1-paraphrase-index-derived-state")
    assert review["case_verdict"] == "PASS"
    assert all(item["verdict"] == "SUPPORTED" for item in review["claim_reviews"])


def test_unsupported_citation_fails_reviewed_semantic_case() -> None:
    gold, reviews, _, _ = contract_inputs()
    analyses = json.loads((TOOL.BASELINE / "case_analysis.json").read_text(encoding="utf-8"))
    modified = deepcopy(reviews)
    target = next(item for item in modified["cases"] if item["case_id"] == "rag-v1-single-score-threshold")
    target["citation_reviews"][0]["evidence_role"] = "UNSUPPORTED"
    target["citation_reviews"][0]["materially_supports_answer"] = False
    scored = TOOL.score_frozen_baseline(gold, modified, analyses)
    result = next(item for item in scored["cases"] if item["case_id"] == target["case_id"])
    assert result["reviewed_semantic_verdict"] == "FAIL"


def test_valid_non_gold_supporting_citation_passes() -> None:
    gold, reviews, _, _ = contract_inputs()
    analyses = json.loads((TOOL.BASELINE / "case_analysis.json").read_text(encoding="utf-8"))
    scored = TOOL.score_frozen_baseline(gold, reviews, analyses)
    result = next(item for item in scored["cases"] if item["case_id"] == "rag-v1-paraphrase-delete-history")
    review = next(item for item in reviews["cases"] if item["case_id"] == result["case_id"])
    assert any(item["evidence_role"] == "ACCEPTABLE_SUPPORT" for item in review["citation_reviews"])
    assert result["reviewed_semantic_verdict"] == "PASS"


def test_unanswerable_contract_has_no_required_evidence_or_citations() -> None:
    target = case("rag-v1-unanswerable-weather")
    review = next(item for item in load("semantic_reviews.json")["cases"] if item["case_id"] == target["case_id"])
    assert target["evidence_groups"] == []
    assert target["claims"][0]["evaluation_mode"] == "ANSWERABILITY_ONLY"
    assert target["citation_contract"]["forbid_citations"] is True
    assert review["citation_reviews"] == []
    assert review["case_verdict"] == "PASS"


def test_ambiguous_gold_requires_audit_reason() -> None:
    gold, reviews, manifest, v1_gold = contract_inputs()
    modified = deepcopy(gold)
    target = next(item for item in modified["cases"] if item["case_id"] == "rag-v1-multidoc-http-transaction-errors")
    target["gold_review"]["audit_reasons"] = []
    validation = TOOL.validate_contract(modified, reviews, manifest, v1_gold)
    assert any("semantic change missing audit reason" in item for item in validation["errors"])


def test_review_referencing_nonexistent_claim_is_invalid() -> None:
    gold, reviews, manifest, v1_gold = contract_inputs()
    modified = deepcopy(reviews)
    modified["cases"][0]["claim_reviews"][0]["claim_id"] = "missing-claim"
    validation = TOOL.validate_contract(gold, modified, manifest, v1_gold)
    assert validation["claim_reference_error_count"] > 0


def test_v1_artifact_immutability_matches_latest_audit_hashes() -> None:
    expected = json.loads((TOOL.LATEST_AUDIT / "audit_metadata.json").read_text(encoding="utf-8"))["baseline_artifact_sha256"]
    actual = {name: sha256((TOOL.BASELINE / name).read_bytes()).hexdigest() for name in TOOL.BASELINE_FILES}
    assert actual == expected
    assert json.loads((TOOL.BASELINE / "metrics.json").read_text(encoding="utf-8"))["pass_count"] == 35


def test_v1_to_v2_reconciliation_retains_genuine_failures_and_new_control_failure() -> None:
    gold, reviews, _, _ = contract_inputs()
    analyses = json.loads((TOOL.BASELINE / "case_analysis.json").read_text(encoding="utf-8"))
    reconciliation = TOOL.reconcile(gold, TOOL.score_frozen_baseline(gold, reviews, analyses))
    assert all(item["retained"] for item in reconciliation["genuine_failures"])
    assert any(item["case_id"] == "rag-v1-citation-multifact-sources" and item["v1_verdict"] == "PASS" and item["v2_verdict"] == "FAIL" for item in reconciliation["changes"])
    assert reconciliation["changed_verdict_count"] == 11


def test_frozen_score_contract_is_46_deterministic_and_44_reviewed() -> None:
    gold, reviews, _, _ = contract_inputs()
    analyses = json.loads((TOOL.BASELINE / "case_analysis.json").read_text(encoding="utf-8"))
    metrics = TOOL.score_frozen_baseline(gold, reviews, analyses)["metrics"]
    assert metrics["machine_deterministic_pass_count"] == 46
    assert metrics["reviewed_semantic_pass_count"] == 44
    assert metrics["citation"]["unsupported_citation_rate"] == 0
    assert metrics["answer"]["semantic_reviewed_claim_coverage"] > metrics["answer"]["lexical_proxy_coverage"]
