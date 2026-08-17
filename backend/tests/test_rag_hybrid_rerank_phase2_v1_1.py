from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "evals/rag_real_world_corpus/v1"
PHASE = V1 / "hybrid_rerank_phase2_v1_1"
POST_C_PRODUCTION = V1 / "post_c_production_integrity_v1.json"
if str(PHASE) not in sys.path:
    sys.path.insert(0, str(PHASE))
GOLD_HELPERS = V1 / "gold/v1"
if str(GOLD_HELPERS) not in sys.path:
    sys.path.insert(0, str(GOLD_HELPERS))

from experiment import (  # noqa: E402
    ABLATION_DESIGN_SHA256,
    BM25_B,
    BM25_EPSILON,
    BM25_K1,
    Candidate,
    ContractViolation,
    CorpusChunk,
    DENSE_THRESHOLD,
    FUSED_LIMIT,
    FrozenBM25Index,
    FrozenCorpus,
    FrozenDenseTraceAdapter,
    RERANKER_MODEL_ID,
    RERANKER_REVISION,
    RERANKER_TOKEN_CAP,
    REJECTION_REASONS,
    RRF_CONSTANT,
    RerankObservation,
    analyze_lexical,
    apply_reranker,
    build_candidate_pool,
    build_xlm_roberta_pair_feature,
    candidate_order,
    enforce_pair_token_budget,
    execute_arm,
    govern_evidence,
    reciprocal_rank_fusion,
    stable_candidate_identity,
)
from gold_common import json_schema_errors  # noqa: E402


V1_DESIGN_SHA256 = "4c3b2e294b63dcc0ae57be1d30d713b3cf1ffed5b0f3a989499f1298902703c6"
BASELINE_PATH = (
    V1
    / "results/dense_only_baseline_v1/20260814T052007Z-593cd2ac/raw_results.json"
)


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def make_chunk(
    identity_prefix: str,
    index: int,
    text: str,
    *,
    material_id: int = 1,
    chunk_id: int | None = None,
) -> CorpusChunk:
    content_hash = sha256(text.encode("utf-8")).hexdigest()
    document_id = f"doc-{identity_prefix}"
    return CorpusChunk(
        identity=stable_candidate_identity(document_id, index, content_hash),
        document_id=document_id,
        chunk_index=index,
        content_hash=content_hash,
        filename=f"{document_id}.md",
        page_number=None,
        section_title="fixture",
        raw_text=text,
        material_id=material_id,
        chunk_id=chunk_id if chunk_id is not None else index + 1,
        evidence_ids=(),
    )


def candidate(
    identity_prefix: str,
    index: int,
    text: str,
    *,
    arm: str = "B",
    dense_score: float | None = None,
    dense_rank: int | None = None,
    bm25_score: float | None = None,
    bm25_rank: int | None = None,
    material_id: int = 1,
) -> Candidate:
    result = Candidate.from_chunk(
        make_chunk(identity_prefix, index, text, material_id=material_id), arm
    )
    result.dense_score = dense_score
    result.dense_rank = dense_rank
    result.bm25_score = bm25_score
    result.bm25_rank = bm25_rank
    return result


@pytest.fixture(scope="session")
def frozen_corpus() -> FrozenCorpus:
    return FrozenCorpus.from_project(ROOT)


@pytest.fixture(scope="session")
def dense_adapter(frozen_corpus: FrozenCorpus) -> FrozenDenseTraceAdapter:
    return FrozenDenseTraceAdapter(BASELINE_PATH, frozen_corpus)


def test_analyzer_applies_nfkc_casefold_and_preserves_identifier_plus_parts():
    assert analyze_lexical("ＢＡＡＩ／ＢＧＥ－Ｍ３") == [
        "baai/bge-m3",
        "baai",
        "bge",
        "m3",
    ]
    assert analyze_lexical("Foo_Bar.py/HTTP:2") == [
        "foo_bar.py/http:2",
        "foo",
        "bar",
        "py",
        "http",
        "2",
    ]


def test_analyzer_emits_overlapping_cjk_bigrams_and_single_character_unigram():
    assert analyze_lexical("中文测试") == ["中文", "文测", "测试"]
    assert analyze_lexical("中") == ["中"]
    assert analyze_lexical("中，A-1，文") == ["中", "a-1", "a", "1", "文"]


def test_query_and_document_analyzer_are_the_same_pure_function():
    value = "FastAPI 依赖 BAAI/bge-m3"
    assert analyze_lexical(value) == analyze_lexical(value)
    assert analyze_lexical(value) == [
        "fastapi",
        "依赖",
        "baai/bge-m3",
        "baai",
        "bge",
        "m3",
    ]


def test_frozen_corpus_reconstructs_all_442_exact_stable_chunk_identities(
    frozen_corpus: FrozenCorpus,
):
    assert len(frozen_corpus.chunks) == 442
    assert len(frozen_corpus.by_identity) == 442
    assert len(frozen_corpus.by_document_chunk) == 442
    for chunk in frozen_corpus.chunks:
        assert chunk.identity == stable_candidate_identity(
            chunk.document_id, chunk.chunk_index, chunk.content_hash
        )
        assert sha256(chunk.raw_text.encode("utf-8")).hexdigest() == chunk.content_hash


def test_identity_collision_and_raw_text_tampering_are_hard_failures():
    dense = candidate("same", 0, "same text", dense_score=0.5, dense_rank=1)
    lexical = candidate("same", 0, "same text", bm25_score=2.0, bm25_rank=1)
    lexical.filename = "different.md"
    with pytest.raises(ContractViolation, match="identity collision"):
        build_candidate_pool(arm="B", dense_candidates=[dense], bm25_candidates=[lexical])
    tampered = candidate("tampered", 0, "original", dense_score=0.5, dense_rank=1)
    tampered.raw_text = "changed"
    with pytest.raises(ContractViolation, match="raw text hash mismatch"):
        build_candidate_pool(arm="C", dense_candidates=[tampered])


def test_dense_bm25_or_admission_preserves_nonadmitting_dense_provenance():
    dense = candidate("dual", 0, "dual", dense_score=0.31, dense_rank=8)
    lexical = candidate("dual", 0, "dual", bm25_score=7.25, bm25_rank=3)
    merged = build_candidate_pool(
        arm="B", dense_candidates=[dense], bm25_candidates=[lexical]
    )[0]
    assert merged.dense_score == 0.31
    assert merged.dense_rank == 8
    assert merged.branch_admitted_dense is False
    assert merged.dense_fusion_rank is None
    assert merged.bm25_score == 7.25
    assert merged.bm25_rank == 3
    assert merged.branch_admitted_bm25 is True
    assert merged.bm25_fusion_rank == 3
    assert merged.candidate_admitted is True
    assert merged.rejection_reason is None


def test_dense_only_ineligible_candidate_is_rejected_before_c_reranking():
    low = candidate("low", 0, "low", arm="C", dense_score=0.3499, dense_rank=1)
    pool = build_candidate_pool(arm="C", dense_candidates=[low])
    assert pool[0].branch_admitted_dense is False
    assert pool[0].candidate_admitted is False
    assert pool[0].dense_fusion_rank is None
    assert pool[0].rejection_reason == "dense_ineligible"


def test_bm25_scores_match_frozen_okapi_formula_and_order_is_deterministic():
    chunks = (
        make_chunk("a", 0, "alpha alpha beta"),
        make_chunk("b", 0, "alpha gamma", material_id=2),
        make_chunk("c", 0, "delta", material_id=3),
    )
    index = FrozenBM25Index(chunks)
    scores = index.score("alpha")
    raw_idfs = {
        "alpha": math.log(3 - 2 + 0.5) - math.log(2 + 0.5),
        "beta": math.log(3 - 1 + 0.5) - math.log(1 + 0.5),
        "gamma": math.log(3 - 1 + 0.5) - math.log(1 + 0.5),
        "delta": math.log(3 - 1 + 0.5) - math.log(1 + 0.5),
    }
    average_idf = sum(raw_idfs.values()) / len(raw_idfs)
    alpha_idf = BM25_EPSILON * average_idf
    avgdl = 2.0
    expected_first = alpha_idf * (
        2 * (BM25_K1 + 1)
        / (2 + BM25_K1 * (1 - BM25_B + BM25_B * 3 / avgdl))
    )
    expected_second = alpha_idf * (
        1 * (BM25_K1 + 1)
        / (1 + BM25_K1 * (1 - BM25_B + BM25_B * 2 / avgdl))
    )
    assert scores == pytest.approx([expected_first, expected_second, 0.0])
    first = index.retrieve("alpha", arm="B")
    second = index.retrieve("alpha", arm="B")
    assert candidate_order(first) == candidate_order(second)
    assert [item.bm25_rank for item in first] == [1, 2, 3]


def test_rrf_exact_formula_uses_only_admitted_branch_contributions():
    dense = candidate("dual", 0, "dual", dense_score=0.31, dense_rank=8)
    lexical = candidate("dual", 0, "dual", bm25_score=5.0, bm25_rank=3)
    both_dense = candidate("both", 0, "both", dense_score=0.7, dense_rank=1)
    both_lexical = candidate("both", 0, "both", bm25_score=4.0, bm25_rank=2)
    pool = build_candidate_pool(
        arm="B",
        dense_candidates=[dense, both_dense],
        bm25_candidates=[lexical, both_lexical],
    )
    reciprocal_rank_fusion(pool)
    by_document = {item.document_id: item for item in pool}
    assert by_document["doc-dual"].fusion_score == pytest.approx(1 / (RRF_CONSTANT + 3))
    assert by_document["doc-both"].fusion_score == pytest.approx(
        1 / (RRF_CONSTANT + 1) + 1 / (RRF_CONSTANT + 2)
    )


def test_rrf_tie_break_prefers_dense_then_bm25_then_stable_identity():
    dense_first = candidate("z-dense", 0, "dense", dense_score=0.8, dense_rank=1)
    bm_first = candidate("a-bm", 0, "bm", bm25_score=8.0, bm25_rank=1)
    pool = build_candidate_pool(
        arm="B", dense_candidates=[dense_first], bm25_candidates=[bm_first]
    )
    ordered = reciprocal_rank_fusion(pool)
    assert [item.document_id for item in ordered] == ["doc-z-dense", "doc-a-bm"]


def test_union_dedup_and_fused_top18_cap_are_exact():
    dense = [
        candidate(f"dense-{rank:02}", 0, f"dense {rank}", dense_score=0.9, dense_rank=rank)
        for rank in range(1, 19)
    ]
    bm25 = [
        candidate(f"bm-{rank:02}", 0, f"bm {rank}", bm25_score=10.0 - rank, bm25_rank=rank)
        for rank in range(1, 19)
    ]
    pool = build_candidate_pool(arm="B", dense_candidates=dense, bm25_candidates=bm25)
    assert len(pool) == 36
    fused = reciprocal_rank_fusion(pool)
    assert len(fused) == FUSED_LIMIT == 18
    assert sum(item.rejection_reason == "fused_top18_cutoff" for item in pool) == 18
    assert all(item.candidate_admitted for item in fused)


def test_reranker_revision_model_and_token_contract_are_exact():
    assert RERANKER_MODEL_ID == "BAAI/bge-reranker-v2-m3"
    assert RERANKER_REVISION == "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
    assert RERANKER_TOKEN_CAP == 1024


def test_pair_budget_preserves_query_and_truncates_only_chunk_tail():
    query = list(range(100))
    chunk = list(range(2000, 4000))
    pair = enforce_pair_token_budget(query, chunk, special_token_count=4)
    assert pair.query_token_ids == tuple(query)
    assert pair.chunk_token_ids == tuple(chunk[:920])
    assert pair.truncated is True
    assert pair.total_tokens == 1024
    with pytest.raises(ContractViolation, match="query alone"):
        enforce_pair_token_budget(list(range(1021)), [1], special_token_count=4)


class FrozenXlmRobertaTokenizerFixture:
    bos_token_id = 0
    eos_token_id = 2

    @staticmethod
    def num_special_tokens_to_add(*, pair: bool) -> int:
        assert pair is True
        return 4


def test_xlm_roberta_pair_assembly_matches_frozen_boundary_template():
    pair = enforce_pair_token_budget([41, 1294], [7839, 92], special_token_count=4)
    feature = build_xlm_roberta_pair_feature(FrozenXlmRobertaTokenizerFixture(), pair)
    assert feature == {
        "input_ids": [0, 41, 1294, 2, 2, 7839, 92, 2],
        "attention_mask": [1] * 8,
    }


class FakeReranker:
    model_id = RERANKER_MODEL_ID
    revision = RERANKER_REVISION

    def __init__(self, scores: dict[str, float] | None = None):
        self.scores = scores or {}
        self.seen: list[list[str]] = []

    def score(self, query: str, candidates: list[Candidate]):
        self.seen.append(candidate_order(candidates))
        return [
            RerankObservation(
                raw_logit=self.scores.get(item.identity, 0.0),
                truncated=False,
                input_tokens=10,
            )
            for item in candidates
        ]


def test_reranker_uses_raw_logit_and_ties_by_upstream_rank_then_identity():
    first = candidate("first", 0, "first", arm="C", dense_score=0.8, dense_rank=1)
    second = candidate("second", 0, "second", arm="C", dense_score=0.7, dense_rank=2)
    pool = build_candidate_pool(arm="C", dense_candidates=[first, second])
    scores = {pool[0].identity: -2.0, pool[1].identity: 3.0}
    ordered = apply_reranker(query="q", candidates=pool, reranker=FakeReranker(scores))
    assert [item.reranker_score for item in ordered] == [3.0, -2.0]
    tied = apply_reranker(query="q", candidates=pool, reranker=FakeReranker())
    assert [item.dense_rank for item in tied] == [1, 2]


class InMemoryDenseAdapter:
    def __init__(self, query: str, candidates: list[Candidate]):
        self.query = query
        self.candidates = candidates

    def retrieve(self, case_id: str, *, arm: str):
        return self.query, [replace_candidate(item, arm) for item in self.candidates]


def replace_candidate(value: Candidate, arm: str) -> Candidate:
    chunk = CorpusChunk(
        identity=value.identity,
        document_id=value.document_id,
        chunk_index=value.chunk_index,
        content_hash=value.content_hash,
        filename=value.filename,
        page_number=value.page_number,
        section_title=value.section_title,
        raw_text=value.raw_text,
        material_id=value.material_id,
        chunk_id=value.chunk_id,
        evidence_ids=value.evidence_ids,
    )
    result = Candidate.from_chunk(chunk, arm)
    result.dense_score = value.dense_score
    result.dense_rank = value.dense_rank
    return result


def test_c_reranker_input_excludes_dense_ineligible_and_never_pads_rank19():
    dense = [
        candidate(
            f"c-{rank:02}",
            0,
            f"chunk {rank}",
            arm="C",
            dense_score=0.5 if rank <= 12 else 0.3,
            dense_rank=rank,
            material_id=rank,
        )
        for rank in range(1, 19)
    ]
    reranker = FakeReranker()
    execution = execute_arm(
        arm="C",
        case_id="fixture",
        dense_adapter=InMemoryDenseAdapter("query", dense),
        bm25_index=None,
        reranker=reranker,
    )
    assert execution.pair_count == 12
    assert len(reranker.seen[0]) == 12
    assert {item.dense_rank for item in execution.ordered_for_governance} == set(range(1, 13))
    assert all(item.dense_rank <= 18 for item in execution.pool if item.dense_rank is not None)


def test_d_reranker_receives_only_fused_admitted_top18():
    dense = [
        candidate(
            f"d-{rank:02}", 0, f"dense {rank}", dense_score=0.8, dense_rank=rank
        )
        for rank in range(1, 19)
    ]
    corpus = tuple(make_chunk(f"bm-{rank:02}", 0, f"lexical {rank}") for rank in range(1, 19))
    bm25 = FrozenBM25Index(corpus)
    reranker = FakeReranker()
    execution = execute_arm(
        arm="D",
        case_id="fixture",
        dense_adapter=InMemoryDenseAdapter("unmatched query", dense),
        bm25_index=bm25,
        reranker=reranker,
    )
    assert execution.pair_count == 18
    assert len(reranker.seen[0]) == 18
    assert all(item.candidate_admitted for item in execution.ordered_for_governance)
    assert all(item.fusion_rank <= 18 for item in execution.ordered_for_governance)


def test_governance_exactly_reconstructs_all_frozen_a_selected_identity_order(
    dense_adapter: FrozenDenseTraceAdapter,
):
    for case_id in dense_adapter.cases:
        _, dense = dense_adapter.retrieve(case_id, arm="C")
        pool = build_candidate_pool(arm="C", dense_candidates=dense)
        ordered = sorted(
            (item for item in pool if item.candidate_admitted),
            key=lambda item: (item.dense_rank, item.identity),
        )
        selected = govern_evidence(ordered)
        observed = [(item.chunk_id, item.material_id, item.chunk_index) for item in selected]
        expected = [
            (item["chunk_id"], item["material_id"], item["chunk_index"])
            for item in dense_adapter.reference_selected(case_id)
        ]
        assert observed == expected, case_id


def test_reconstructed_evidence_annotation_matches_frozen_dense_diagnostics(
    dense_adapter: FrozenDenseTraceAdapter,
):
    for case_id in dense_adapter.cases:
        _, dense = dense_adapter.retrieve(case_id, arm="C")
        expected = dense_adapter.reference_candidates(case_id)
        assert [list(item.evidence_ids) for item in dense] == [
            item["evidence_ids"] for item in expected
        ], case_id


def test_arm_state_isolation_with_fresh_bm25_adapters(frozen_corpus: FrozenCorpus, dense_adapter):
    case_id = next(iter(dense_adapter.cases))
    left = execute_arm(
        arm="B",
        case_id=case_id,
        dense_adapter=dense_adapter,
        bm25_index=FrozenBM25Index(frozen_corpus.chunks),
        reranker=None,
    )
    right = execute_arm(
        arm="B",
        case_id=case_id,
        dense_adapter=dense_adapter,
        bm25_index=FrozenBM25Index(frozen_corpus.chunks),
        reranker=None,
    )
    assert candidate_order(left.pool) == candidate_order(right.pool)
    assert candidate_order(left.ordered_for_governance) == candidate_order(
        right.ordered_for_governance
    )
    assert candidate_order(left.selected) == candidate_order(right.selected)
    assert all(a is not b for a, b in zip(left.pool, right.pool, strict=True))


def test_candidate_score_provenance_schema_and_rejection_vocabulary(frozen_corpus):
    sample = Candidate.from_chunk(frozen_corpus.chunks[0], "B")
    schema = json.loads((PHASE / "candidate_trace.schema.json").read_text(encoding="utf-8"))
    assert json_schema_errors(sample.to_dict(), schema) == []
    assert REJECTION_REASONS == (
        "dense_ineligible",
        "not_admitted",
        "fused_top18_cutoff",
        "overlap_dedup",
        "diversity_deferred",
        "final_top_k",
        "context_budget",
        "empty_content",
    )


def test_zero_llm_surface_and_arm_a_execution_guard(frozen_corpus, dense_adapter):
    source = (PHASE / "experiment.py").read_text(encoding="utf-8").casefold()
    assert "generate_structured" not in source
    assert "deepseek" not in source
    assert "openai" not in source
    with pytest.raises(ContractViolation, match="Arm A execution is forbidden"):
        execute_arm(
            arm="A",
            case_id=next(iter(dense_adapter.cases)),
            dense_adapter=dense_adapter,
            bm25_index=None,
            reranker=None,
        )


def test_design_v1_predecessor_and_all_frozen_production_hash_guards():
    assert digest(V1 / "ablation_design_v1_1/ablation_design_manifest.json") == (
        ABLATION_DESIGN_SHA256
    )
    assert digest(V1 / "ablation_design_v1/ablation_design_manifest.json") == (
        V1_DESIGN_SHA256
    )
    failure = json.loads(
        (V1 / "failure_analysis_v1/failure_analysis_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    historical = failure["frozen_bindings"]["production_code"]
    production = json.loads(POST_C_PRODUCTION.read_text(encoding="utf-8"))
    assert historical["all_match"] is True
    assert production["strict_equality_required"] is True
    assert production["hash_algorithm"] == "SHA-256"
    assert production["file_count"] == len(production["baseline_sha256"]) == 15
    assert set(production["baseline_sha256"]) == set(historical["baseline_sha256"])
    for relative_path, expected_hash in production["baseline_sha256"].items():
        assert digest(ROOT / relative_path) == expected_hash


def test_all_frozen_parameters_remain_exact():
    assert DENSE_THRESHOLD == 0.35
    assert (BM25_K1, BM25_B, BM25_EPSILON) == (1.5, 0.75, 0.25)
    assert RRF_CONSTANT == 60
    assert FUSED_LIMIT == 18
