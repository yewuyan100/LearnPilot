from functools import lru_cache

from app.core.config import Settings
from app.services.embedding.base import Embedder
from app.services.embedding.bge_m3 import BgeM3Embedder


@lru_cache(maxsize=4)
def _cached_embedder(
    model_name: str,
    model_revision: str,
    cache_folder: str | None,
    local_files_only: bool,
    device: str,
    batch_size: int,
    normalized: bool,
) -> BgeM3Embedder:
    from pathlib import Path

    return BgeM3Embedder(
        model_name=model_name,
        model_revision=model_revision,
        cache_folder=Path(cache_folder) if cache_folder else None,
        local_files_only=local_files_only,
        device=device,
        batch_size=batch_size,
        normalized=normalized,
    )


def build_embedder(settings: Settings) -> Embedder:
    return _cached_embedder(
        settings.embedding_model_name,
        settings.embedding_model_revision,
        str(settings.hf_home) if settings.hf_home else None,
        settings.embedding_local_files_only,
        settings.embedding_device,
        settings.embedding_batch_size,
        settings.embedding_normalize,
    )
