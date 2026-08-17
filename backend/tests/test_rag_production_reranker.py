from pathlib import Path

import pytest

from app.core.config import Settings
from app.schemas.material_chunk import MaterialSearchResponse, MaterialSearchResult
from app.schemas.rag import RagRetrievalSummary
from app.services.rag.reranker import (
    RerankBatch,
    RerankCandidate,
    RerankerProvider,
    RerankerUnavailable,
    RerankScore,
    build_reranker_provider,
)
from app.services.rag.retrieval import retrieve_sources


class ReverseReranker:
    device = "cuda:0"
    dtype = "float32"

    def __init__(self):
        self.calls = 0
        self.candidate_counts = []

    def rerank(self, query, candidates):  # noqa: ANN001
        self.calls += 1
        self.candidate_counts.append(len(candidates))
        ordered = list(reversed(candidates))
        return RerankBatch(
            scores=tuple(
                RerankScore(
                    identity=item.identity,
                    dense_rank=item.dense_rank,
                    rank=rank,
                    raw_logit=float(len(ordered) - rank),
                    truncated=False,
                    input_tokens=10,
                )
                for rank, item in enumerate(ordered, start=1)
            ),
            pair_count=len(candidates),
            batch_count=1,
            device=self.device,
            dtype=self.dtype,
        )


class FailingReranker:
    device = "cuda:0"
    dtype = "float32"

    def rerank(self, query, candidates):  # noqa: ANN001
        raise RerankerUnavailable("inference_failed")


def reranker_settings(**updates) -> Settings:
    values = {
        "rag_reranker_enabled": True,
        "rag_reranker_model_path": Path(
            "C:/models/953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
        ),
        "rag_reranker_device": "cuda",
        "rag_final_context_top_k": 7,
    }
    values.update(updates)
    return Settings(_env_file=None, **values)


def search_results(count: int = 18) -> list[MaterialSearchResult]:
    return [
        MaterialSearchResult(
            rank=index,
            score=1.0 - index / 100,
            chunk_id=index,
            material_id=index,
            original_filename=f"doc-{index}.md",
            chunk_index=0,
            content=f"independent candidate {index}",
            page_number=None,
            section_title=f"Section {index}",
        )
        for index in range(1, count + 1)
    ]


def install_search(monkeypatch, results):  # noqa: ANN001
    def fake_search(self, **kwargs):  # noqa: ANN001
        assert kwargs["top_k"] == 18
        return MaterialSearchResponse(
            query=kwargs["query"],
            model_name="fake-dense",
            index_version="index-v1",
            results=results,
            duration_ms=4,
            retrieved_count=len(results),
            filtered_count=0,
        )

    monkeypatch.setattr(
        "app.services.rag.retrieval.MaterialIndexService.search", fake_search
    )


def test_reranker_config_requires_path_and_cuda_device():
    with pytest.raises(ValueError, match="RAG_RERANKER_MODEL_PATH"):
        Settings(_env_file=None, rag_reranker_enabled=True)
    with pytest.raises(ValueError, match="RAG_RERANKER_DEVICE"):
        reranker_settings(rag_reranker_device="cpu")


def test_reranker_provider_loads_once_and_reuses_adapter():
    adapter = ReverseReranker()
    factory_calls = 0

    def factory():
        nonlocal factory_calls
        factory_calls += 1
        return adapter

    provider = RerankerProvider(factory)
    candidates = [RerankCandidate("one", 1, "one")]
    provider.rerank("query", candidates)
    provider.rerank("query", candidates)

    assert factory_calls == 1
    assert provider.status().load_count == 1
    assert provider.status().load_attempt_count == 1
    assert provider.status().inference_count == 2


def test_reranker_provider_does_not_retry_failed_initialization():
    factory_calls = 0

    def factory():
        nonlocal factory_calls
        factory_calls += 1
        raise RerankerUnavailable("cuda_unavailable")

    provider = RerankerProvider(factory)
    for _ in range(2):
        with pytest.raises(RerankerUnavailable, match="cuda_unavailable"):
            provider.rerank("query", [RerankCandidate("one", 1, "one")])

    assert factory_calls == 1
    assert provider.status().load_count == 0
    assert provider.status().load_attempt_count == 1
    assert provider.status().state == "degraded"


def test_production_retrieval_runs_reranker_before_existing_governance(monkeypatch):
    results = search_results()
    install_search(monkeypatch, results)
    adapter = ReverseReranker()
    provider = RerankerProvider(lambda: adapter)

    outcome = retrieve_sources(
        db=object(),
        settings=reranker_settings(),
        embedder=object(),
        query="question",
        top_k=7,
        material_ids=None,
        reranker_provider=provider,
    )

    assert outcome.candidate_count == 18
    assert [source.chunk_id for source in outcome.sources] == [18, 17, 16, 15, 14, 13, 12]
    assert adapter.candidate_counts == [18]
    assert outcome.final_count == 7
    assert outcome.retrieval_mode == "dense_rerank"
    assert outcome.reranker_status == "active"
    assert outcome.reranker_device == "cuda:0"
    assert outcome.reranker_dtype == "float32"
    assert outcome.reranker_batch_count == 1


def test_production_retrieval_falls_back_to_dense_and_does_not_reload(monkeypatch):
    results = search_results()
    install_search(monkeypatch, results)
    provider = RerankerProvider(FailingReranker)

    outcomes = [
        retrieve_sources(
            db=object(),
            settings=reranker_settings(),
            embedder=object(),
            query="question",
            top_k=7,
            material_ids=None,
            reranker_provider=provider,
        )
        for _ in range(2)
    ]

    assert all(
        [source.chunk_id for source in outcome.sources] == [1, 2, 3, 4, 5, 6, 7]
        for outcome in outcomes
    )
    assert all(outcome.retrieval_mode == "dense_fallback" for outcome in outcomes)
    assert all(outcome.reranker_status == "degraded" for outcome in outcomes)
    assert all(
        outcome.reranker_fallback_reason == "inference_failed"
        for outcome in outcomes
    )
    assert provider.status().load_count == 1
    assert provider.status().load_attempt_count == 1


def test_build_reranker_provider_is_process_singleton():
    settings = reranker_settings()
    assert build_reranker_provider(settings) is build_reranker_provider(settings)


def test_retrieval_summary_exposes_reranker_metadata():
    summary = RagRetrievalSummary(
        query="q",
        top_k=6,
        candidate_count=18,
        source_count=6,
        min_score=0.35,
        index_version="v1",
        duration_ms=4,
        retrieval_mode="dense_fallback",
        reranker_status="degraded",
        reranker_fallback_reason="cuda_unavailable",
    )
    payload = summary.model_dump()

    assert payload["retrieval_mode"] == "dense_fallback"
    assert payload["reranker_status"] == "degraded"
    assert payload["reranker_fallback_reason"] == "cuda_unavailable"
