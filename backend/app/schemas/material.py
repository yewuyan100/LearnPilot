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
    error_message: str | None

