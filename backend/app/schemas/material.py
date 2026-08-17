from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import Timestamped


class MaterialRead(Timestamped):
    title: str
    original_filename: str
    stored_filename: str
    file_path: str
    source_type: str
    mime_type: str
    file_size: int
    processing_status: str
    ingestion_status: str
    indexing_status: str
    chunk_count: int
    indexed_chunk_count: int
    processed_at: datetime | None
    indexed_at: datetime | None
    archived_at: datetime | None
    error_message: str | None
    deletion_status: str
    deletion_error: str | None
    deletion_requested_at: datetime | None
    deletion_attempts: int


class MaterialArchiveBulkRequest(BaseModel):
    material_ids: list[int] = Field(min_length=1, max_length=100)


class MaterialArchiveBulkResult(BaseModel):
    archived_ids: list[int]
