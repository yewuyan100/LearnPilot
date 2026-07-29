import logging
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any

import numpy as np

from app.services.embedding.base import EmbeddingError, FloatMatrix


logger = logging.getLogger("personal_learning.embedding")


class BgeM3Embedder:
    def __init__(
        self,
        *,
        model_name: str,
        model_revision: str,
        cache_folder: Path | None,
        local_files_only: bool,
        device: str,
        batch_size: int,
        normalized: bool,
    ):
        self.model_name = model_name
        self.model_revision = model_revision
        self.cache_folder = cache_folder
        self.local_files_only = local_files_only
        self.device = device
        self.batch_size = batch_size
        self.normalized = normalized
        self._model: Any | None = None
        self._dimension: int | None = None
        self._load_lock = Lock()

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            try:
                from sentence_transformers import SentenceTransformer

                started = perf_counter()
                kwargs: dict[str, Any] = {
                    "local_files_only": self.local_files_only,
                    "device": self.device,
                }
                if self.cache_folder is not None:
                    # HF_HOME points at a root whose Hub cache lives in ``hub``.
                    # SentenceTransformer's cache_folder argument expects that
                    # Hub cache itself, so accept either convention.
                    hub_cache = self.cache_folder / "hub"
                    kwargs["cache_folder"] = str(
                        hub_cache if hub_cache.is_dir() else self.cache_folder
                    )
                if self.model_revision and self.model_revision != "local-cache":
                    kwargs["revision"] = self.model_revision
                self._model = SentenceTransformer(self.model_name, **kwargs)
                dimension_getter = getattr(
                    self._model,
                    "get_embedding_dimension",
                    self._model.get_sentence_embedding_dimension,
                )
                dimension = dimension_getter()
                if not dimension or dimension <= 0:
                    raise EmbeddingError("本地 Embedding 模型没有返回有效向量维度。")
                self._dimension = int(dimension)
                logger.info(
                    "embedding_model_loaded model=%s revision=%s device=%s "
                    "dimension=%s batch_size=%s duration_ms=%s",
                    self.model_name,
                    self.model_revision,
                    self.device,
                    self._dimension,
                    self.batch_size,
                    round((perf_counter() - started) * 1000),
                )
                return self._model
            except EmbeddingError:
                raise
            except Exception as exc:
                mode = "本地离线缓存" if self.local_files_only else "模型缓存"
                raise EmbeddingError(
                    f"无法从{mode}加载 {self.model_name}。请检查 HF_HOME、模型缓存和设备配置。"
                ) from exc

    @property
    def dimension(self) -> int:
        self._load()
        assert self._dimension is not None
        return self._dimension

    def _encode(self, texts: list[str]) -> FloatMatrix:
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingError("不能对空文本生成 Embedding。")
        model = self._load()
        started = perf_counter()
        try:
            vectors = model.encode(
                texts,
                batch_size=self.batch_size,
                convert_to_numpy=True,
                normalize_embeddings=self.normalized,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise EmbeddingError("本地 Embedding 编码失败，请查看后端日志。") from exc
        result = np.asarray(vectors, dtype=np.float32)
        if result.ndim == 1:
            result = result.reshape(1, -1)
        if result.shape != (len(texts), self.dimension):
            raise EmbeddingError(
                f"Embedding 输出维度不一致：期望 {self.dimension}，实际 {result.shape}。"
            )
        if self.normalized:
            norms = np.linalg.norm(result, axis=1, keepdims=True)
            if np.any(norms == 0):
                raise EmbeddingError("Embedding 返回了零向量。")
            result = (result / norms).astype(np.float32, copy=False)
        logger.info(
            "embedding_encoded model=%s text_count=%s dimension=%s batch_count=%s "
            "embedding_duration_ms=%s",
            self.model_name,
            len(texts),
            self.dimension,
            (len(texts) + self.batch_size - 1) // self.batch_size,
            round((perf_counter() - started) * 1000),
        )
        return result

    def embed_documents(self, texts: list[str]) -> FloatMatrix:
        return self._encode(texts)

    def embed_query(self, query: str) -> FloatMatrix:
        if not query.strip():
            raise EmbeddingError("检索问题不能为空。")
        return self._encode([query.strip()])
