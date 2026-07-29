from typing import Protocol

import numpy as np
from numpy.typing import NDArray


FloatMatrix = NDArray[np.float32]


class EmbeddingError(RuntimeError):
    """A user-readable local embedding configuration or execution failure."""


class Embedder(Protocol):
    model_name: str
    model_revision: str
    normalized: bool

    @property
    def dimension(self) -> int: ...

    def embed_documents(self, texts: list[str]) -> FloatMatrix: ...

    def embed_query(self, query: str) -> FloatMatrix: ...
