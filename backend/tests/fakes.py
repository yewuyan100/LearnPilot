from hashlib import sha256

import numpy as np

from app.services.embedding.base import EmbeddingError, FloatMatrix


class FakeEmbedder:
    model_name = "fake/bge-m3"
    model_revision = "test"
    normalized = True

    def __init__(self, dimension: int = 16):
        self._dimension = dimension
        self.calls = 0

    @property
    def dimension(self) -> int:
        return self._dimension

    def _vector(self, text: str) -> np.ndarray:
        if not text.strip():
            raise EmbeddingError("不能对空文本生成 Embedding。")
        vector = np.zeros(self.dimension, dtype=np.float32)
        compact = "".join(text.lower().split())
        for index, character in enumerate(compact):
            digest = sha256(f"{index % 3}:{character}".encode("utf-8")).digest()
            vector[int.from_bytes(digest[:2], "little") % self.dimension] += 1.0
        norm = np.linalg.norm(vector)
        if norm:
            vector /= norm
        return vector

    def embed_documents(self, texts: list[str]) -> FloatMatrix:
        self.calls += 1
        return np.stack([self._vector(text) for text in texts]).astype(np.float32)

    def embed_query(self, query: str) -> FloatMatrix:
        self.calls += 1
        return self._vector(query).reshape(1, -1).astype(np.float32)
