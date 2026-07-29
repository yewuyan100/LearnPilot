import re
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models.material import Material


MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
}


def safe_display_name(filename: str) -> str:
    name = Path(filename).name.replace("\x00", "").strip()
    name = re.sub(r"[\r\n\t]", " ", name)
    return name[:255] or "未命名资料"


async def save_upload(db: Session, upload: UploadFile, settings: Settings) -> Material:
    original_name = safe_display_name(upload.filename or "")
    extension = Path(original_name).suffix.lower()
    if extension not in settings.allowed_file_extensions:
        raise AppError(
            "unsupported_file_type",
            f"不支持 {extension or '未知'} 文件，仅允许 PDF、Markdown 和 TXT",
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{extension}"
    path = settings.upload_dir / stored_name
    size = 0
    try:
        with path.open("wb") as destination:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_size_bytes:
                    raise AppError(
                        "file_too_large",
                        f"文件超过 {settings.max_upload_size_mb} MB 限制",
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    )
                destination.write(chunk)
        if size == 0:
            raise AppError("empty_file", "不能上传空文件", status.HTTP_422_UNPROCESSABLE_ENTITY)

        material = Material(
            title=Path(original_name).stem[:255],
            original_filename=original_name,
            stored_filename=stored_name,
            file_path=str(path.resolve()),
            source_type=extension.removeprefix("."),
            mime_type=MIME_BY_EXTENSION[extension],
            file_size=size,
            processing_status="ready",
        )
        db.add(material)
        db.commit()
        db.refresh(material)
        return material
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


def delete_material_file(material: Material) -> None:
    Path(material.file_path).unlink(missing_ok=True)

