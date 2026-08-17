from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import random
from typing import Any
from uuid import uuid4


HERE = Path(__file__).resolve().parent
V1 = HERE.parent
ROOT = V1.parents[2]
DESIGN_VERSION = "V1.1"
DESIGN_SHA256 = "442bedce1c43b27b3557b0055708342edd278e98bcac0c12a68c1390fe88f655"
PHASE2_RUN_ID = "20260814T095542Z-1317c6a7"
PHASE3_RUN_ID = "20260814T123142Z-8852712b"
PHASE3_CONTEXT_SHA256 = "f299c0a00dc2dbe8bb21e35c8888d0bfee8f0a1b94c6bbe094407b31c1bf1cf7"
PHASE3_RAW_SHA256 = "84ced9e50fff8c2e7f6290045ea9d369179f9413bd6efe3e04d97e62f59046ad"
PHASE2_DIR = V1 / f"results/hybrid_rerank_phase2_v1_1/{PHASE2_RUN_ID}"
PHASE3_DIR = V1 / f"results/hybrid_rerank_phase3_v1_1/{PHASE3_RUN_ID}"
RESULTS_ROOT = V1 / "results/hybrid_rerank_phase4_v1_1"
FROZEN_A_PATH = V1 / "results/dense_only_baseline_v1/20260814T052007Z-593cd2ac/raw_results.json"
FROZEN_A_SHA256 = "bf718aed08e226149c9310cbf20bf25c403708217e2908789120178ac5574e28"
BLIND_SEED = "learnpilot-rag-phase4-v1.1-blind-20260814"
ARMS = ("A", "B", "C", "D")
FROZEN_HASHES = {
    "design": (V1 / "ablation_design_v1_1/ablation_design_manifest.json", DESIGN_SHA256),
    "gold": (V1 / "gold/v1/gold_cases.json", "33a0b69901fa47e3fe45be0277228cd4a5519fe780fe5b9d2c52b1bfe614927a"),
    "gold_freeze": (V1 / "gold/v1/gold_dataset_v1_freeze_manifest.json", "d979079be4eb901a825ab29414dd7b5124d030182e09b55eea1e93749c12a5c2"),
    "corpus": (V1 / "corpus_manifest.json", "6f67d510cd35197f107400d33033972c0c3c84478174e4991e491f6c8e4ab563"),
    "frozen_a": (FROZEN_A_PATH, FROZEN_A_SHA256),
    "failure_analysis": (V1 / "failure_analysis_v1/failure_analysis_manifest.json", "e869fd73e2570413595c1af194b6ec6876e8b822fbd4eac279541a03cac27fb8"),
    "phase3_raw": (PHASE3_DIR / "canonical_raw_results.json", PHASE3_RAW_SHA256),
    "phase3_context": (PHASE3_DIR / "context_freeze.json", PHASE3_CONTEXT_SHA256),
}


class IntegrityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def metadata(run_id: str, **payload: Any) -> dict[str, Any]:
    return {
        "design_version": DESIGN_VERSION,
        "ablation_design_sha256": DESIGN_SHA256,
        "phase2_run_id": PHASE2_RUN_ID,
        "phase3_run_id": PHASE3_RUN_ID,
        "phase4_run_id": run_id,
        "recorded_at": utc_now(),
        **payload,
    }


def verify_manifest(latest_path: Path, expected_run_id: str, run_dir: Path) -> dict[str, Any]:
    latest = read_json(latest_path)
    bound_run = latest.get("phase3_run_id") or latest.get("run_id")
    if latest.get("status") != "PASS" or bound_run != expected_run_id:
        raise IntegrityError(f"authoritative latest-run mismatch: {latest_path}")
    manifest_path = run_dir / "artifact_manifest.json"
    if file_sha256(manifest_path) != latest["artifact_manifest_sha256"]:
        raise IntegrityError(f"artifact manifest hash drift: {manifest_path}")
    manifest = read_json(manifest_path)
    items = manifest["result_files"] + manifest["implementation_and_report_files"]
    for item in items:
        path = ROOT / item["path"]
        if file_sha256(path) != item["sha256"] or path.stat().st_size != item["size_bytes"]:
            raise IntegrityError(f"manifest entry drift: {item['path']}")
    return {"manifest_sha256": file_sha256(manifest_path), "verified_entries": len(items)}


def verify_production_bindings() -> dict[str, Any]:
    failure = read_json(V1 / "failure_analysis_v1/failure_analysis_manifest.json")
    binding = failure["frozen_bindings"]["production_code"]
    expected = binding["baseline_sha256"]
    if len(expected) != 15 or not binding["all_match"]:
        raise IntegrityError("production binding is not the frozen 15-file set")
    for relative, digest in expected.items():
        if file_sha256(ROOT / relative) != digest:
            raise IntegrityError(f"production file drift: {relative}")
    return {"file_count": len(expected), "all_match": True, "hashes": expected}


def a_output(case: dict[str, Any]) -> dict[str, Any]:
    value = case["frozen_A"]
    return {
        "answer": value["answer"],
        "answerable": value["answerable"],
        "refusal_reason": None,
        "citation_ids": [citation["source_label"] for citation in value["citations"]],
        "citations": value["citations"],
    }


def experimental_output(case: dict[str, Any], arm: str) -> dict[str, Any]:
    value = case[arm]
    return {
        "answer": value["answer"],
        "answerable": value["answerable"],
        "refusal_reason": value["refusal_reason"],
        "citation_ids": value["citation_ids"],
        "citations": value["citations"],
    }


def output_for(case: dict[str, Any], arm: str) -> dict[str, Any]:
    return a_output(case) if arm == "A" else experimental_output(case, arm)


def verify_review_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    raw = read_json(PHASE3_DIR / "canonical_raw_results.json")
    context = read_json(PHASE3_DIR / "context_freeze.json")
    frozen_a = read_json(FROZEN_A_PATH)
    raw_by_key = {(row["arm"], row["case_id"]): row for row in raw["records"]}
    context_by_key = {(row["arm"], row["case_id"]): row for row in context["records"]}
    a_by_id = {row["case_id"]: row for row in frozen_a["cases"]}
    cases = bundle["cases"]
    if len(cases) != 72 or len({row["case_id"] for row in cases}) != 72:
        raise IntegrityError("Phase 4 bundle must contain 72 unique cases")
    claim_ids = []
    output_count = 0
    for case in cases:
        case_id = case["case_id"]
        claim_ids.extend(claim["claim_id"] for claim in case["Gold"]["required_claims"])
        historical = a_by_id[case_id]
        a = case["frozen_A"]
        if a["answer"] != historical["normalized_answer"] or a["citations"] != historical["citations"]:
            raise IntegrityError(f"frozen A answer/citation drift: {case_id}")
        output_count += 1
        for arm in ("B", "C", "D"):
            value = case[arm]
            raw_row = raw_by_key[(arm, case_id)]
            frozen_context = context_by_key[(arm, case_id)]
            checks = (
                value["answer"] == raw_row["answer_markdown"],
                value["answerable"] == raw_row["answerable"],
                value["refusal_reason"] == raw_row["refusal_reason"],
                value["citation_ids"] == raw_row["citation_ids"],
                value["context_digest"] == raw_row["context_digest"] == frozen_context["context_digest"],
                value["result_identity_sha256"] == raw_row["result_identity_sha256"],
                value["selected_evidence"] == frozen_context["selected_sources"],
            )
            if not all(checks):
                raise IntegrityError(f"Phase 3 answer/context/citation drift: {arm}/{case_id}")
            output_count += 1
    if len(claim_ids) != 132 or len(set(claim_ids)) != 132:
        raise IntegrityError(f"expected 132 unique frozen claims, got {len(claim_ids)}/{len(set(claim_ids))}")
    if len(raw_by_key) != 216 or len(context_by_key) != 216 or output_count != 288:
        raise IntegrityError("frozen output/context cardinality mismatch")
    return {
        "case_count": len(cases),
        "arm_outputs_per_case": 4,
        "frozen_output_count": output_count,
        "frozen_claim_count": len(claim_ids),
        "phase3_record_count": len(raw_by_key),
        "phase3_context_count": len(context_by_key),
        "answer_text_unchanged": True,
        "citation_lists_unchanged": True,
        "context_digests_unchanged": True,
        "omitted_cases": [],
        "duplicate_cases": [],
    }


def permutation(case_id: str) -> list[str]:
    digest = sha256(f"{BLIND_SEED}\0{case_id}".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest, "big"))
    arms = list(ARMS)
    rng.shuffle(arms)
    return arms


def make_blinded_artifacts(run_id: str, bundle: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    blinded_cases = []
    mappings = []
    for case in bundle["cases"]:
        arms = permutation(case["case_id"])
        responses = []
        case_mapping = {}
        for index, arm in enumerate(arms, start=1):
            label = f"response_X{index}"
            case_mapping[label] = arm
            response = output_for(case, arm)
            responses.append(
                {
                    "response_label": label,
                    "answer": response["answer"],
                    "answerable": response["answerable"],
                    "refusal_reason": response["refusal_reason"],
                    "citation_ids": response["citation_ids"],
                    "mechanical_citation_validity": True,
                    "cited_evidence": response["citations"],
                }
            )
        blinded_cases.append(
            {
                "case_id": case["case_id"],
                "question": case["question"],
                "Gold": case["Gold"],
                "responses": responses,
            }
        )
        mappings.append({"case_id": case["case_id"], "response_to_arm": case_mapping})
    blinded = metadata(
        run_id,
        review_stage="PASS_1_BLINDED_INPUT",
        blind_seed_sha256=sha256(BLIND_SEED.encode("utf-8")).hexdigest(),
        reviewer_visible_fields=["case_id", "question", "Gold", "response_label", "answer", "answerable", "refusal_reason", "citation_ids", "mechanical_citation_validity", "cited_evidence"],
        prohibited_fields_absent=["arm", "architecture", "retrieval_latency", "historical_verdict", "phase2_diagnostic"],
        case_count=len(blinded_cases),
        response_count=sum(len(row["responses"]) for row in blinded_cases),
        frozen_claim_count=sum(len(row["Gold"]["required_claims"]) for row in blinded_cases),
        cases=blinded_cases,
    )
    mapping = metadata(
        run_id,
        review_stage="SEALED_MAPPING_DO_NOT_READ_BEFORE_PASS1_FREEZE",
        seed=BLIND_SEED,
        seed_sha256=sha256(BLIND_SEED.encode("utf-8")).hexdigest(),
        algorithm="per-case SHA-256-derived Python random.Random shuffle over A,B,C,D",
        mapping_count=len(mappings),
        mappings=mappings,
    )
    return blinded, mapping


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id")
    args = parser.parse_args()
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    run_dir = RESULTS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    observed = {}
    for name, (path, expected) in FROZEN_HASHES.items():
        actual = file_sha256(path)
        if actual != expected:
            raise IntegrityError(f"frozen hash mismatch {name}: {actual} != {expected}")
        observed[name] = {"path": path.relative_to(ROOT).as_posix(), "sha256": actual, "match": True}
    phase2 = verify_manifest(V1 / "results/hybrid_rerank_phase2_v1_1/latest_run.json", PHASE2_RUN_ID, PHASE2_DIR)
    phase3 = verify_manifest(V1 / "results/hybrid_rerank_phase3_v1_1/latest_run.json", PHASE3_RUN_ID, PHASE3_DIR)
    phase3_validation = read_json(PHASE3_DIR / "machine_validation.json")
    if phase3_validation["status"] != "PASS" or phase3_validation["execution_counts"] != {"A": 0, "B": 72, "C": 72, "D": 72}:
        raise IntegrityError("Phase 3 machine validation is not authoritative PASS")
    production = verify_production_bindings()
    bundle_path = PHASE3_DIR / "phase4_review_bundle.json"
    detached_bundle_hash = (PHASE3_DIR / "phase4_review_bundle.sha256").read_text(encoding="utf-8").split()[0]
    if file_sha256(bundle_path) != detached_bundle_hash:
        raise IntegrityError("Phase 4 review bundle detached hash mismatch")
    bundle = read_json(bundle_path)
    bundle_validation = verify_review_bundle(bundle)
    preflight = metadata(
        run_id,
        status="PASS",
        frozen_hashes=observed,
        phase2=phase2,
        phase3=phase3,
        phase3_review_bundle_sha256=file_sha256(bundle_path),
        phase3_validation_sha256=file_sha256(PHASE3_DIR / "machine_validation.json"),
        production_bindings=production,
        bundle_validation=bundle_validation,
        new_deepseek_calls=0,
        new_generation_calls=0,
        new_retrieval_runs=0,
        new_reranker_runs=0,
        arm_a_reruns=0,
        production_modifications=0,
    )
    blinded, mapping = make_blinded_artifacts(run_id, bundle)
    blinded_path = run_dir / "blinded_review_input.json"
    mapping_path = run_dir / "sealed_blind_mapping.json"
    write_json(run_dir / "integrity_preflight.json", preflight)
    write_json(blinded_path, blinded)
    write_json(mapping_path, mapping)
    (run_dir / "blinded_review_input.sha256").write_text(file_sha256(blinded_path) + "  blinded_review_input.json\n", encoding="utf-8")
    write_json(
        run_dir / "run_manifest.json",
        metadata(
            run_id,
            status="BLINDED_INPUT_FROZEN",
            blinded_review_input_sha256=file_sha256(blinded_path),
            sealed_mapping_sha256=file_sha256(mapping_path),
            mapping_must_remain_sealed_until="blinded_adjudication.json detached hash exists",
            blind_seed_identity=canonical_sha256({"seed": BLIND_SEED}),
            new_external_or_model_calls=0,
        ),
    )
    print(json.dumps({"status": "BLINDED_INPUT_FROZEN", "run_id": run_id, "run_dir": str(run_dir), "blinded_input_sha256": file_sha256(blinded_path), "case_count": 72, "response_count": 288, "claim_count": 132}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
