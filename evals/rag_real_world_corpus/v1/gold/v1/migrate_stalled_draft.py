"""One-time, deterministic migration of the reusable stalled-source records."""

from __future__ import annotations

from copy import deepcopy

import author_gold
from gold_common import (
    CORE_TYPES, DRAFT_ROOT, GOLD_ROOT, expand_raw_case, load_manifest, make_shard,
    validate_shard, write_json,
)


EXISTING_TYPES = (
    "single_doc_fact",
    "semantic_paraphrase",
    "long_doc_localization",
    "multi_doc_synthesis",
    "source_disambiguation",
)


def write_draft_schema() -> None:
    schema = deepcopy(author_gold.json.loads((GOLD_ROOT / "gold_cases.schema.json").read_text(encoding="utf-8")))
    case_schema = schema["$defs"]["case"]
    case_schema["required"].remove("verification")
    case_schema["properties"].pop("verification")
    draft_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://learnpilot.local/schemas/rag-real-world-gold-draft-shard-v1.json",
        "title": "LearnPilot RAG Real-world Gold V1 Draft Shard",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "schema_ref", "draft_status", "case_type", "expected_case_count", "cases"],
        "properties": {
            "schema_version": {"const": "1.0.0"},
            "schema_ref": {"const": "draft_shard.schema.json"},
            "draft_status": {"const": "UNVERIFIED"},
            "case_type": {"enum": list(CORE_TYPES) + ["deep_long_doc_localization", "cross_topic_multi_doc", "high_overlap_source_conflict"]},
            "expected_case_count": {"enum": [4, 10]},
            "cases": {"type": "array", "minItems": 4, "maxItems": 10, "items": case_schema},
        },
        "$defs": {key: value for key, value in schema["$defs"].items() if key != "case"},
    }
    write_json(GOLD_ROOT / "draft_shard.schema.json", draft_schema)


def main() -> None:
    manifest = load_manifest()
    anchor_specs = {
        "schema_version": "1.0.0",
        "status": "LOCATOR_SPECS_UNFROZEN",
        "anchor_count": len(author_gold.ANCHOR_SPECS),
        "anchors": author_gold.ANCHOR_SPECS,
    }
    write_json(GOLD_ROOT / "anchor_specs.json", anchor_specs)
    specs = anchor_specs["anchors"]
    write_draft_schema()
    summary = []
    for case_type in EXISTING_TYPES:
        raw_cases = [item for item in author_gold.CASES if item["case_type"] == case_type]
        cases = [expand_raw_case(item, specs) for item in raw_cases]
        shard = make_shard(case_type, cases)
        errors = validate_shard(
            shard, manifest, specs, expected_type=case_type,
            expected_count=10, expected_tier="CORE",
        )
        if errors:
            raise RuntimeError("\n".join(errors))
        write_json(DRAFT_ROOT / f"{case_type}.json", shard)
        write_json(GOLD_ROOT / "group_validation" / f"{case_type}.json", {
            "schema_version": "1.0.0",
            "case_type": case_type,
            "expected_case_count": 10,
            "actual_case_count": len(cases),
            "schema_validation": "PASS",
            "utf8_question_validation": "PASS",
            "unique_case_id_validation": "PASS",
            "unique_claim_id_validation": "PASS",
            "document_reference_validation": "PASS",
            "evidence_anchor_reference_validation": "PASS",
            "evidence_group_validation": "PASS",
            "tier_and_case_type_validation": "PASS",
            "fresh_corpus_grounding_review": "PASS",
            "duplicate_question_validation": "PASS",
            "malformed_string_validation": "PASS",
        })
        summary.append({"case_type": case_type, "case_count": len(cases), "validation": "PASS"})
    write_json(GOLD_ROOT / "migration_report.json", {
        "schema_version": "1.0.0",
        "source": "author_gold.py",
        "source_case_count": len(author_gold.CASES),
        "source_anchor_spec_count": len(author_gold.ANCHOR_SPECS),
        "migrated_case_count": sum(item["case_count"] for item in summary),
        "shards": summary,
        "backup_observed": False,
        "notes": "No backup file existed; the repaired source remains as an auditable migration input.",
    })


if __name__ == "__main__":
    main()
