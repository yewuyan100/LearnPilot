"""Validate the versioned RAG demo corpus without touching runtime storage."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "corpus_manifest.json"
GOLD_PATH = ROOT / "gold_cases.json"
MANIFEST_SCHEMA_PATH = ROOT / "corpus_manifest.schema.json"
GOLD_SCHEMA_PATH = ROOT / "gold_cases.schema.json"
ALLOWED_TOPICS = {
    "rag_retrieval",
    "agent_engineering",
    "ai_app_backend",
    "evaluation_production_reliability",
}
ALLOWED_CASE_TYPES = {
    "single_doc_fact",
    "semantic_paraphrase",
    "multi_doc",
    "rerank_disambiguation",
    "citation_sensitive",
    "unanswerable",
}
DOCUMENT_ID = re.compile(r"^lp-rag-v1-[a-d][0-9]{2}$")
CASE_ID = re.compile(r"^rag-v1-[a-z0-9-]+$")


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_schema_documents(errors: list[str]) -> None:
    for path in (MANIFEST_SCHEMA_PATH, GOLD_SCHEMA_PATH):
        schema = load_json(path)
        require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", f"{path.name} must use JSON Schema 2020-12", errors)
        require(schema.get("type") == "object", f"{path.name} root type must be object", errors)
        require(bool(schema.get("$id")), f"{path.name} must declare $id", errors)


def validate_manifest(errors: list[str]) -> tuple[dict, set[str]]:
    manifest = load_json(MANIFEST_PATH)
    require(manifest.get("schema_version") == "1.0.0", "manifest schema_version must be 1.0.0", errors)
    require(manifest.get("corpus_id") == "learnpilot-rag-demo-corpus", "unexpected corpus_id", errors)
    require(manifest.get("corpus_version") == "v1", "corpus_version must be v1", errors)
    documents = manifest.get("documents")
    require(isinstance(documents, list), "documents must be an array", errors)
    if not isinstance(documents, list):
        return manifest, set()
    require(10 <= len(documents) <= 15, "manifest must contain 10-15 documents", errors)
    ids: set[str] = set()
    paths: set[str] = set()
    topic_counts: Counter[str] = Counter()
    required = {
        "document_id", "title", "topic", "source_type", "source_reference",
        "version_or_date", "language", "expected_ingestion_type",
        "repository_path", "sha256", "notes",
    }
    for index, document in enumerate(documents):
        label = f"documents[{index}]"
        require(isinstance(document, dict), f"{label} must be an object", errors)
        if not isinstance(document, dict):
            continue
        require(set(document) == required, f"{label} fields do not match contract", errors)
        document_id = document.get("document_id", "")
        require(bool(DOCUMENT_ID.fullmatch(document_id)), f"{label} has invalid document_id", errors)
        require(document_id not in ids, f"duplicate document_id: {document_id}", errors)
        ids.add(document_id)
        topic = document.get("topic")
        require(topic in ALLOWED_TOPICS, f"{label} has invalid topic", errors)
        topic_counts[topic] += 1
        require(document.get("language") == "zh-CN", f"{label} language must be zh-CN", errors)
        require(document.get("expected_ingestion_type") == "md", f"{label} must ingest as md", errors)
        relative = document.get("repository_path", "")
        require(relative not in paths, f"duplicate repository_path: {relative}", errors)
        paths.add(relative)
        file_path = ROOT.parents[2] / relative
        require(file_path.is_file(), f"missing corpus document: {relative}", errors)
        if file_path.is_file():
            actual = sha256(file_path.read_bytes()).hexdigest()
            require(actual == document.get("sha256"), f"sha256 mismatch: {relative}", errors)
    require(set(topic_counts) == ALLOWED_TOPICS, "all four topic clusters must be represented", errors)
    return manifest, ids


def validate_gold(errors: list[str], document_ids: set[str]) -> dict:
    gold = load_json(GOLD_PATH)
    require(gold.get("schema_version") == "1.0.0", "gold schema_version must be 1.0.0", errors)
    require(gold.get("corpus_id") == "learnpilot-rag-demo-corpus", "gold corpus_id mismatch", errors)
    require(gold.get("corpus_version") == "v1", "gold corpus_version mismatch", errors)
    cases = gold.get("cases")
    require(isinstance(cases, list), "gold cases must be an array", errors)
    if not isinstance(cases, list):
        return gold
    seen: set[str] = set()
    type_counts: Counter[str] = Counter()
    required = {
        "case_id", "question", "difficulty", "type", "answerable",
        "expected_document_ids", "key_facts", "citation_expectations",
    }
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        require(isinstance(case, dict), f"{label} must be an object", errors)
        if not isinstance(case, dict):
            continue
        require(required.issubset(case), f"{label} missing required fields", errors)
        case_id = case.get("case_id", "")
        require(bool(CASE_ID.fullmatch(case_id)), f"{label} has invalid case_id", errors)
        require(case_id not in seen, f"duplicate case_id: {case_id}", errors)
        seen.add(case_id)
        case_type = case.get("type")
        require(case_type in ALLOWED_CASE_TYPES, f"{label} has invalid type", errors)
        type_counts[case_type] += 1
        expected = case.get("expected_document_ids", [])
        facts = case.get("key_facts", [])
        require(isinstance(expected, list), f"{label} expected_document_ids must be an array", errors)
        if isinstance(expected, list):
            require(set(expected).issubset(document_ids), f"{label} references unknown document_id", errors)
            require(len(expected) == len(set(expected)), f"{label} repeats a document_id", errors)
        answerable = case.get("answerable") is True
        if answerable:
            require(bool(expected), f"{label} answerable case needs expected documents", errors)
            require(bool(facts), f"{label} answerable case needs key facts", errors)
        else:
            require(case_type == "unanswerable", f"{label} false answerable requires unanswerable type", errors)
            require(expected == [], f"{label} unanswerable expected documents must be empty", errors)
            require(facts == [], f"{label} unanswerable key facts must be empty", errors)
        if case_type == "multi_doc":
            require(len(expected) >= 2, f"{label} multi_doc requires at least two documents", errors)
        expectations = case.get("citation_expectations", {})
        if isinstance(expectations, dict):
            must_cite = expectations.get("must_cite_document_ids", [])
            require(
                set(must_cite).issubset(set(expected)),
                f"{label} must-cite documents must be expected documents",
                errors,
            )
            if answerable:
                require(
                    expectations.get("minimum_distinct_documents", 0)
                    <= len(expected),
                    f"{label} citation minimum exceeds expected documents",
                    errors,
                )
    if cases:
        require(len(cases) == 48, "baseline gold set must contain exactly 48 cases", errors)
        require(
            type_counts == Counter({case_type: 8 for case_type in ALLOWED_CASE_TYPES}),
            "baseline gold set must contain exactly 8 cases of each type",
            errors,
        )
    return gold


def main() -> int:
    errors: list[str] = []
    validate_schema_documents(errors)
    manifest, document_ids = validate_manifest(errors)
    gold = validate_gold(errors, document_ids)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(json.dumps({
        "status": "valid",
        "corpus_version": manifest["corpus_version"],
        "document_count": len(manifest["documents"]),
        "gold_case_count": len(gold["cases"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
