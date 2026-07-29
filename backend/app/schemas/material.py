from datetime import datetime

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
    error_message: str | None
