"""Build exactly one file-backed draft shard per invocation."""

from __future__ import annotations

import argparse

from gold_common import (
    CORE_TYPES, DRAFT_ROOT, GOLD_ROOT, STRESS_TYPES, expand_raw_case, load_anchor_specs,
    load_manifest, make_shard, read_json, validate_shard, write_json,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_type", choices=list(CORE_TYPES) + list(STRESS_TYPES))
    args = parser.parse_args()
    case_type = args.case_type
    spec_path = GOLD_ROOT / "authoring_specs" / f"{case_type}.json"
    raw = read_json(spec_path)
    if raw.get("case_type") != case_type:
        raise ValueError("authoring spec case_type mismatch")
    specs = load_anchor_specs()
    cases = [expand_raw_case(item, specs) for item in raw["cases"]]
    shard = make_shard(case_type, cases)
    expected_count = CORE_TYPES.get(case_type, STRESS_TYPES.get(case_type))
    tier = "CORE" if case_type in CORE_TYPES else "STRESS"
    errors = validate_shard(
        shard, load_manifest(), specs, expected_type=case_type,
        expected_count=expected_count, expected_tier=tier,
    )
    if errors:
        raise RuntimeError("\n".join(errors))
    write_json(DRAFT_ROOT / f"{case_type}.json", shard)
    write_json(GOLD_ROOT / "group_validation" / f"{case_type}.json", {
        "schema_version": "1.0.0",
        "case_type": case_type,
        "expected_case_count": expected_count,
        "actual_case_count": len(cases),
        "schema_validation": "PASS",
        "document_reference_validation": "PASS",
        "evidence_anchor_reference_validation": "PASS",
        "distribution_validation": "PASS",
        "cumulative_authored_count": raw["cumulative_authored_count"],
    })


if __name__ == "__main__":
    main()
