from pathlib import Path

import numpy as np
import pytest
import sentence_transformers

from app.services.embedding.base import EmbeddingError
from app.services.embedding.bge_m3 import BgeM3Embedder
from tests.fakes import FakeEmbedder


def test_fake_embedder_documents_query_dtype_and_normalization():
    embedder = FakeEmbedder()
    documents = embedder.embed_documents(["MCP tools", "MCP resources"])
    query = embedder.embed_query("MCP tools")

    assert documents.shape == (2, embedder.dimension)
    assert query.shape == (1, embedder.dimension)
    assert documents.dtype == np.float32
    assert np.allclose(np.linalg.norm(documents, axis=1), 1.0)


def test_fake_embedder_rejects_empty_text():
    with pytest.raises(EmbeddingError):
        FakeEmbedder().embed_documents([""])


def test_bge_embedder_loads_model_once_and_honors_device(monkeypatch, tmp_path: Path):
    calls: list[dict] = []

    class FakeModel:
        def __init__(self, model_name, **kwargs):
            calls.append({"model_name": model_name, **kwargs})

        def get_sentence_embedding_dimension(self):
            return 4

        def encode(self, texts, **kwargs):
            return np.array([[1, 0, 0, 0] for _ in texts], dtype=np.float32)

    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", FakeModel)
    embedder = BgeM3Embedder(
        model_name="BAAI/bge-m3",
        model_revision="local-cache",
        cache_folder=tmp_path,
        local_files_only=True,
        device="cpu",
        batch_size=2,
        normalized=True,
    )
    embedder.embed_documents(["one", "two"])
    embedder.embed_query("one")

    assert len(calls) == 1
    assert calls[0]["local_files_only"] is True
    assert calls[0]["device"] == "cpu"
    assert calls[0]["cache_folder"] == str(tmp_path)


def test_bge_embedder_reports_missing_local_model(monkeypatch):
    def missing(*args, **kwargs):
        raise OSError("not cached")

    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", missing)
    embedder = BgeM3Embedder(
        model_name="missing/model",
        model_revision="local-cache",
        cache_folder=None,
        local_files_only=True,
        device="cpu",
        batch_size=1,
        normalized=True,
    )
    with pytest.raises(EmbeddingError, match="HF_HOME"):
        _ = embedder.dimension


def test_bge_embedder_rejects_unexpected_output_dimension(monkeypatch):
    class WrongDimensionModel:
        def __init__(self, *args, **kwargs):
            pass

        def get_sentence_embedding_dimension(self):
            return 4

        def encode(self, texts, **kwargs):
            return np.ones((len(texts), 3), dtype=np.float32)

    monkeypatch.setattr(
        sentence_transformers,
        "SentenceTransformer",
        WrongDimensionModel,
    )
    embedder = BgeM3Embedder(
        model_name="fake/model",
        model_revision="test",
        cache_folder=None,
        local_files_only=True,
        device="cpu",
        batch_size=2,
        normalized=True,
    )

    with pytest.raises(EmbeddingError, match="维度"):
        embedder.embed_documents(["one"])
