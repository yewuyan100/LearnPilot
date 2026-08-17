from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"
V1 = REPO_ROOT / "evals/rag_real_world_corpus/v1"
sys.path.insert(0, str(V1))
sys.path.insert(0, str(BACKEND_ROOT))

from canonical_model_path import resolve_canonical_reranker_model_path  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.schemas.material_chunk import (  # noqa: E402
    MaterialSearchResponse,
    MaterialSearchResult,
)
from app.services.rag.prompts import build_context  # noqa: E402
from app.services.rag.reranker import (  # noqa: E402
    RerankBatch,
    RerankCandidate,
    RerankerProvider,
    build_reranker_provider,
)
from app.services.rag.retrieval import retrieve_sources  # noqa: E402
import app.services.rag.retrieval as retrieval_module  # noqa: E402

MODEL_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
MODEL_PATH = resolve_canonical_reranker_model_path()
TRACE_PATH = (
    REPO_ROOT
    / "evals/rag_real_world_corpus/v1/results/hybrid_rerank_phase2_v1_1"
    / "20260814T095542Z-1317c6a7/arm_C/candidate_traces.jsonl"
)
REFERENCE_PATH = (
    REPO_ROOT
    / "evals/rag_real_world_corpus/v1/results/c_v1_3b_cuda_fp32_full"
    / "20260816T050910Z-fbb5cec1/equivalence_results.json"
)
GOLD_PATH = REPO_ROOT / "evals/rag_real_world_corpus/v1/gold/v1/gold_cases.json"
CASE_IDS = (
    "rw-gold-v1-single-langgraph-js",
    "rw-gold-v1-disambig-ragas-otel",
    "rw-gold-v1-disambig-bge-long",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class RecordingGateway:
    def __init__(self, provider: RerankerProvider):
        self.provider = provider
        self.inputs: list[tuple[RerankCandidate, ...]] = []
        self.outputs: list[RerankBatch] = []

    def rerank(
        self, query: str, candidates: list[RerankCandidate]
    ) -> RerankBatch:
        self.inputs.append(tuple(candidates))
        result = self.provider.rerank(query, candidates)
        self.outputs.append(result)
        return result

    def status(self):  # noqa: ANN201
        return self.provider.status()


def material_result(candidate: dict[str, Any]) -> MaterialSearchResult:
    return MaterialSearchResult(
        rank=int(candidate["dense_rank"]),
        score=float(candidate["dense_score"]),
        chunk_id=int(candidate["chunk_id"]),
        material_id=int(candidate["material_id"]),
        original_filename=candidate["filename"],
        chunk_index=int(candidate["chunk_index"]),
        content=candidate["raw_text"],
        page_number=candidate["page_number"],
        section_title=candidate["section_title"],
    )


def evidence_coverage(
    groups: list[dict[str, Any]], selected: list[dict[str, Any]]
) -> dict[str, Any]:
    rows = []
    for group in groups:
        if not group["required"]:
            continue
        rows.append(
            {
                "evidence_group_id": group["evidence_group_id"],
                "document_match": any(
                    candidate["document_id"] in group["any_of_document_ids"]
                    for candidate in selected
                ),
                "anchor_match": any(
                    set(candidate["evidence_ids"]) & set(group["any_of_evidence_ids"])
                    for candidate in selected
                ),
            }
        )
    return {
        "groups": rows,
        "document_groups_covered": sum(row["document_match"] for row in rows),
        "anchor_groups_covered": sum(row["anchor_match"] for row in rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    args.run_dir.mkdir(parents=True, exist_ok=True)

    traces = {
        row["case_id"]: row
        for row in (
            json.loads(line)
            for line in TRACE_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if row["case_id"] in CASE_IDS
    }
    references = {
        row["case_id"]: row for row in read_json(REFERENCE_PATH)["rows"]
    }
    gold = {
        row["case_id"]: row for row in read_json(GOLD_PATH)["cases"]
    }
    if set(traces) != set(CASE_IDS):
        raise SystemExit("missing frozen production smoke trace")

    settings = Settings(
        _env_file=None,
        rag_reranker_enabled=True,
        rag_reranker_model_path=MODEL_PATH,
        rag_reranker_device="cuda",
        rag_top_k_default=6,
        rag_max_sources=6,
        search_top_k_max=20,
        rag_min_score=0.35,
        rag_max_context_chars=12000,
        rag_max_chunk_chars=2200,
    )
    provider = build_reranker_provider(settings)
    if provider is None:
        raise SystemExit("production reranker provider was not enabled")
    recording = RecordingGateway(provider)
    rows = []

    original_search = retrieval_module.MaterialIndexService.search
    try:
        for case_id in CASE_IDS:
            trace = traces[case_id]
            reference = references[case_id]
            candidates = sorted(
                trace["candidates"],
                key=lambda row: (int(row["dense_rank"]), row["identity"]),
            )
            if len(candidates) != 18 or not all(
                candidate["candidate_admitted"] for candidate in candidates
            ):
                raise SystemExit(f"unexpected candidate contract for {case_id}")
            production_ids = {
                f'{candidate["material_id"]}:{candidate["chunk_id"]}': candidate["identity"]
                for candidate in candidates
            }
            rows_by_identity = {candidate["identity"]: candidate for candidate in candidates}
            search_rows = [material_result(candidate) for candidate in candidates]

            def frozen_search(self, **kwargs):  # noqa: ANN001
                if kwargs["top_k"] != 18:
                    raise AssertionError("production dense candidate depth changed")
                return MaterialSearchResponse(
                    query=kwargs["query"],
                    model_name="frozen-bge-m3-dense",
                    index_version="frozen-phase2-v1.1",
                    results=search_rows,
                    duration_ms=0,
                    retrieved_count=18,
                    filtered_count=0,
                )

            retrieval_module.MaterialIndexService.search = frozen_search
            input_offset = len(recording.inputs)
            output_offset = len(recording.outputs)
            outcome = retrieve_sources(
                db=object(),
                settings=settings,
                embedder=object(),
                query=trace["effective_query"],
                top_k=6,
                material_ids=None,
                reranker_provider=recording,
            )
            reranker_input = recording.inputs[input_offset]
            reranker_output = recording.outputs[output_offset]
            input_order = [production_ids[item.identity] for item in reranker_input]
            production_order = [
                production_ids[item.identity] for item in reranker_output.scores
            ]
            production_top6 = [
                next(
                    candidate["identity"]
                    for candidate in candidates
                    if int(candidate["material_id"]) == source.material_id
                    and int(candidate["chunk_id"]) == source.chunk_id
                )
                for source in outcome.sources
            ]
            context_digest = digest_text(build_context(outcome.sources))
            required_evidence = evidence_coverage(
                gold[case_id]["evidence_groups"],
                [rows_by_identity[identity] for identity in production_top6],
            )
            row = {
                "case_id": case_id,
                "candidate_count": outcome.candidate_count,
                "pair_count": reranker_output.pair_count,
                "batch_count": reranker_output.batch_count,
                "retrieval_mode": outcome.retrieval_mode,
                "reranker_status": outcome.reranker_status,
                "reranker_device": outcome.reranker_device,
                "reranker_dtype": outcome.reranker_dtype,
                "candidate_identities_equal": input_order
                == [candidate["identity"] for candidate in candidates],
                "ordering_equal": production_order == reference["cuda_order"],
                "top6_equal": production_top6 == reference["cuda_top6"],
                "context_equal": context_digest == reference["cuda_context_digest"],
                "required_evidence_equal": required_evidence
                == reference["cuda_required_evidence"],
                "production_order": production_order,
                "reference_order": reference["cuda_order"],
                "production_top6": production_top6,
                "reference_top6": reference["cuda_top6"],
                "production_context_digest": context_digest,
                "reference_context_digest": reference["cuda_context_digest"],
                "production_required_evidence": required_evidence,
                "reference_required_evidence": reference["cuda_required_evidence"],
            }
            rows.append(row)
            if not all(
                row[key]
                for key in (
                    "candidate_identities_equal",
                    "ordering_equal",
                    "top6_equal",
                    "context_equal",
                    "required_evidence_equal",
                )
            ):
                write_json(
                    args.run_dir / "production_context_equivalence.json",
                    {"run_id": args.run_id, "status": "FAIL", "rows": rows},
                )
                raise SystemExit(f"production context mismatch: {case_id}")
    finally:
        retrieval_module.MaterialIndexService.search = original_search

    import torch

    status = provider.status()
    lifecycle = {
        "run_id": args.run_id,
        "status": "PASS",
        "model_load_count_per_process": status.load_count,
        "model_load_attempt_count_per_process": status.load_attempt_count,
        "inference_count": status.inference_count,
        "pair_count": sum(row["pair_count"] for row in rows),
        "batch_count": sum(row["batch_count"] for row in rows),
        "device": status.device,
        "dtype": status.dtype,
        "model_eval": not provider._instance.model.training,
        "inference_mode_used": True,
        "tf32_matmul": torch.backends.cuda.matmul.allow_tf32,
        "tf32_cudnn": torch.backends.cudnn.allow_tf32,
        "autocast": torch.is_autocast_enabled("cuda"),
        "local_files_only": True,
        "trust_remote_code": False,
        "hf_hub_offline": __import__("os").environ.get("HF_HUB_OFFLINE"),
        "transformers_offline": __import__("os").environ.get("TRANSFORMERS_OFFLINE"),
    }
    equivalence = {
        "run_id": args.run_id,
        "status": "PASS",
        "authoritative_reference_run": "20260816T050910Z-fbb5cec1",
        "cases": rows,
        "summary": {
            "candidate_identities": "3/3",
            "reranker_ordering": "3/3",
            "governed_top6": "3/3",
            "final_context_digest": "3/3",
            "required_evidence": "3/3",
            "production_c_context_equivalence": "3/3",
        },
        "execution": {
            "deepseek_calls": 0,
            "generation_calls": 0,
            "full_72_case_run": False,
        },
    }
    write_json(args.run_dir / "reranker_lifecycle_validation.json", lifecycle)
    write_json(args.run_dir / "production_context_equivalence.json", equivalence)
    print(
        json.dumps(
            {
                "status": "PASS",
                "load_count": status.load_count,
                "device": status.device,
                "dtype": status.dtype,
                "equivalence": equivalence["summary"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
