"""Shared, evaluation-only contract helpers for Real-world Gold Dataset V1."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
import re
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[5]
CORPUS_ROOT = REPO_ROOT / "evals" / "rag_real_world_corpus" / "v1"
GOLD_ROOT = Path(__file__).resolve().parent
DRAFT_ROOT = GOLD_ROOT / "draft_shards"

CORE_TYPES = {
    "single_doc_fact": 10,
    "semantic_paraphrase": 10,
    "long_doc_localization": 10,
    "multi_doc_synthesis": 10,
    "source_disambiguation": 10,
    "unanswerable_near_boundary": 10,
}
STRESS_TYPES = {
    "deep_long_doc_localization": 4,
    "cross_topic_multi_doc": 4,
    "high_overlap_source_conflict": 4,
}
TYPE_ORDER = tuple(CORE_TYPES) + tuple(STRESS_TYPES)
TOPICS = {"rag_retrieval", "agent_engineering", "ai_app_backend", "evaluation_reliability"}
LANGUAGES = {"zh-CN", "en"}
DIFFICULTIES = {"easy", "medium", "hard", "stress"}
MOJIBAKE_MARKERS = ("\ufffd", "\u00c3", "\u00e2", "\u951b", "\u9286")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


def json_schema_errors(instance: Any, schema: dict[str, Any]) -> list[str]:
    """Validate the JSON-Schema subset used by the evaluation artifacts.

    The repository intentionally adds no production dependency for evaluation-only data.
    """
    errors: list[str] = []
    root = schema

    def resolve(node: dict[str, Any]) -> dict[str, Any]:
        if "$ref" not in node:
            return node
        ref = node["$ref"]
        if not ref.startswith("#/"):
            errors.append(f"$: unsupported external schema reference {ref}")
            return {}
        target: Any = root
        for part in ref[2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        return target

    def matches_type(value: Any, expected: str) -> bool:
        return {
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "null": value is None,
        }.get(expected, True)

    def visit(value: Any, raw_node: dict[str, Any], path: str) -> None:
        node = resolve(raw_node)
        if "oneOf" in node:
            branch_results = []
            for branch in node["oneOf"]:
                before = len(errors)
                visit(value, branch, path)
                branch_results.append(errors[before:])
                del errors[before:]
            passing = sum(not result for result in branch_results)
            if passing != 1:
                errors.append(f"{path}: expected exactly one matching oneOf branch")
            return
        expected_type = node.get("type")
        if expected_type:
            allowed = expected_type if isinstance(expected_type, list) else [expected_type]
            if not any(matches_type(value, item) for item in allowed):
                errors.append(f"{path}: expected type {allowed}")
                return
        if "const" in node and value != node["const"]:
            errors.append(f"{path}: expected const {node['const']!r}")
        if "enum" in node and value not in node["enum"]:
            errors.append(f"{path}: value is outside enum")
        if isinstance(value, dict):
            required = node.get("required", [])
            for key in required:
                if key not in value:
                    errors.append(f"{path}: missing required property {key}")
            properties = node.get("properties", {})
            if node.get("additionalProperties") is False:
                for key in value:
                    if key not in properties:
                        errors.append(f"{path}: unexpected property {key}")
            for key, child in properties.items():
                if key in value:
                    visit(value[key], child, f"{path}.{key}")
            if len(value) < node.get("minProperties", 0):
                errors.append(f"{path}: too few properties")
        elif isinstance(value, list):
            if len(value) < node.get("minItems", 0) or len(value) > node.get("maxItems", len(value)):
                errors.append(f"{path}: array length outside bounds")
            if node.get("uniqueItems"):
                serialized = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in value]
                if len(serialized) != len(set(serialized)):
                    errors.append(f"{path}: array items are not unique")
            if "items" in node:
                for index, item in enumerate(value):
                    visit(item, node["items"], f"{path}[{index}]")
        elif isinstance(value, str):
            if len(value) < node.get("minLength", 0) or len(value) > node.get("maxLength", len(value)):
                errors.append(f"{path}: string length outside bounds")
            if "pattern" in node and not re.search(node["pattern"], value):
                errors.append(f"{path}: string does not match pattern")
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            if value < node.get("minimum", value):
                errors.append(f"{path}: value below minimum")

    visit(instance, schema, "$")
    return errors


def load_manifest() -> dict[str, Any]:
    return read_json(CORPUS_ROOT / "corpus_manifest.json")


def load_anchor_specs() -> list[dict[str, Any]]:
    return read_json(GOLD_ROOT / "anchor_specs.json")["anchors"]


def spec_index(specs: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {"ev-rw-" + item["id"]: item for item in specs}


def minimum_hitting_documents(groups: list[dict[str, Any]]) -> int:
    if not groups:
        return 0
    documents = sorted({doc for group in groups for doc in group["any_of_document_ids"]})
    for size in range(1, len(documents) + 1):
        for candidate in combinations(documents, size):
            chosen = set(candidate)
            if all(chosen.intersection(group["any_of_document_ids"]) for group in groups):
                return size
    raise ValueError("evidence groups have no document cover")


def expand_raw_case(raw: dict[str, Any], specs: list[dict[str, Any]]) -> dict[str, Any]:
    """Expand the compact stalled-source representation into a file-backed draft case."""
    by_evidence = spec_index(specs)
    slug = raw["slug"]
    groups: list[dict[str, Any]] = []
    for index, raw_group in enumerate(raw["groups"], 1):
        evidence_ids = ["ev-rw-" + item for item in raw_group]
        unknown = [item for item in evidence_ids if item not in by_evidence]
        if unknown:
            raise ValueError(f"{slug}: unknown evidence specs {unknown}")
        groups.append({
            "evidence_group_id": f"eg-rw-{slug}-{index:02d}",
            "required": True,
            "evidence_role": "REQUIRED",
            "any_of_document_ids": sorted({by_evidence[item]["doc"] for item in evidence_ids}),
            "any_of_evidence_ids": evidence_ids,
            "notes": "AND across required groups; OR within this group's stable source anchors.",
        })
    group_ids = [item["evidence_group_id"] for item in groups]
    claims: list[dict[str, Any]] = []
    for index, raw_claim in enumerate(raw["claims"], 1):
        claim_groups = [group_ids[item] for item in raw_claim["groups"]]
        claim = {
            "claim_id": f"rw-gold-v1-{slug}-claim-{index:02d}",
            "canonical_claim": raw_claim["text"],
            "required": True,
            "evaluation_mode": raw_claim["mode"],
            "evidence_group_ids": claim_groups,
            "notes": "Atomic claim; judge against the referenced stable evidence groups.",
        }
        if raw_claim.get("terms"):
            claim["deterministic_match"] = {"all_terms": raw_claim["terms"]}
        claims.append(claim)
    accepts = [{
        "document_id": doc,
        "evidence_ids": ["ev-rw-" + item for item in evidence],
        "evidence_role": "ACCEPTABLE_SUPPORT",
        "notes": notes,
    } for doc, evidence, notes in raw["accepts"]]
    distractors = [{
        "document_id": doc,
        "evidence_ids": [],
        "evidence_role": "UNSUPPORTED",
        "notes": notes,
    } for doc, notes in raw["distractors"]]
    answerable = raw["absent"] is None
    case: dict[str, Any] = {
        "case_id": "rw-gold-v1-" + slug,
        "tier": raw["tier"],
        "case_type": raw["case_type"],
        "information_need_key": slug,
        "question": raw["question"],
        "query_language": raw["language"],
        "expected_answer_language": raw["language"],
        "primary_topic": raw["topic"],
        "secondary_topics": raw["secondary"],
        "difficulty": raw["difficulty"],
        "answerable": answerable,
        "localization_region": raw["region"],
        "evidence_groups": groups,
        "acceptable_supporting_evidence": accepts,
        "plausible_distractor_documents": distractors,
        "claims": claims,
        "citation_contract": {
            "citation_required": answerable,
            "required_evidence_group_ids": group_ids,
            "minimum_distinct_required_documents": minimum_hitting_documents(groups),
            "acceptable_support_policy": "ALLOW_GENUINE_SUPPORT" if answerable else "NO_CORPUS_CITATIONS",
            "forbid_citations": not answerable,
            "notes": (
                "Citations must semantically support each attached claim and cover every required group."
                if answerable else
                "Do not cite near-boundary passages as if they contained the absent answer."
            ),
        },
    }
    if raw["absent"] is not None:
        near_docs, near_evidence, absent_information = raw["absent"]
        case["unanswerable_contract"] = {
            "near_boundary_document_ids": near_docs,
            "near_boundary_evidence_ids": ["ev-rw-" + item for item in near_evidence],
            "absent_information": absent_information,
            "unsupported_factual_answer_forbidden": True,
            "fabricated_citation_forbidden": True,
        }
    return case


def _duplicates(values: Iterable[str]) -> list[str]:
    counts = Counter(values)
    return sorted(item for item, count in counts.items() if count > 1)


def validate_case(
    case: dict[str, Any], manifest: dict[str, Any], specs: list[dict[str, Any]], *,
    expected_type: str | None = None, expected_tier: str | None = None,
) -> list[str]:
    errors: list[str] = []
    case_id = case.get("case_id", "<missing-case-id>")
    document_ids = {item["document_id"] for item in manifest["documents"]}
    evidence = spec_index(specs)
    if expected_type and case.get("case_type") != expected_type:
        errors.append(f"{case_id}: expected case_type {expected_type}")
    if expected_tier and case.get("tier") != expected_tier:
        errors.append(f"{case_id}: expected tier {expected_tier}")
    if case.get("query_language") not in LANGUAGES or case.get("expected_answer_language") not in LANGUAGES:
        errors.append(f"{case_id}: invalid language")
    if case.get("primary_topic") not in TOPICS:
        errors.append(f"{case_id}: invalid primary topic")
    if case.get("difficulty") not in DIFFICULTIES:
        errors.append(f"{case_id}: invalid difficulty")
    question = case.get("question", "")
    if len(question.strip()) < 8 or any(marker in question for marker in MOJIBAKE_MARKERS):
        errors.append(f"{case_id}: unreadable or malformed UTF-8 question")
    groups = case.get("evidence_groups", [])
    group_ids = [item.get("evidence_group_id", "") for item in groups]
    if _duplicates(group_ids):
        errors.append(f"{case_id}: duplicate evidence group IDs")
    for group in groups:
        if group.get("evidence_role") != "REQUIRED" or group.get("required") is not True:
            errors.append(f"{case_id}: invalid required evidence role")
        docs = set(group.get("any_of_document_ids", []))
        evs = group.get("any_of_evidence_ids", [])
        if not docs or not evs:
            errors.append(f"{case_id}: empty evidence group")
        if docs - document_ids:
            errors.append(f"{case_id}: unresolved evidence-group document")
        for evidence_id in evs:
            if evidence_id not in evidence:
                errors.append(f"{case_id}: unresolved evidence anchor {evidence_id}")
            elif evidence[evidence_id]["doc"] not in docs:
                errors.append(f"{case_id}: evidence anchor/document mismatch {evidence_id}")
    claim_ids = [item.get("claim_id", "") for item in case.get("claims", [])]
    if not claim_ids or _duplicates(claim_ids):
        errors.append(f"{case_id}: missing or duplicate claim IDs")
    for claim in case.get("claims", []):
        if set(claim.get("evidence_group_ids", [])) - set(group_ids):
            errors.append(f"{case_id}: claim references an unknown evidence group")
    for key, allowed_role in (("acceptable_supporting_evidence", "ACCEPTABLE_SUPPORT"), ("plausible_distractor_documents", "UNSUPPORTED")):
        for record in case.get(key, []):
            if record.get("evidence_role") != allowed_role:
                errors.append(f"{case_id}: invalid {key} role")
            if record.get("document_id") not in document_ids:
                errors.append(f"{case_id}: unresolved {key} document")
            for evidence_id in record.get("evidence_ids", []):
                if evidence_id not in evidence:
                    errors.append(f"{case_id}: unresolved supporting anchor {evidence_id}")
    citation = case.get("citation_contract", {})
    if case.get("answerable"):
        if not groups or not citation.get("citation_required") or citation.get("forbid_citations"):
            errors.append(f"{case_id}: invalid answerable citation/evidence contract")
        if "unanswerable_contract" in case:
            errors.append(f"{case_id}: answerable case has unanswerable contract")
    else:
        if groups or citation.get("citation_required") or not citation.get("forbid_citations"):
            errors.append(f"{case_id}: unanswerable case has required evidence/citations")
        boundary = case.get("unanswerable_contract")
        if not boundary:
            errors.append(f"{case_id}: missing unanswerable contract")
        else:
            if set(boundary.get("near_boundary_document_ids", [])) - document_ids:
                errors.append(f"{case_id}: unresolved near-boundary document")
            for evidence_id in boundary.get("near_boundary_evidence_ids", []):
                if evidence_id not in evidence:
                    errors.append(f"{case_id}: unresolved near-boundary anchor {evidence_id}")
    return errors


def validate_shard(
    shard: dict[str, Any], manifest: dict[str, Any], specs: list[dict[str, Any]], *,
    expected_type: str, expected_count: int, expected_tier: str,
) -> list[str]:
    errors: list[str] = []
    schema = read_json(GOLD_ROOT / "draft_shard.schema.json")
    errors.extend(f"{expected_type}: schema {item}" for item in json_schema_errors(shard, schema))
    cases = shard.get("cases", [])
    if shard.get("schema_version") != "1.0.0" or shard.get("draft_status") != "UNVERIFIED":
        errors.append(f"{expected_type}: invalid shard metadata")
    if shard.get("case_type") != expected_type or shard.get("expected_case_count") != expected_count:
        errors.append(f"{expected_type}: shard contract mismatch")
    if len(cases) != expected_count:
        errors.append(f"{expected_type}: expected {expected_count} cases, got {len(cases)}")
    case_ids = [item.get("case_id", "") for item in cases]
    claim_ids = [claim.get("claim_id", "") for item in cases for claim in item.get("claims", [])]
    questions = [" ".join(item.get("question", "").casefold().split()) for item in cases]
    if _duplicates(case_ids):
        errors.append(f"{expected_type}: duplicate case IDs {_duplicates(case_ids)}")
    if _duplicates(claim_ids):
        errors.append(f"{expected_type}: duplicate claim IDs {_duplicates(claim_ids)}")
    if _duplicates(questions):
        errors.append(f"{expected_type}: duplicate questions")
    for case in cases:
        errors.extend(validate_case(case, manifest, specs, expected_type=expected_type, expected_tier=expected_tier))
    return errors


def make_shard(case_type: str, cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "schema_ref": "draft_shard.schema.json",
        "draft_status": "UNVERIFIED",
        "case_type": case_type,
        "expected_case_count": CORE_TYPES.get(case_type, STRESS_TYPES.get(case_type)),
        "cases": cases,
    }
