from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import shutil
from uuid import uuid4

import numpy as np

from app.services.vector_store.base import VectorSearchHit
from app.services.vector_store.manifest import FaissManifest


logger = logging.getLogger("personal_learning.vector_store")


class VectorStoreError(RuntimeError):
    """A user-readable FAISS index or manifest failure."""


class FaissStore:
    def __init__(self, index_path: Path, manifest_path: Path):
        self.index_path = index_path
        self.manifest_path = manifest_path

    @staticmethod
    def _faiss():
        try:
            import faiss

            return faiss
        except Exception as exc:
            raise VectorStoreError("FAISS 未正确安装，无法使用本地向量索引。") from exc

    def exists(self) -> bool:
        return self.index_path.is_file() and self.manifest_path.is_file()

    def clear(self) -> None:
        self.index_path.unlink(missing_ok=True)
        self.manifest_path.unlink(missing_ok=True)

    def read_manifest(self) -> FaissManifest | None:
        if not self.index_path.exists() and not self.manifest_path.exists():
            return None
        if not self.index_path.is_file() or not self.manifest_path.is_file():
            raise VectorStoreError("FAISS 索引与 Manifest 不完整，需要重新构建。")
        try:
            return FaissManifest.model_validate_json(
                self.manifest_path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            raise VectorStoreError("FAISS Manifest 损坏，需要重新构建。") from exc

    def load(
        self,
        *,
        model_name: str,
        normalized: bool,
        model_revision: str | None = None,
        embedding_dimension: int | None = None,
    ):
        manifest = self.read_manifest()
        if manifest is None:
            return None, None
        if (
            manifest.model_name != model_name
            or manifest.normalized != normalized
            or (
                model_revision is not None
                and manifest.model_revision != model_revision
            )
        ):
            raise VectorStoreError("Embedding 配置已变化，FAISS 索引需要重新构建。")
        if (
            embedding_dimension is not None
            and manifest.embedding_dimension != embedding_dimension
        ):
            raise VectorStoreError("Embedding 维度已变化，FAISS 索引需要重新构建。")
        try:
            if manifest.index_checksum:
                actual = sha256(self.index_path.read_bytes()).hexdigest()
                if actual != manifest.index_checksum:
                    raise VectorStoreError("FAISS 索引校验失败，需要重新构建。")
            index = self._faiss().read_index(str(self.index_path))
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError("FAISS 索引文件损坏，需要重新构建。") from exc
        if index.ntotal != manifest.chunk_count:
            raise VectorStoreError("FAISS 索引数量与 Manifest 不一致，需要重新构建。")
        if index.d != manifest.embedding_dimension:
            raise VectorStoreError("FAISS 索引维度与 Manifest 不一致，需要重新构建。")
        if len(manifest.chunk_ids) != manifest.chunk_count:
            raise VectorStoreError("FAISS Chunk ID 映射不完整，需要重新构建。")
        return index, manifest

    def save(
        self,
        vectors: np.ndarray,
        manifest: FaissManifest,
    ) -> FaissManifest:
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[0] != len(manifest.chunk_ids):
            raise VectorStoreError("向量数量与 Chunk ID 数量不一致。")
        if vectors.shape[1] != manifest.embedding_dimension:
            raise VectorStoreError("向量维度与 Manifest 不一致。")

        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        suffix = uuid4().hex
        temp_index = self.index_path.with_name(f"{self.index_path.name}.{suffix}.tmp")
        temp_manifest = self.manifest_path.with_name(
            f"{self.manifest_path.name}.{suffix}.tmp"
        )
        backup_index = self.index_path.with_name(f"{self.index_path.name}.{suffix}.bak")
        backup_manifest = self.manifest_path.with_name(
            f"{self.manifest_path.name}.{suffix}.bak"
        )
        had_index = self.index_path.is_file()
        had_manifest = self.manifest_path.is_file()
        try:
            faiss = self._faiss()
            index = faiss.IndexFlatIP(manifest.embedding_dimension)
            index.add(vectors)
            faiss.write_index(index, str(temp_index))
            saved_manifest = manifest.model_copy(
                update={"index_checksum": sha256(temp_index.read_bytes()).hexdigest()}
            )
            temp_manifest.write_text(
                saved_manifest.model_dump_json(indent=2),
                encoding="utf-8",
            )

            loaded_temp = faiss.read_index(str(temp_index))
            parsed_temp = FaissManifest.model_validate(
                json.loads(temp_manifest.read_text(encoding="utf-8"))
            )
            if (
                loaded_temp.ntotal != parsed_temp.chunk_count
                or loaded_temp.d != parsed_temp.embedding_dimension
            ):
                raise VectorStoreError("临时 FAISS 索引校验失败。")

            if had_index:
                shutil.copy2(self.index_path, backup_index)
            if had_manifest:
                shutil.copy2(self.manifest_path, backup_manifest)
            os.replace(temp_index, self.index_path)
            os.replace(temp_manifest, self.manifest_path)
            return saved_manifest
        except Exception:
            if had_index and backup_index.is_file():
                os.replace(backup_index, self.index_path)
            elif not had_index:
                self.index_path.unlink(missing_ok=True)
            if had_manifest and backup_manifest.is_file():
                os.replace(backup_manifest, self.manifest_path)
            elif not had_manifest:
                self.manifest_path.unlink(missing_ok=True)
            raise
        finally:
            for path in (temp_index, temp_manifest, backup_index, backup_manifest):
                path.unlink(missing_ok=True)

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int,
        *,
        model_name: str,
        model_revision: str | None = None,
        normalized: bool,
    ) -> tuple[list[VectorSearchHit], FaissManifest]:
        vector = np.asarray(query_vector, dtype=np.float32)
        if vector.ndim == 1:
            vector = vector.reshape(1, -1)
        index, manifest = self.load(
            model_name=model_name,
            model_revision=model_revision,
            normalized=normalized,
            embedding_dimension=vector.shape[1],
        )
        if index is None or manifest is None:
            raise VectorStoreError("尚未建立可用的资料索引。")
        limit = min(max(top_k, 1), manifest.chunk_count)
        scores, positions = index.search(vector, limit)
        hits: list[VectorSearchHit] = []
        for score, position in zip(scores[0], positions[0], strict=True):
            if position < 0 or position >= len(manifest.chunk_ids):
                logger.warning("invalid_faiss_position position=%s", int(position))
                continue
            hits.append(
                VectorSearchHit(
                    chunk_id=manifest.chunk_ids[int(position)],
                    score=float(score),
                )
            )
        return hits, manifest
