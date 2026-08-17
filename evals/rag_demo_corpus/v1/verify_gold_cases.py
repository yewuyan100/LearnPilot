"""Independent evidence pass for the frozen 48-case baseline gold set."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent


def normalized_terms(text: str) -> set[str]:
    terms = {
        item.lower()
        for item in re.findall(r"[A-Za-z][A-Za-z0-9_.-]+|\d+(?:\.\d+)?", text)
        if len(item) >= 2 or item.isdigit()
    }
    for sequence in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        terms.update(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return terms


def main() -> int:
    manifest = json.loads((ROOT / "corpus_manifest.json").read_text(encoding="utf-8"))
    gold = json.loads((ROOT / "gold_cases.json").read_text(encoding="utf-8"))
    documents = {
        item["document_id"]: (
            ROOT.parents[2] / item["repository_path"]
        ).read_text(encoding="utf-8")
        for item in manifest["documents"]
    }
    errors: list[str] = []
    reviews: list[dict] = []
    for case in gold["cases"]:
        case_errors: list[str] = []
        expected = case["expected_document_ids"]
        combined = "\n".join(documents[item] for item in expected)
        if case["answerable"]:
            for fact in case["key_facts"]:
                terms = normalized_terms(fact)
                overlap = terms & normalized_terms(combined)
                if terms and not overlap:
                    case_errors.append(f"key fact has no lexical evidence: {fact}")
            if not expected:
                case_errors.append("answerable case has no expected documents")
        else:
            if expected or case["key_facts"]:
                case_errors.append("unanswerable case contains expected evidence")
        must_cite = case["citation_expectations"]["must_cite_document_ids"]
        if not set(must_cite).issubset(expected):
            case_errors.append("must-cite documents are outside expected documents")
        reviews.append(
            {
                "case_id": case["case_id"],
                "status": "verified" if not case_errors else "failed",
                "expected_document_ids": expected,
                "key_fact_count": len(case["key_facts"]),
                "notes": case_errors,
            }
        )
        errors.extend(f"{case['case_id']}: {item}" for item in case_errors)
    result = {
        "status": "verified" if not errors else "failed",
        "case_count": len(reviews),
        "type_distribution": dict(sorted(Counter(item["type"] for item in gold["cases"]).items())),
        "reviews": reviews,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
