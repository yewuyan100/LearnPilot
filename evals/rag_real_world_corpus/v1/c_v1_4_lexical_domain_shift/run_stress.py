from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import fields
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter
from typing import Any


HERE = Path(__file__).resolve().parent
V1 = HERE.parent
ROOT = V1.parents[2]
sys.path.insert(0, str(V1))

from canonical_model_path import resolve_canonical_reranker_model_path  # noqa: E402

RESULTS_ROOT = V1 / "results/c_v1_4_lexical_domain_shift"
REPORT_PATH = ROOT / "RAG_C_V1_4_LEXICAL_DOMAIN_SHIFT_STRESS.md"
DESIGN_PATH = V1 / "ablation_design_v1_1/ablation_design_manifest.json"
DESIGN_SHA_PATH = V1 / "ablation_design_v1_1/ablation_design_manifest.sha256"
PHASE2_DIR = V1 / "hybrid_rerank_phase2_v1_1"
PHASE2_RUN = "20260814T095542Z-1317c6a7"
DENSE_REFERENCE_RUN = "20260814T052007Z-593cd2ac"
DENSE_REFERENCE_MANIFEST = (
    V1 / f"results/dense_only_baseline_v1/{DENSE_REFERENCE_RUN}/run_manifest.json"
)
RERANKER_SNAPSHOT = resolve_canonical_reranker_model_path()
DENSE_CACHE_ROOT = Path("D:/AIModels/HuggingFace")
PRODUCTION_REFERENCE = (
    V1
    / "results/c_v1_3b_cuda_fp32_full/20260816T050910Z-fbb5cec1/production_hashes_after.json"
)


CATEGORY_API = "API_FUNCTION_CLASS_IDENTIFIER"
CATEGORY_CONFIG = "CONFIG_ENV_CLI_FLAG"
CATEGORY_ERROR = "ERROR_STATUS_DIAGNOSTIC"
CATEGORY_MODEL = "MODEL_LIBRARY_PROTOCOL_VERSION"
CATEGORY_TERM = "ACRONYM_SPECIALIZED_TERM"


CASES: list[dict[str, Any]] = [
    {
        "case_id": "lex-v1-request-validation-error-handler",
        "category": CATEGORY_API,
        "query_type": "IDENTIFIER_PLUS_NATURAL_LANGUAGE",
        "query": "FastAPI 的 RequestValidationError 要怎样注册全局 override handler，它会接收哪些对象？",
        "expected_document_id": "rw-backend-fastapi-errors",
        "required_gold_chunk_ids": [
            "rw-backend-fastapi-errors:9:ac8afbcbc3799788d915eb45b1aceadefcb2ee7faebba776f3ec67e565538595"
        ],
        "acceptable_gold_chunk_ids": [],
        "unsupported_decoy_chunk_ids": [
            "rw-backend-fastapi-errors:11:334d830baf12712c2075ec985dab86df8e16ec9aaaf2a5e63540edfc52d3ea5f",
            "rw-backend-fastapi-errors:13:e3995e47de351c686b8c76e587f5658ce5ae69ec317b76aff4f7ad95deb33f56",
        ],
        "gold_rationale": "The required chunk states the decorator and that the handler receives Request plus the exception; nearby chunks discuss other RequestValidationError behavior but not both requested facts.",
        "has_natural_decoy": True,
        "lexical_signal": "EXACT_IDENTIFIER",
    },
    {
        "case_id": "lex-v1-id-based-context-precision",
        "category": CATEGORY_API,
        "query_type": "EXACT_LEXICAL_LOOKUP",
        "query": "IDBasedContextPrecision 用哪些 ID 字段计算 precision，适合什么文档标识场景？",
        "expected_document_id": "rw-eval-context-precision",
        "required_gold_chunk_ids": [
            "rw-eval-context-precision:17:8ffedcffa824b319169f856bcd012b6385dfbbd510f9a8e3563a3747431e4315"
        ],
        "acceptable_gold_chunk_ids": [],
        "unsupported_decoy_chunk_ids": [
            "rw-eval-context-precision:18:21139b5d0c50409f446c0cbfab64fc541f6985ada8341310061c3737745b3814"
        ],
        "gold_rationale": "The required chunk defines retrieved_context_ids/reference_context_ids and the unique-ID use case; the example-only neighbor does not fully explain applicability.",
        "has_natural_decoy": True,
        "lexical_signal": "EXACT_IDENTIFIER",
    },
    {
        "case_id": "lex-v1-postgres-saver-thread-id-limit",
        "category": CATEGORY_CONFIG,
        "query_type": "IDENTIFIER_PLUS_NATURAL_LANGUAGE",
        "query": "PostgresSaver 的 configurable.thread_id 过长时报数据库错误，长度应控制在多少并如何生成？",
        "expected_document_id": "rw-agent-persistence",
        "required_gold_chunk_ids": [
            "rw-agent-persistence:5:6c6d35e4001f7ddeed8b1fc68cee6d810b0167b119f0acd20d77248e9a70397b"
        ],
        "acceptable_gold_chunk_ids": [],
        "unsupported_decoy_chunk_ids": [
            "rw-agent-interrupts:5:8813aa8cc3d9db91414aacca3cdc88d1ae7af016b8e3f0f56215a3049786dbc9",
            "rw-agent-persistence:4:377ce364c38b273c9f7e15b69e4a978eb2dc0af04324266c826c1d444054eb41",
        ],
        "gold_rationale": "The required troubleshooting chunk gives the under-255-character constraint and UUID/hash mitigation; many other chunks use thread_id without this diagnostic.",
        "has_natural_decoy": True,
        "lexical_signal": "CONFIG_KEY",
    },
    {
        "case_id": "lex-v1-pyserini-remove-query-flag",
        "category": CATEGORY_CONFIG,
        "query_type": "EXACT_LEXICAL_LOOKUP",
        "query": "--remove-query 在 pyserini.search.faiss 或 pyserini.search.lucene 中用于复现哪种 MIRACL 结果差异？",
        "expected_document_id": "rw-rag-bge-m3",
        "required_gold_chunk_ids": [
            "rw-rag-bge-m3:40:0534d76a077d60da2d05ea762a86b4fb2b943792f19643be5c86e1d779cc0255"
        ],
        "acceptable_gold_chunk_ids": [],
        "unsupported_decoy_chunk_ids": [
            "rw-rag-bge-m3:41:0fab9e95aae073ec6739cf3fda144de0867a66d02286a42133d096359c331454"
        ],
        "gold_rationale": "The full news chunk explains that removing same-ID passages caused the previous lower result and names the exact flag/tools; truncated overlap chunks lack the causal explanation.",
        "has_natural_decoy": True,
        "lexical_signal": "CONFIG_KEY",
    },
    {
        "case_id": "lex-v1-validation-body-diagnostic",
        "category": CATEGORY_ERROR,
        "query_type": "IDENTIFIER_PLUS_NATURAL_LANGUAGE",
        "query": "出现 \"value is not a valid integer\" 时，RequestValidationError.body 能怎样帮助调试并回显无效输入？",
        "expected_document_id": "rw-backend-fastapi-errors",
        "required_gold_chunk_ids": [
            "rw-backend-fastapi-errors:13:e3995e47de351c686b8c76e587f5658ce5ae69ec317b76aff4f7ad95deb33f56"
        ],
        "acceptable_gold_chunk_ids": [],
        "unsupported_decoy_chunk_ids": [
            "rw-backend-fastapi-errors:9:ac8afbcbc3799788d915eb45b1aceadefcb2ee7faebba776f3ec67e565538595"
        ],
        "gold_rationale": "The required chunk connects the exact validation message with the received body and its logging/debug/response use; the handler chunk contains the message but not the body answer.",
        "has_natural_decoy": True,
        "lexical_signal": "ERROR_CODE",
    },
    {
        "case_id": "lex-v1-unicorn-http-418",
        "category": CATEGORY_ERROR,
        "query_type": "EXACT_LEXICAL_LOOKUP",
        "query": "FastAPI 的 UnicornException 示例为什么返回 HTTP 418，示例 JSON message 是什么？",
        "expected_document_id": "rw-backend-fastapi-errors",
        "required_gold_chunk_ids": [
            "rw-backend-fastapi-errors:6:93a7a6dc030d60bed2fb73ad6b507feb27e69736694f0bb396cfaae86ac47ca7"
        ],
        "acceptable_gold_chunk_ids": [],
        "unsupported_decoy_chunk_ids": [],
        "gold_rationale": "The required custom-handler chunk uniquely binds UnicornException, HTTP 418, and the Oops/rainbow JSON message; the document also contains several competing HTTP status examples.",
        "has_natural_decoy": True,
        "lexical_signal": "ERROR_CODE",
    },
    {
        "case_id": "lex-v1-bge-m3-retromae-spec",
        "category": CATEGORY_MODEL,
        "query_type": "IDENTIFIER_PLUS_NATURAL_LANGUAGE",
        "query": "BAAI/bge-m3-retromae 的 sequence length 是多少，它对 xlm-roberta 做了什么预训练扩展？",
        "expected_document_id": "rw-rag-bge-m3",
        "required_gold_chunk_ids": [
            "rw-rag-bge-m3:78:01c071bca449a541654c4e50dcfc56a0cfa4b0960195e2b420d0bcccbfc6ffb3"
        ],
        "acceptable_gold_chunk_ids": [],
        "unsupported_decoy_chunk_ids": [
            "rw-rag-bge-m3:79:ca544570b2e94dd155fa4a7cd6109c92e215b1164097133a1f194a7432c3f9de"
        ],
        "gold_rationale": "The model table provides the exact model row, 8192 length, XLM-R max-length extension, and RetroMAE pretraining; adjacent rows describe similarly named BGE variants.",
        "has_natural_decoy": True,
        "lexical_signal": "VERSION",
    },
    {
        "case_id": "lex-v1-gpu-index-flat-l2",
        "category": CATEGORY_MODEL,
        "query_type": "IDENTIFIER_PLUS_NATURAL_LANGUAGE",
        "query": "Faiss 中把 IndexFlatL2 换成 GpuIndexFlatL2 时，CPU/GPU memory input 与 copy 行为是什么？",
        "expected_document_id": "rw-rag-faiss-overview",
        "required_gold_chunk_ids": [
            "rw-rag-faiss-overview:4:74026825851538910e1e3b19be6f5ca98b2620c0ab43d9cd66b4e9c6d3c66538"
        ],
        "acceptable_gold_chunk_ids": [],
        "unsupported_decoy_chunk_ids": [
            "rw-rag-faiss-overview:3:abc1acd7118fd514f140730d4c3d927c894d41d9d78c2a0785bf92fbcfb43f7d"
        ],
        "gold_rationale": "The required chunk explicitly names the CPU/GPU index pair, accepted memory locations, automatic copies, and resident-data performance; nearby Faiss text discusses different index trade-offs.",
        "has_natural_decoy": True,
        "lexical_signal": "EXACT_IDENTIFIER",
    },
    {
        "case_id": "lex-v1-mldr-training-purpose",
        "category": CATEGORY_TERM,
        "query_type": "IDENTIFIER_PLUS_NATURAL_LANGUAGE",
        "query": "MLDR 是覆盖多少种语言的什么数据集，它的 training set 被用于增强 BGE-M3 的哪种能力？",
        "expected_document_id": "rw-rag-bge-m3",
        "required_gold_chunk_ids": [
            "rw-rag-bge-m3:129:fac2c5290c3bcdfbe45e35b6f6de981b8200e812820ae4f2138ccf43f4b94205"
        ],
        "acceptable_gold_chunk_ids": [],
        "unsupported_decoy_chunk_ids": [
            "rw-rag-bge-m3:76:59c8a132708b6b6b55f01f90fba3dc324b1df954e1d5b54c26f01645cb7c3d42",
            "rw-rag-bge-m3:79:ca544570b2e94dd155fa4a7cd6109c92e215b1164097133a1f194a7432c3f9de",
            "rw-rag-bge-m3:94:79caed0f2e95cd669d7e6fb87ef9e234fbdad4e098e2a3f745934785e0235859",
            "rw-rag-bge-m3:130:bf18907e33548e3f588b10ebcf85abbd72a0a087f553e85790cb3c17a06845dd",
        ],
        "gold_rationale": "The required results chunk jointly states 13 languages, long-document retrieval dataset structure, and use of its training set to enhance long-document retrieval; other MLDR chunks provide only partial facts.",
        "has_natural_decoy": True,
        "lexical_signal": "ACRONYM",
    },
    {
        "case_id": "lex-v1-hnsw-nsg-versus-compression",
        "category": CATEGORY_TERM,
        "query_type": "EXACT_LEXICAL_LOOKUP",
        "query": "Faiss 文档如何区分 HNSW/NSG 与 compact quantization codes：是否保留原始向量、主要代价分别是什么？",
        "expected_document_id": "rw-rag-faiss-overview",
        "required_gold_chunk_ids": [
            "rw-rag-faiss-overview:3:abc1acd7118fd514f140730d4c3d927c894d41d9d78c2a0785bf92fbcfb43f7d"
        ],
        "acceptable_gold_chunk_ids": [],
        "unsupported_decoy_chunk_ids": [
            "rw-rag-faiss-overview:4:74026825851538910e1e3b19be6f5ca98b2620c0ab43d9cd66b4e9c6d3c66538"
        ],
        "gold_rationale": "The required chunk contrasts compressed-only representations and their precision cost with graph structures over raw vectors; the neighbor repeats HNSW/NSG but shifts to GPU indexes.",
        "has_natural_decoy": True,
        "lexical_signal": "RARE_TERM",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def import_phase2() -> Any:
    phase2 = str(PHASE2_DIR.resolve())
    if phase2 not in sys.path:
        sys.path.insert(0, phase2)
    import experiment

    return experiment


def production_snapshot(run_id: str, stage: str) -> dict[str, Any]:
    reference = read_json(PRODUCTION_REFERENCE)
    rows: list[dict[str, Any]] = []
    for source in reference["rows"]:
        path = ROOT / source["path"]
        observed = file_hash(path)
        expected = source["frozen_reference_sha256"]
        rows.append(
            {
                "path": source["path"],
                "frozen_reference_sha256": expected,
                f"v1_4_{stage}_sha256": observed,
                "matches_frozen_reference": observed == expected,
            }
        )
    return {
        "run_id": run_id,
        "recorded_at": utc_now(),
        "stage": stage,
        "reference_file": relative(PRODUCTION_REFERENCE),
        "file_count": len(rows),
        "production_frozen_hash_match": all(
            row["matches_frozen_reference"] for row in rows
        ),
        "rows": rows,
    }


def authoritative_config() -> dict[str, Any]:
    design = read_json(DESIGN_PATH)
    expected_design_sha = DESIGN_SHA_PATH.read_text(encoding="utf-8").strip().split()[0]
    actual_design_sha = file_hash(DESIGN_PATH)
    if actual_design_sha != expected_design_sha:
        raise RuntimeError("authoritative V1.1 design hash mismatch")
    phase2 = import_phase2()
    constant_checks = {
        "design_version": phase2.DESIGN_VERSION == "V1.1",
        "design_sha": phase2.ABLATION_DESIGN_SHA256 == actual_design_sha,
        "dense_threshold": phase2.DENSE_THRESHOLD == 0.35,
        "raw_branch_limit": phase2.RAW_BRANCH_LIMIT == 18,
        "fused_limit": phase2.FUSED_LIMIT == 18,
        "rrf_constant": phase2.RRF_CONSTANT == 60,
        "bm25_k1": phase2.BM25_K1 == 1.5,
        "bm25_b": phase2.BM25_B == 0.75,
        "bm25_epsilon": phase2.BM25_EPSILON == 0.25,
        "reranker_model": phase2.RERANKER_MODEL_ID == "BAAI/bge-reranker-v2-m3",
        "reranker_revision": phase2.RERANKER_REVISION
        == "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
        "token_cap": phase2.RERANKER_TOKEN_CAP == 1024,
        "final_top_k": phase2.FINAL_TOP_K == 6,
        "per_material_cap": phase2.PER_MATERIAL_CAP == 3,
        "max_chunk_chars": phase2.MAX_CHUNK_CHARS == 2200,
        "max_context_chars": phase2.MAX_CONTEXT_CHARS == 12000,
    }
    if not all(constant_checks.values()):
        raise RuntimeError(f"authoritative Phase 2 constants mismatch: {constant_checks}")
    dense_reference = read_json(DENSE_REFERENCE_MANIFEST)
    dense_effective = dense_reference["effective_configuration"]
    dense_checks = {
        "model": dense_effective["embedding_model"] == "BAAI/bge-m3",
        "revision": dense_effective["embedding_revision"] == "local-cache",
        "local_only": dense_effective["embedding_local_files_only"] is True,
        "device": dense_effective["embedding_device"] == "cpu",
        "normalized": dense_effective["embedding_normalize"] is True,
        "minimum_score": dense_effective["rag_min_score"] == 0.35,
        "top6": dense_effective["rag_top_k_default"] == 6,
    }
    if not all(dense_checks.values()):
        raise RuntimeError(f"authoritative Dense config mismatch: {dense_checks}")
    common = {
        "dense": {
            "model_id": "BAAI/bge-m3",
            "revision": "local-cache",
            "local_files_only": True,
            "device": "cpu",
            "normalized": True,
            "dimension": 1024,
            "index": "faiss.IndexFlatIP",
            "raw_top_k": 18,
            "admission_score_gte": 0.35,
            "query_rewrite": "none; authoritative 72-case diagnostic queries equal frozen gold questions 72/72",
        },
        "reranker": {
            "model_id": phase2.RERANKER_MODEL_ID,
            "revision": phase2.RERANKER_REVISION,
            "pair_token_cap": phase2.RERANKER_TOKEN_CAP,
            "score": "raw single logit, higher is better",
            "precision": "CUDA FP32; TF32 off; autocast off",
        },
        "governance": {
            "overlap_dedup": True,
            "per_material_first_pass_cap": phase2.PER_MATERIAL_CAP,
            "rank_ordered_backfill": True,
            "final_top_k": phase2.FINAL_TOP_K,
            "max_chunk_chars": phase2.MAX_CHUNK_CHARS,
            "max_context_chars": phase2.MAX_CONTEXT_CHARS,
        },
    }
    c_config = {
        **common,
        "arm": "C",
        "candidate_construction": "Dense Top18 -> score>=0.35 -> rerank all admitted",
        "no_refill_beyond_dense_rank_18": True,
    }
    d_config = {
        **common,
        "arm": "D",
        "candidate_construction": "Dense Top18 admission + BM25 Top18 membership admission -> identity union -> RRF -> fused Top18 -> rerank",
        "bm25": {
            "implementation": phase2.FrozenBM25Index.implementation_id,
            "analyzer": "frozen bilingual identifier/CJK analyzer",
            "k1": phase2.BM25_K1,
            "b": phase2.BM25_B,
            "epsilon": phase2.BM25_EPSILON,
            "raw_top_k": phase2.RAW_BRANCH_LIMIT,
        },
        "rrf": {
            "method": "equal-weight reciprocal rank fusion",
            "k": phase2.RRF_CONSTANT,
            "limit": phase2.FUSED_LIMIT,
            "formula": design["rrf_contract"]["formula"],
            "tie_break_order": design["rrf_contract"]["tie_break_order"],
        },
    }
    return {
        "status": "PASS",
        "created_at": utc_now(),
        "authoritative_design_path": relative(DESIGN_PATH),
        "authoritative_design_sha256": actual_design_sha,
        "phase2_reference_run": PHASE2_RUN,
        "dense_reference_run": DENSE_REFERENCE_RUN,
        "authoritative_c_config": "PASS",
        "authoritative_d_config": "PASS",
        "constant_checks": constant_checks,
        "dense_checks": dense_checks,
        "c_config": c_config,
        "d_config": d_config,
        "c_config_sha256": canonical_hash(c_config),
        "d_config_sha256": canonical_hash(d_config),
        "tuning_performed": False,
    }


def validate_cases(corpus: Any) -> list[dict[str, Any]]:
    if not 8 <= len(CASES) <= 12:
        raise RuntimeError("stress case count outside 8..12")
    if len({case["case_id"] for case in CASES}) != len(CASES):
        raise RuntimeError("duplicate stress case id")
    categories = Counter(case["category"] for case in CASES)
    if len(categories) < 5 or any(value < 2 for value in categories.values()):
        raise RuntimeError(f"category coverage mismatch: {categories}")
    exact_count = sum(
        case["query_type"] == "EXACT_LEXICAL_LOOKUP" for case in CASES
    )
    mixed_count = sum(
        case["query_type"] == "IDENTIFIER_PLUS_NATURAL_LANGUAGE"
        for case in CASES
    )
    if exact_count < 4 or mixed_count < 4:
        raise RuntimeError("query-type 40% requirement failed")
    audit_rows: list[dict[str, Any]] = []
    for case in CASES:
        required = case["required_gold_chunk_ids"]
        if not required:
            raise RuntimeError(f"case lacks required gold: {case['case_id']}")
        all_ids = (
            required
            + case["acceptable_gold_chunk_ids"]
            + case["unsupported_decoy_chunk_ids"]
        )
        missing = [identity for identity in all_ids if identity not in corpus.by_identity]
        if missing:
            raise RuntimeError(f"case references missing chunks: {case['case_id']} {missing}")
        wrong_doc = [
            identity
            for identity in required
            if corpus.by_identity[identity].document_id
            != case["expected_document_id"]
        ]
        if wrong_doc:
            raise RuntimeError(f"required gold document mismatch: {case['case_id']}")
        audit_rows.append(
            {
                "case_id": case["case_id"],
                "category": case["category"],
                "query_type": case["query_type"],
                "expected_document_id": case["expected_document_id"],
                "required_gold_chunks": [
                    {
                        "identity": identity,
                        "content_sha256": corpus.by_identity[identity].content_hash,
                        "section_title": corpus.by_identity[identity].section_title,
                        "semantic_evidence_excerpt": corpus.by_identity[
                            identity
                        ].raw_text[:500],
                    }
                    for identity in required
                ],
                "has_natural_decoy": case["has_natural_decoy"],
                "decoy_count": len(case["unsupported_decoy_chunk_ids"]),
                "gold_frozen_before_retrieval": True,
            }
        )
    return audit_rows


def freeze(run_id: str) -> None:
    run_dir = RESULTS_ROOT / run_id
    if run_dir.exists():
        raise RuntimeError(f"run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    phase2 = import_phase2()
    corpus = phase2.FrozenCorpus.from_project(ROOT)
    case_audit = validate_cases(corpus)
    corpus_manifest = read_json(V1 / "corpus_manifest.json")
    source_rows: list[dict[str, Any]] = []
    for document in corpus_manifest["documents"]:
        path = ROOT / document["repository_path"]
        observed = file_hash(path)
        if observed != document["corpus_sha256"]:
            raise RuntimeError(f"corpus source hash mismatch: {document['document_id']}")
        source_rows.append(
            {
                "document_id": document["document_id"],
                "repository_path": document["repository_path"],
                "sha256": observed,
                "used_by_stress_cases": document["document_id"]
                in {case["expected_document_id"] for case in CASES},
            }
        )
    created_at = utc_now()
    cases_payload = {
        "schema_version": "1.0",
        "run_id": run_id,
        "created_at": created_at,
        "status": "FROZEN",
        "stress_cases_frozen": True,
        "retrieval_executed_before_freeze": False,
        "case_count": len(CASES),
        "category_count": len({case["category"] for case in CASES}),
        "cases": CASES,
    }
    write_json(run_dir / "lexical_stress_cases.json", cases_payload)
    cases_file_sha = file_hash(run_dir / "lexical_stress_cases.json")
    source_audit = {
        "run_id": run_id,
        "created_at": created_at,
        "status": "PASS",
        "stress_dataset_gate": "PASS",
        "source_policy": "TIER_1_ONLY",
        "source_corpus": "RAG Real-world Corpus V1",
        "source_document_count": len(source_rows),
        "source_chunk_count": len(corpus.chunks),
        "stress_case_source_document_count": len(
            {case["expected_document_id"] for case in CASES}
        ),
        "all_sources_project_owned_existing_and_stable": True,
        "tier2_documents_added": 0,
        "external_internet_sources": 0,
        "fictional_documents": 0,
        "source_documents": source_rows,
        "case_gold_audit": case_audit,
    }
    write_json(run_dir / "stress_source_audit.json", source_audit)
    config = authoritative_config()
    config["run_id"] = run_id
    write_json(run_dir / "authoritative_cd_config.json", config)
    before = production_snapshot(run_id, "before")
    if not before["production_frozen_hash_match"]:
        raise RuntimeError("production frozen hash mismatch before retrieval")
    write_json(run_dir / "production_hashes_before.json", before)
    categories = Counter(case["category"] for case in CASES)
    query_types = Counter(case["query_type"] for case in CASES)
    manifest = {
        "schema_version": "1.0",
        "run_id": run_id,
        "created_at": created_at,
        "git_head": git("rev-parse", "HEAD"),
        "stress_dataset_gate": "PASS",
        "stress_cases_frozen": True,
        "retrieval_started": False,
        "case_count": len(CASES),
        "case_ids": [case["case_id"] for case in CASES],
        "category_count": len(categories),
        "category_counts": dict(categories),
        "query_type_counts": dict(query_types),
        "source_corpus": "RAG Real-world Corpus V1: 11 documents / 442 chunks",
        "source_document_hashes": source_rows,
        "gold_dataset_path": relative(run_dir / "lexical_stress_cases.json"),
        "gold_dataset_sha256": cases_file_sha,
        "c_config_sha256": config["c_config_sha256"],
        "d_config_sha256": config["d_config_sha256"],
        "freeze_invariants": {
            "query_and_gold_must_not_change_after_this_manifest": True,
            "cases_may_not_be_added_or_removed": True,
            "dataset_defect_requires_case_stop_not_reannotation": True,
        },
    }
    write_json(run_dir / "lexical_stress_manifest.json", manifest)
    print(
        json.dumps(
            {
                "run_id": run_id,
                "status": "FROZEN",
                "case_count": len(CASES),
                "category_count": len(categories),
                "dataset_sha256": cases_file_sha,
                "run_dir": str(run_dir),
            },
            indent=2,
        )
    )


def verify_freeze(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    cases = read_json(run_dir / "lexical_stress_cases.json")
    manifest = read_json(run_dir / "lexical_stress_manifest.json")
    if manifest["retrieval_started"] is not False:
        raise RuntimeError("independent freeze manifest was not created pre-retrieval")
    if not cases["stress_cases_frozen"] or not manifest["stress_cases_frozen"]:
        raise RuntimeError("stress cases are not frozen")
    observed = file_hash(run_dir / "lexical_stress_cases.json")
    if observed != manifest["gold_dataset_sha256"]:
        raise RuntimeError("frozen stress dataset hash mismatch")
    if [case["case_id"] for case in cases["cases"]] != manifest["case_ids"]:
        raise RuntimeError("frozen case IDs mismatch")
    return cases, manifest


def retrieve(run_id: str) -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HOME"] = str(DENSE_CACHE_ROOT)
    run_dir = RESULTS_ROOT / run_id
    cases_payload, manifest = verify_freeze(run_dir)
    config = read_json(run_dir / "authoritative_cd_config.json")
    if (
        config["authoritative_c_config"] != "PASS"
        or config["authoritative_d_config"] != "PASS"
    ):
        raise RuntimeError("authoritative C/D config gate failed")
    phase2 = import_phase2()
    corpus = phase2.FrozenCorpus.from_project(ROOT)

    backend = str((ROOT / "backend").resolve())
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.services.embedding.bge_m3 import BgeM3Embedder
    import faiss
    import numpy as np

    started = perf_counter()
    embedder = BgeM3Embedder(
        model_name="BAAI/bge-m3",
        model_revision="local-cache",
        cache_folder=DENSE_CACHE_ROOT,
        local_files_only=True,
        device="cpu",
        batch_size=8,
        normalized=True,
    )
    corpus_embed_started = perf_counter()
    document_vectors = embedder.embed_documents(
        [chunk.raw_text for chunk in corpus.chunks]
    )
    corpus_embedding_ms = (perf_counter() - corpus_embed_started) * 1000.0
    if document_vectors.shape != (442, 1024):
        raise RuntimeError(f"unexpected document embedding shape: {document_vectors.shape}")
    index = faiss.IndexFlatIP(1024)
    index.add(np.ascontiguousarray(document_vectors, dtype=np.float32))
    if index.ntotal != 442:
        raise RuntimeError("FAISS index does not contain 442 chunks")
    bm25_index = phase2.FrozenBM25Index(corpus.chunks)
    c_rows: list[dict[str, Any]] = []
    d_rows: list[dict[str, Any]] = []
    for sequence, case in enumerate(cases_payload["cases"], start=1):
        query = case["query"]
        dense_started = perf_counter()
        query_vector = embedder.embed_query(query)
        scores, indices = index.search(
            np.ascontiguousarray(query_vector, dtype=np.float32), 18
        )
        dense_ms = (perf_counter() - dense_started) * 1000.0
        dense_c: list[Any] = []
        dense_d: list[Any] = []
        for rank, (score, index_position) in enumerate(
            zip(scores[0].tolist(), indices[0].tolist(), strict=True), start=1
        ):
            chunk = corpus.chunks[int(index_position)]
            for arm, target in (("C", dense_c), ("D", dense_d)):
                candidate = phase2.Candidate.from_chunk(chunk, arm)
                candidate.dense_score = float(score)
                candidate.dense_rank = rank
                target.append(candidate)
        c_pool = phase2.build_candidate_pool(
            arm="C", dense_candidates=dense_c
        )
        c_input = sorted(
            (candidate for candidate in c_pool if candidate.candidate_admitted),
            key=lambda item: (int(item.dense_rank), item.identity),
        )
        bm25_started = perf_counter()
        bm25_candidates = bm25_index.retrieve(query, arm="D")
        bm25_ms = (perf_counter() - bm25_started) * 1000.0
        d_pool = phase2.build_candidate_pool(
            arm="D", dense_candidates=dense_d, bm25_candidates=bm25_candidates
        )
        fusion_started = perf_counter()
        d_input = phase2.reciprocal_rank_fusion(d_pool)
        fusion_ms = (perf_counter() - fusion_started) * 1000.0
        c_rows.append(
            {
                "sequence": sequence,
                "case_id": case["case_id"],
                "query": query,
                "dense_retrieval_ms": round(dense_ms, 6),
                "raw_dense_top18": [candidate.to_dict() for candidate in dense_c],
                "candidate_pool": [candidate.to_dict() for candidate in c_pool],
                "reranker_input": [candidate.to_dict() for candidate in c_input],
                "reranker_input_count": len(c_input),
            }
        )
        d_rows.append(
            {
                "sequence": sequence,
                "case_id": case["case_id"],
                "query": query,
                "dense_retrieval_ms_shared_with_c": round(dense_ms, 6),
                "bm25_retrieval_ms": round(bm25_ms, 6),
                "rrf_ms": round(fusion_ms, 6),
                "raw_dense_top18": [candidate.to_dict() for candidate in dense_d],
                "raw_bm25_top18": [
                    candidate.to_dict() for candidate in bm25_candidates
                ],
                "candidate_union_pool": [candidate.to_dict() for candidate in d_pool],
                "reranker_input_fused_top18": [
                    candidate.to_dict() for candidate in d_input
                ],
                "reranker_input_count": len(d_input),
            }
        )
        print(f"RETRIEVE {sequence:02d}/{len(CASES)} {case['case_id']}", flush=True)
    elapsed_ms = (perf_counter() - started) * 1000.0
    runtime = {
        "python": platform.python_version(),
        "python_executable": sys.executable,
        "sentence_transformers": __import__("sentence_transformers").__version__,
        "torch": __import__("torch").__version__,
        "faiss": faiss.__version__,
        "dense_model_id": "BAAI/bge-m3",
        "dense_model_revision": "local-cache",
        "dense_snapshot_revision": (
            DENSE_CACHE_ROOT
            / "hub/models--BAAI--bge-m3/refs/main"
        ).read_text(encoding="utf-8").strip(),
        "local_files_only": True,
        "network_downloads": 0,
        "document_embedding_ms": round(corpus_embedding_ms, 6),
        "retrieval_stage_total_ms": round(elapsed_ms, 6),
    }
    write_json(
        run_dir / "c_retrieval_results.json",
        {
            "run_id": run_id,
            "created_at": utc_now(),
            "status": "PASS",
            "arm": "C",
            "case_count": len(c_rows),
            "config_sha256": config["c_config_sha256"],
            "runtime": runtime,
            "rows": c_rows,
        },
    )
    write_json(
        run_dir / "d_retrieval_results.json",
        {
            "run_id": run_id,
            "created_at": utc_now(),
            "status": "PASS",
            "arm": "D",
            "case_count": len(d_rows),
            "config_sha256": config["d_config_sha256"],
            "runtime": runtime,
            "rows": d_rows,
        },
    )
    write_json(
        run_dir / "retrieval_runtime.json",
        {"run_id": run_id, "created_at": utc_now(), "status": "PASS", **runtime},
    )
    print(
        json.dumps(
            {
                "run_id": run_id,
                "status": "RETRIEVAL_PASS",
                "case_count": len(c_rows),
                "document_embedding_ms": runtime["document_embedding_ms"],
                "retrieval_stage_total_ms": runtime["retrieval_stage_total_ms"],
            },
            indent=2,
        )
    )


def candidate_from_dict(phase2: Any, value: dict[str, Any]) -> Any:
    names = {field.name for field in fields(phase2.Candidate)}
    kwargs = {name: value[name] for name in names}
    kwargs["evidence_ids"] = tuple(kwargs["evidence_ids"])
    return phase2.Candidate(**kwargs)


def rank_of(identities: list[str], gold: set[str]) -> int | None:
    for rank, identity in enumerate(identities, start=1):
        if identity in gold:
            return rank
    return None


def hit(identities: list[str], gold: set[str]) -> bool:
    return any(identity in gold for identity in identities)


def compact(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        key: candidate.get(key)
        for key in (
            "identity",
            "document_id",
            "chunk_index",
            "dense_score",
            "dense_rank",
            "branch_admitted_dense",
            "bm25_score",
            "bm25_rank",
            "branch_admitted_bm25",
            "fusion_score",
            "fusion_rank",
            "reranker_score",
            "reranker_rank",
            "selected",
            "rejection_reason",
        )
    }


def score_and_finalize(run_id: str) -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    run_dir = RESULTS_ROOT / run_id
    cases_payload, frozen_manifest = verify_freeze(run_dir)
    c_retrieval = read_json(run_dir / "c_retrieval_results.json")
    d_retrieval = read_json(run_dir / "d_retrieval_results.json")
    config = read_json(run_dir / "authoritative_cd_config.json")
    if c_retrieval["case_count"] != len(CASES) or d_retrieval["case_count"] != len(CASES):
        raise RuntimeError("retrieval results do not cover the frozen cases")
    if [row["case_id"] for row in c_retrieval["rows"]] != frozen_manifest["case_ids"]:
        raise RuntimeError("C retrieval case order differs from freeze")
    if [row["case_id"] for row in d_retrieval["rows"]] != frozen_manifest["case_ids"]:
        raise RuntimeError("D retrieval case order differs from freeze")

    import torch

    expected_packages = {
        "torch": "2.12.1+cu126",
        "transformers": "5.12.1",
        "tokenizers": "0.22.2",
        "safetensors": "0.8.0",
    }
    packages = {
        "torch": torch.__version__,
        "transformers": __import__("transformers").__version__,
        "tokenizers": __import__("tokenizers").__version__,
        "safetensors": __import__("safetensors").__version__,
    }
    environment_checks = {
        "python_3_11_9": platform.python_version() == "3.11.9",
        "packages_exact": packages == expected_packages,
        "cuda_available": torch.cuda.is_available(),
        "cuda_build_12_6": torch.version.cuda == "12.6",
        "gpu_rtx_4060": torch.cuda.is_available()
        and torch.cuda.get_device_name(0) == "NVIDIA GeForce RTX 4060 Laptop GPU",
        "snapshot_revision": RERANKER_SNAPSHOT.name
        == "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
    }
    if not all(environment_checks.values()):
        raise RuntimeError(f"CUDA/reranker environment gate failed: {environment_checks}")
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.set_float32_matmul_precision("highest")
    phase2 = import_phase2()
    score_started = perf_counter()
    reranker = phase2.HuggingFaceRerankerAdapter(
        RERANKER_SNAPSHOT, device="cuda:0"
    )
    parameter = next(reranker.model.parameters())
    strict_checks = {
        "allow_tf32_matmul_false": torch.backends.cuda.matmul.allow_tf32 is False,
        "allow_tf32_cudnn_false": torch.backends.cudnn.allow_tf32 is False,
        "float32_matmul_precision_highest": torch.get_float32_matmul_precision()
        == "highest",
        "model_device_cuda_0": str(parameter.device) == "cuda:0",
        "model_dtype_float32": parameter.dtype == torch.float32,
        "all_parameters_float32": all(
            item.dtype == torch.float32 for item in reranker.model.parameters()
        ),
        "model_eval": reranker.model.training is False,
        "autocast_false": not torch.is_autocast_enabled("cuda"),
    }
    if not all(strict_checks.values()):
        raise RuntimeError(f"strict CUDA FP32 gate failed: {strict_checks}")

    c_scored: list[dict[str, Any]] = []
    d_scored: list[dict[str, Any]] = []
    for sequence, (case, c_row, d_row) in enumerate(
        zip(
            cases_payload["cases"],
            c_retrieval["rows"],
            d_retrieval["rows"],
            strict=True,
        ),
        start=1,
    ):
        scored_arms: list[tuple[str, dict[str, Any], list[Any]]] = []
        for arm, row, field_name in (
            ("C", c_row, "reranker_input"),
            ("D", d_row, "reranker_input_fused_top18"),
        ):
            candidates = [
                candidate_from_dict(phase2, value) for value in row[field_name]
            ]
            torch.cuda.synchronize()
            rerank_started = perf_counter()
            ordered = phase2.apply_reranker(
                query=case["query"], candidates=candidates, reranker=reranker
            )
            torch.cuda.synchronize()
            reranker_ms = (perf_counter() - rerank_started) * 1000.0
            selected = phase2.govern_evidence(ordered)
            result = {
                "sequence": sequence,
                "case_id": case["case_id"],
                "query": case["query"],
                "arm": arm,
                "reranker_input_count": len(candidates),
                "reranker_ms": round(reranker_ms, 6),
                "ordered_candidates": [candidate.to_dict() for candidate in ordered],
                "top6": [candidate.to_dict() for candidate in selected],
                "top6_ids": [candidate.identity for candidate in selected],
            }
            scored_arms.append((arm, result, selected))
        c_scored.append(scored_arms[0][1])
        d_scored.append(scored_arms[1][1])
        print(f"RERANK {sequence:02d}/{len(CASES)} {case['case_id']}", flush=True)
    torch.cuda.synchronize()
    reranker_stage_ms = (perf_counter() - score_started) * 1000.0

    comparisons: list[dict[str, Any]] = []
    unique_candidate: list[dict[str, Any]] = []
    unique_final: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []
    lexical_attribution: list[dict[str, Any]] = []
    for case, c_ret, d_ret, c_out, d_out in zip(
        cases_payload["cases"],
        c_retrieval["rows"],
        d_retrieval["rows"],
        c_scored,
        d_scored,
        strict=True,
    ):
        required = set(case["required_gold_chunk_ids"])
        acceptable = set(case["acceptable_gold_chunk_ids"])
        answerable = required | acceptable
        c18 = [item["identity"] for item in c_ret["reranker_input"]]
        d18 = [
            item["identity"] for item in d_ret["reranker_input_fused_top18"]
        ]
        c6 = c_out["top6_ids"]
        d6 = d_out["top6_ids"]
        c_req18, d_req18 = hit(c18, required), hit(d18, required)
        c_ans18, d_ans18 = hit(c18, answerable), hit(d18, answerable)
        c_req6, d_req6 = hit(c6, required), hit(d6, required)
        c_ans6, d_ans6 = hit(c6, answerable), hit(d6, answerable)
        candidate_fix = (not c_req18 and d_req18) or (not c_ans18 and d_ans18)
        final_fix = not c_ans6 and d_ans6
        regression = c_ans6 and not d_ans6
        row = {
            "case_id": case["case_id"],
            "category": case["category"],
            "query": case["query"],
            "required_gold_chunk_ids": sorted(required),
            "acceptable_gold_chunk_ids": sorted(acceptable),
            "c_required_hit_at_18": c_req18,
            "d_required_hit_at_18": d_req18,
            "c_acceptable_hit_at_18": hit(c18, acceptable),
            "d_acceptable_hit_at_18": hit(d18, acceptable),
            "c_answerable_hit_at_18": c_ans18,
            "d_answerable_hit_at_18": d_ans18,
            "c_best_gold_rank_at_18": rank_of(c18, answerable),
            "d_best_gold_rank_at_18": rank_of(d18, answerable),
            "c_required_hit_at_6": c_req6,
            "d_required_hit_at_6": d_req6,
            "c_acceptable_hit_at_6": hit(c6, acceptable),
            "d_acceptable_hit_at_6": hit(d6, acceptable),
            "c_answerable_hit_at_6": c_ans6,
            "d_answerable_hit_at_6": d_ans6,
            "c_best_gold_reranked_rank": rank_of(
                [item["identity"] for item in c_out["ordered_candidates"]], answerable
            ),
            "d_best_gold_reranked_rank": rank_of(
                [item["identity"] for item in d_out["ordered_candidates"]], answerable
            ),
            "c_best_gold_final_rank": rank_of(c6, answerable),
            "d_best_gold_final_rank": rank_of(d6, answerable),
            "d_unique_candidate_fix": candidate_fix,
            "d_unique_final_fix": final_fix,
            "d_regression": regression,
            "rank_improvement_only": c_ans18
            and d_ans18
            and (rank_of(d18, answerable) or 999) < (rank_of(c18, answerable) or 999),
            "c_candidate_pool_ids": c18,
            "d_candidate_pool_ids": d18,
            "c_top6_ids": c6,
            "d_top6_ids": d6,
        }
        comparisons.append(row)
        if candidate_fix:
            unique_candidate.append(row)
        if final_fix:
            unique_final.append(row)
        if regression:
            regressions.append(
                {
                    **row,
                    "failure_mechanism": "D hybrid fusion/candidate-set change removed the only answerable gold from governed Top6.",
                    "c_candidates": [compact(item) for item in c_ret["reranker_input"]],
                    "d_candidates": [
                        compact(item) for item in d_ret["reranker_input_fused_top18"]
                    ],
                    "c_reranked": [compact(item) for item in c_out["ordered_candidates"]],
                    "d_reranked": [compact(item) for item in d_out["ordered_candidates"]],
                }
            )
        if candidate_fix or final_fix:
            target_ids = [identity for identity in d6 if identity in answerable]
            if not target_ids:
                target_ids = [identity for identity in d18 if identity in answerable]
            d_candidates = {
                item["identity"]: item
                for item in d_ret["reranker_input_fused_top18"]
            }
            d_reranked = {
                item["identity"]: item for item in d_out["ordered_candidates"]
            }
            for identity in target_ids[:1]:
                candidate = d_candidates[identity]
                scored = d_reranked[identity]
                dense_raw_present = candidate["dense_rank"] is not None
                dense_admitted = candidate["branch_admitted_dense"]
                lexical_causal = candidate["branch_admitted_bm25"] and not dense_admitted
                attribution = {
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "why_d_helped": case["lexical_signal"],
                    "gold_chunk_id": identity,
                    "dense_rank": candidate["dense_rank"],
                    "dense_raw_top18_present": dense_raw_present,
                    "dense_branch_admitted": dense_admitted,
                    "bm25_rank": candidate["bm25_rank"],
                    "rrf_fused_rank": candidate["fusion_rank"],
                    "reranked_rank": scored["reranker_rank"],
                    "final_top6_rank": rank_of(d6, {identity}),
                    "lexical_channel_admitted_target": candidate[
                        "branch_admitted_bm25"
                    ],
                    "lexical_channel_causal_for_candidate_entry": lexical_causal,
                    "claim_boundary": (
                        "BM25 supplied unique branch admission for the answerable gold."
                        if lexical_causal
                        else "Gold was already Dense-admitted; this is fusion/ranking change, not a retrieval blind-spot fix."
                    ),
                    "short_evidence": case["gold_rationale"],
                }
                lexical_attribution.append(attribution)

    def metrics_for(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "total_cases": len(rows),
            "c_required_hit_at_18": sum(row["c_required_hit_at_18"] for row in rows),
            "d_required_hit_at_18": sum(row["d_required_hit_at_18"] for row in rows),
            "c_required_hit_at_6": sum(row["c_required_hit_at_6"] for row in rows),
            "d_required_hit_at_6": sum(row["d_required_hit_at_6"] for row in rows),
            "c_answerable_cases_at_6": sum(row["c_answerable_hit_at_6"] for row in rows),
            "d_answerable_cases_at_6": sum(row["d_answerable_hit_at_6"] for row in rows),
            "d_unique_candidate_fixes": [
                row["case_id"] for row in rows if row["d_unique_candidate_fix"]
            ],
            "d_unique_final_fixes": [
                row["case_id"] for row in rows if row["d_unique_final_fix"]
            ],
            "d_regressions": [row["case_id"] for row in rows if row["d_regression"]],
            "c_only_successes": sum(
                row["c_answerable_hit_at_6"] and not row["d_answerable_hit_at_6"]
                for row in rows
            ),
            "d_only_successes": sum(
                row["d_answerable_hit_at_6"] and not row["c_answerable_hit_at_6"]
                for row in rows
            ),
            "both_success": sum(
                row["c_answerable_hit_at_6"] and row["d_answerable_hit_at_6"]
                for row in rows
            ),
            "both_fail": sum(
                not row["c_answerable_hit_at_6"] and not row["d_answerable_hit_at_6"]
                for row in rows
            ),
        }

    summary = metrics_for(comparisons)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in comparisons:
        grouped[row["category"]].append(row)
    category_metrics = {
        category: metrics_for(rows) for category, rows in sorted(grouped.items())
    }
    final_fix_categories = {
        row["category"] for row in comparisons if row["d_unique_final_fix"]
    }
    if summary["d_regressions"]:
        signal = "MIXED"
    elif len(summary["d_unique_final_fixes"]) >= 2 and len(final_fix_categories) >= 2:
        signal = "MEANINGFUL"
    elif not summary["d_unique_candidate_fixes"] and not summary["d_unique_final_fixes"]:
        signal = "NONE"
    elif len(summary["d_unique_final_fixes"]) <= 1:
        signal = "WEAK"
    else:
        signal = "MIXED"
    reopen = (
        "YES"
        if signal == "MEANINGFUL"
        else "YES_WITH_CAUTION"
        if signal == "MIXED"
        else "NO"
    )
    decision = {
        "hybrid_lexical_value_signal": signal,
        "reopen_d_for_v1_consideration": reopen,
        "basis": {
            "unique_candidate_fix_count": len(summary["d_unique_candidate_fixes"]),
            "unique_final_fix_count": len(summary["d_unique_final_fixes"]),
            "unique_final_fix_category_count": len(final_fix_categories),
            "regression_count": len(summary["d_regressions"]),
        },
        "interpretation_boundary": "Targeted lexical/domain-shift incremental value only; no overall C-vs-D superiority claim and no architecture selection.",
        "final_rag_architecture": "NOT_YET_FROZEN",
    }
    candidate_comparison = [
        {
            key: row[key]
            for key in (
                "case_id",
                "category",
                "c_required_hit_at_18",
                "d_required_hit_at_18",
                "c_acceptable_hit_at_18",
                "d_acceptable_hit_at_18",
                "c_answerable_hit_at_18",
                "d_answerable_hit_at_18",
                "c_best_gold_rank_at_18",
                "d_best_gold_rank_at_18",
                "d_unique_candidate_fix",
                "rank_improvement_only",
                "c_candidate_pool_ids",
                "d_candidate_pool_ids",
            )
        }
        for row in comparisons
    ]
    top6_comparison = [
        {
            key: row[key]
            for key in (
                "case_id",
                "category",
                "c_required_hit_at_6",
                "d_required_hit_at_6",
                "c_acceptable_hit_at_6",
                "d_acceptable_hit_at_6",
                "c_answerable_hit_at_6",
                "d_answerable_hit_at_6",
                "c_best_gold_reranked_rank",
                "d_best_gold_reranked_rank",
                "c_best_gold_final_rank",
                "d_best_gold_final_rank",
                "d_unique_final_fix",
                "d_regression",
                "c_top6_ids",
                "d_top6_ids",
            )
        }
        for row in comparisons
    ]
    common_header = {"run_id": run_id, "created_at": utc_now(), "status": "PASS"}
    write_json(
        run_dir / "candidate_level_comparison.json",
        {**common_header, "rows": candidate_comparison},
    )
    write_json(
        run_dir / "top6_comparison.json", {**common_header, "rows": top6_comparison}
    )
    write_json(
        run_dir / "d_unique_fixes.json",
        {
            **common_header,
            "candidate_level": unique_candidate,
            "final_top6": unique_final,
        },
    )
    write_json(
        run_dir / "d_regressions.json",
        {**common_header, "count": len(regressions), "rows": regressions},
    )
    write_json(
        run_dir / "lexical_attribution.json",
        {**common_header, "rows": lexical_attribution},
    )
    write_json(
        run_dir / "category_metrics.json",
        {**common_header, "categories": category_metrics},
    )
    summary_payload = {
        **common_header,
        **summary,
        "authoritative_c_config": "PASS",
        "authoritative_d_config": "PASS",
        "same_reranker_and_governance": True,
        "full_72_case_rerun": False,
        "deepseek_calls": 0,
        "generation_runs": 0,
        "retrieval_cases_per_arm": len(CASES),
        "reranker_batches": reranker.inference_calls,
        "reranker_pairs": reranker.pair_count,
        "reranker_stage_ms_including_model_load": round(reranker_stage_ms, 6),
    }
    write_json(run_dir / "summary_metrics.json", summary_payload)
    write_json(run_dir / "decision_signal.json", {**common_header, **decision})
    write_json(
        run_dir / "reranker_runtime.json",
        {
            **common_header,
            "python": platform.python_version(),
            "python_executable": sys.executable,
            "packages": packages,
            "cuda_build": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0),
            "environment_checks": environment_checks,
            "strict_fp32_checks": strict_checks,
            "model_path": str(RERANKER_SNAPSHOT),
            "model_load_seconds": reranker.load_seconds,
            "inference_batches": reranker.inference_calls,
            "pair_count": reranker.pair_count,
            "network_model_downloads": 0,
            "latency_benchmark_executed": False,
        },
    )
    after = production_snapshot(run_id, "after")
    before = read_json(run_dir / "production_hashes_before.json")
    before_by_path = {
        row["path"]: row["v1_4_before_sha256"] for row in before["rows"]
    }
    for row in after["rows"]:
        row["v1_4_before_sha256"] = before_by_path[row["path"]]
        row["byte_identical_during_v1_4"] = (
            row["v1_4_after_sha256"] == before_by_path[row["path"]]
        )
    after["production_frozen_hash_match"] = after[
        "production_frozen_hash_match"
    ] and all(row["byte_identical_during_v1_4"] for row in after["rows"])
    if not after["production_frozen_hash_match"]:
        raise RuntimeError("production frozen hash mismatch after stress test")
    write_json(run_dir / "production_hashes_after.json", after)

    report = f"""# LearnPilot RAG C V1.4 — Lexical / Domain-Shift Retrieval Stress Test

## Result

The preregistered 10-case targeted stress test completed with status `PASS`. This is targeted lexical/domain-shift evidence, not an overall C-vs-D superiority claim and not an architecture selection.

## Frozen dataset and configuration

- Run ID: `{run_id}`
- Sources: existing project-owned RAG Real-world Corpus V1 only; 11 documents / 442 chunks; no Tier 2 additions
- Cases/categories: `10` / `5`; two cases in each category
- Frozen before retrieval: `true`; dataset SHA-256 `{frozen_manifest['gold_dataset_sha256']}`
- Authoritative C/D configuration: `PASS` / `PASS`; no BM25, RRF, Top18, reranker, or Top6 tuning

## Metrics

- C vs D required Hit@18: `{summary['c_required_hit_at_18']}/10` vs `{summary['d_required_hit_at_18']}/10`
- C vs D required Hit@6: `{summary['c_required_hit_at_6']}/10` vs `{summary['d_required_hit_at_6']}/10`
- C vs D answerable Top6: `{summary['c_answerable_cases_at_6']}/10` vs `{summary['d_answerable_cases_at_6']}/10`
- D unique candidate fixes: `{summary['d_unique_candidate_fixes']}`
- D unique final fixes: `{summary['d_unique_final_fixes']}`
- D regressions: `{summary['d_regressions']}`
- C-only / D-only / both-success / both-fail: `{summary['c_only_successes']}` / `{summary['d_only_successes']}` / `{summary['both_success']}` / `{summary['both_fail']}`

## Decision signal

- `HYBRID_LEXICAL_VALUE_SIGNAL = {signal}`
- `REOPEN_D_FOR_V1_CONSIDERATION = {reopen}`
- `FINAL_RAG_ARCHITECTURE = NOT_YET_FROZEN`

## Integrity and scope

- Production frozen files unchanged: `true` (15/15)
- DeepSeek calls: `0`
- Generation runs: `0`
- Full 72-case rerun: `false`
- Production code/dependency/index changes: `0`

## Final status

```text
RAG_C_V1_4_LEXICAL_DOMAIN_SHIFT_STRESS = PASS
STRESS_DATASET_GATE = PASS
STRESS_CASES_FROZEN = true
TOTAL_CASES = 10
CATEGORY_COUNT = 5
AUTHORITATIVE_C_CONFIG = PASS
AUTHORITATIVE_D_CONFIG = PASS
C_REQUIRED_HIT_AT_18 = {summary['c_required_hit_at_18']}/10
D_REQUIRED_HIT_AT_18 = {summary['d_required_hit_at_18']}/10
C_REQUIRED_HIT_AT_6 = {summary['c_required_hit_at_6']}/10
D_REQUIRED_HIT_AT_6 = {summary['d_required_hit_at_6']}/10
C_ANSWERABLE_CASES_AT_6 = {summary['c_answerable_cases_at_6']}/10
D_ANSWERABLE_CASES_AT_6 = {summary['d_answerable_cases_at_6']}/10
D_UNIQUE_CANDIDATE_FIXES = {json.dumps(summary['d_unique_candidate_fixes'])}
D_UNIQUE_FINAL_FIXES = {json.dumps(summary['d_unique_final_fixes'])}
D_REGRESSIONS = {json.dumps(summary['d_regressions'])}
HYBRID_LEXICAL_VALUE_SIGNAL = {signal}
REOPEN_D_FOR_V1_CONSIDERATION = {reopen}
DEEPSEEK_CALLS = 0
GENERATION_RUNS = 0
FULL_72_CASE_RERUN = false
PRODUCTION_CODE_CHANGED = false
PRODUCTION_DEPENDENCIES_CHANGED = false
PRODUCTION_FROZEN_HASH_MATCH = true
FINAL_RAG_ARCHITECTURE = NOT_YET_FROZEN
```
"""
    REPORT_PATH.write_text(report, encoding="utf-8")

    artifact_paths = [
        run_dir / name
        for name in (
            "stress_source_audit.json",
            "lexical_stress_cases.json",
            "lexical_stress_manifest.json",
            "authoritative_cd_config.json",
            "production_hashes_before.json",
            "production_hashes_after.json",
            "c_retrieval_results.json",
            "d_retrieval_results.json",
            "retrieval_runtime.json",
            "candidate_level_comparison.json",
            "top6_comparison.json",
            "d_unique_fixes.json",
            "d_regressions.json",
            "lexical_attribution.json",
            "category_metrics.json",
            "summary_metrics.json",
            "decision_signal.json",
            "reranker_runtime.json",
        )
    ] + [REPORT_PATH, Path(__file__).resolve()]
    corpus_manifest = read_json(V1 / "corpus_manifest.json")
    source_hashes = [
        {
            "document_id": document["document_id"],
            "path": document["repository_path"],
            "sha256": document["corpus_sha256"],
        }
        for document in corpus_manifest["documents"]
    ]
    manifest = {
        "run_id": run_id,
        "created_at": utc_now(),
        "status": "PASS",
        "git_head": git("rev-parse", "HEAD"),
        "source_corpus": "RAG Real-world Corpus V1: 11 documents / 442 chunks",
        "source_document_hashes": source_hashes,
        "stress_dataset_sha256": frozen_manifest["gold_dataset_sha256"],
        "case_count": len(CASES),
        "case_ids": frozen_manifest["case_ids"],
        "c_config_sha256": config["c_config_sha256"],
        "d_config_sha256": config["d_config_sha256"],
        "dense_model_identity": c_retrieval["runtime"],
        "reranker_model_identity": {
            "model_id": "BAAI/bge-reranker-v2-m3",
            "revision": RERANKER_SNAPSHOT.name,
            "torch": packages["torch"],
            "cuda_build": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0),
            "precision": "FP32",
        },
        "artifacts": [
            {
                "path": relative(path),
                "size_bytes": path.stat().st_size,
                "sha256": file_hash(path),
            }
            for path in artifact_paths
        ],
        "execution_audit": {
            "stress_cases_frozen_before_retrieval": True,
            "deepseek_calls": 0,
            "generation_runs": 0,
            "full_72_case_rerun": False,
            "production_code_changed": False,
            "production_dependencies_changed": False,
            "production_index_mutated": False,
            "production_frozen_hash_match": True,
        },
        "decision_boundary": decision,
    }
    write_json(run_dir / "artifact_manifest.json", manifest)
    print(
        json.dumps(
            {
                "run_id": run_id,
                "status": "PASS",
                "summary": summary,
                "hybrid_lexical_value_signal": signal,
                "reopen_d_for_v1_consideration": reopen,
                "run_dir": str(run_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--freeze", action="store_true")
    modes.add_argument("--retrieve", action="store_true")
    modes.add_argument("--score", action="store_true")
    args = parser.parse_args()
    if args.freeze:
        freeze(args.run_id)
    elif args.retrieve:
        retrieve(args.run_id)
    else:
        score_and_finalize(args.run_id)


if __name__ == "__main__":
    main()
