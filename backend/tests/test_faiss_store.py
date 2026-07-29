from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from app.services.vector_store.faiss_store import FaissStore, VectorStoreError
from app.services.vector_store.manifest import FaissManifest


def manifest() -> FaissManifest:
    return FaissManifest(
        index_version="v-test",
        model_name="fake/bge-m3",
        model_revision="test",
        embedding_dimension=3,
        normalized=True,
        chunk_count=2,
        chunk_ids=[11, 22],
        built_at=datetime.now(timezone.utc),
        content_checksum="content",
    )


def vectors() -> np.ndarray:
    return np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)


def test_faiss_build_save_load_search_and_manifest(tmp_path: Path):
    store = FaissStore(tmp_path / "index.faiss", tmp_path / "manifest.json")
    saved = store.save(vectors(), manifest())
    index, loaded = store.load(model_name="fake/bge-m3", normalized=True)
    hits, searched = store.search(
        np.array([[1, 0, 0]], dtype=np.float32),
        2,
        model_name="fake/bge-m3",
        normalized=True,
    )

    assert index.ntotal == 2
    assert loaded == saved
    assert [hit.chunk_id for hit in hits] == [11, 22]
    assert searched.index_checksum


@pytest.mark.parametrize("target", ["index", "manifest"])
def test_faiss_rejects_corrupted_files(tmp_path: Path, target: str):
    store = FaissStore(tmp_path / "index.faiss", tmp_path / "manifest.json")
    store.save(vectors(), manifest())
    path = store.index_path if target == "index" else store.manifest_path
    path.write_bytes(b"corrupted")
    with pytest.raises(VectorStoreError, match="损坏|校验"):
        store.load(model_name="fake/bge-m3", normalized=True)


def test_faiss_rejects_model_and_dimension_mismatch(tmp_path: Path):
    store = FaissStore(tmp_path / "index.faiss", tmp_path / "manifest.json")
    store.save(vectors(), manifest())
    with pytest.raises(VectorStoreError, match="配置"):
        store.load(model_name="other/model", normalized=True)
    with pytest.raises(VectorStoreError, match="配置"):
        store.load(
            model_name="fake/bge-m3",
            model_revision="other-revision",
            normalized=True,
        )
    with pytest.raises(VectorStoreError, match="维度"):
        store.load(
            model_name="fake/bge-m3",
            normalized=True,
            embedding_dimension=4,
        )


def test_failed_rebuild_keeps_previous_index(tmp_path: Path):
    store = FaissStore(tmp_path / "index.faiss", tmp_path / "manifest.json")
    original = store.save(vectors(), manifest())
    with pytest.raises(VectorStoreError):
        store.save(np.zeros((1, 4), dtype=np.float32), manifest())
    _, loaded = store.load(model_name="fake/bge-m3", normalized=True)
    assert loaded.index_version == original.index_version
