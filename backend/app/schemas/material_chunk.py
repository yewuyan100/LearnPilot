from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import Timestamped


class MaterialChunkRead(Timestamped):
    material_id: int
    chunk_index: int
    content: str
    char_count: int
    content_hash: str
    page_number: int | None
    section_title: str | None


class MaterialChunkPage(BaseModel):
    items: list[MaterialChunkRead]
    total: int
    page: int
    page_size: int
    pages: int


class MaterialSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1)
    material_ids: list[int] | None = None
    min_score: float | None = Field(default=None, ge=-1.0, le=1.0)


class MaterialSearchResult(BaseModel):
    rank: int
    score: float
    chunk_id: int
    material_id: int
    original_filename: str
    chunk_index: int
    content: str
    page_number: int | None
    section_title: str | None


class MaterialSearchResponse(BaseModel):
    query: str
    model_name: str
    index_version: str
    results: list[MaterialSearchResult]
    duration_ms: int
    retrieved_count: int = 0
    filtered_count: int = 0


class MaterialIndexStatus(BaseModel):
    available: bool
    building: bool
    model_name: str
    embedding_dimension: int | None
    chunk_count: int
    built_at: datetime | None
    index_version: str | None
    stale: bool
    error_message: str | None


class MaterialIndexBuildResult(BaseModel):
    index_version: str | None
    chunk_count: int
    model_name: str
    embedding_dimension: int | None
    built_at: datetime | None
