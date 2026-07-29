from datetime import datetime
from hashlib import sha256

from pydantic import BaseModel

from app.models.material_chunk import MaterialChunk


class FaissManifest(BaseModel):
    schema_version: int = 1
    index_version: str
    model_name: str
    model_revision: str
    embedding_dimension: int
    normalized: bool
    distance_metric: str = "inner_product"
    chunk_count: int
    chunk_ids: list[int]
    built_at: datetime
    content_checksum: str
    index_checksum: str | None = None


def chunks_checksum(chunks: list[MaterialChunk]) -> str:
    payload = "\n".join(
        f"{chunk.id}:{chunk.material_id}:{chunk.content_hash}" for chunk in chunks
    )
    return sha256(payload.encode("utf-8")).hexdigest()
