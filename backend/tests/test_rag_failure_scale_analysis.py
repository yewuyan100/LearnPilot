from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "evals" / "rag_demo_corpus" / "v1" / "analyze_failure_scale.py"
sys.path.insert(0, str(TOOL_PATH.parent))
SPEC = importlib.util.spec_from_file_location("failure_scale_analysis", TOOL_PATH)
assert SPEC and SPEC.loader
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)


def test_review_set_matches_all_canonical_machine_failures() -> None:
    cases = json.loads((TOOL.BASELINE / "case_analysis.json").read_text(encoding="utf-8"))
    failed = {item["case_id"] for item in cases if not item["passed"]}
    assert failed == set(TOOL.REVIEWS)
    assert Counter(item["reviewed_taxonomy"] for item in TOOL.REVIEWS.values()) == Counter({
        "GOLD_EXPECTATION_TOO_STRICT": 6,
        "GOLD_EXPECTATION_AMBIGUOUS": 1,
        "LEXICAL_PROXY_FALSE_NEGATIVE": 3,
        "TRUE_ANSWERABILITY_FAILURE": 1,
        "TRUE_GENERATION_OMISSION": 1,
        "TRUE_MULTI_DOC_SYNTHESIS_FAILURE": 1,
    })


def test_precision_ceiling_explains_sparse_gold_structure() -> None:
    cases = json.loads((TOOL.BASELINE / "case_analysis.json").read_text(encoding="utf-8"))
    result = TOOL.precision_structure(cases)
    assert round(result["macro_theoretical_max_if_six_unique_documents"], 5) == 0.225
    assert round(result["macro_observed_unique_document_ceiling"], 5) == 0.26875
    assert round(result["canonical_source_precision_at_k"], 5) == 0.24625
    assert result["fraction_of_observed_ceiling_achieved"] > 0.91


def test_fallback_is_grounding_repair_not_provider_failover() -> None:
    raw = [json.loads(line) for line in (TOOL.BASELINE / "raw_cases.jsonl").read_text(encoding="utf-8").splitlines()]
    cases = json.loads((TOOL.BASELINE / "case_analysis.json").read_text(encoding="utf-8"))
    result = TOOL.fallback_audit(raw, cases)
    assert result["fallback_count"] == 6
    assert result["actual_types"] == {
        "GROUNDING_REPAIR": 6,
        "QUERY_REWRITE_FALLBACK": 0,
        "PROVIDER_FALLBACK": 0,
    }
    assert all(row["grounding_contract_valid_after_repair"] for row in result["rows"])
