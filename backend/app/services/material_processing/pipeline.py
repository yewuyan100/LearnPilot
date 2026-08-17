import logging
from pathlib import Path
from time import perf_counter

from fastapi import status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.clock import clock_from_settings
from app.core.errors import AppError
from app.models.material import Material
from app.models.material_chunk import MaterialChunk
from app.repositories.material_chunks import MaterialChunkRepository
from app.repositories.materials import MaterialRepository
from app.services.material_processing.chunking import chunk_sections
from app.services.material_processing.cleaning import clean_text
from app.services.material_processing.parsers import parser_for
from app.services.material_processing.types import MaterialProcessingError, ParsedSection
from app.services.material_state import touch_material


logger = logging.getLogger("personal_learning.material_processing")


class MaterialProcessingPipeline:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        self.clock = clock_from_settings(settings)
        self.materials = MaterialRepository(db)
        self.chunks = MaterialChunkRepository(db)

    def process(self, material_id: int) -> Material:
        material = self.materials.get(material_id)
        if material.ingestion_status == "processing":
            raise AppError(
                "material_processing",
                "该资料正在解析，请勿重复提交。",
                status.HTTP_409_CONFLICT,
            )

        material.ingestion_status = "processing"
        material.indexing_status = "pending"
        material.error_message = None
        touch_material(material, self.clock.now())
        self.db.commit()

        started = perf_counter()
        try:
            path = Path(material.file_path)
            if not path.is_file():
                raise MaterialProcessingError("原始资料文件不存在，无法处理。")
            parser = parser_for(path, material.source_type)
            document = parser.parse(path)
            cleaned_sections = [
                ParsedSection(
                    text=clean_text(
                        section.text,
                        repair_pdf_lines=document.parser_type == "pdf",
                    ),
                    source_order=section.source_order,
                    page_number=section.page_number,
                    section_title=section.section_title,
                )
                for section in document.sections
            ]
            cleaned_sections = [section for section in cleaned_sections if section.text]
            drafts = chunk_sections(
                cleaned_sections,
                chunk_size=self.settings.material_chunk_size,
                overlap=self.settings.material_chunk_overlap,
                min_chunk_size=self.settings.material_min_chunk_size,
            )
            if not drafts:
                raise MaterialProcessingError("资料清洗后没有可生成片段的正文。")

            rows = [
                MaterialChunk(
                    material_id=material.id,
                    chunk_index=draft.chunk_index,
                    content=draft.content,
                    char_count=draft.char_count,
                    content_hash=draft.content_hash,
                    page_number=draft.page_number,
                    section_title=draft.section_title,
                )
                for draft in drafts
            ]
            self.chunks.replace_for_material(material.id, rows)
            material.chunk_count = len(rows)
            material.indexed_chunk_count = 0
            material.ingestion_status = "completed"
            material.indexing_status = "pending"
            material.processed_at = self.clock.now()
            touch_material(material, material.processed_at)
            material.indexed_at = None
            material.error_message = None
            self.db.commit()
            self.db.refresh(material)
            logger.info(
                "material_processed material_id=%s filename=%s parser_type=%s "
                "page_count=%s cleaned_char_count=%s chunk_count=%s processing_duration_ms=%s",
                material.id,
                material.original_filename,
                document.parser_type,
                document.page_count,
                sum(len(section.text) for section in cleaned_sections),
                len(rows),
                round((perf_counter() - started) * 1000),
            )
            return material
        except Exception as exc:
            self.db.rollback()
            failed = self.materials.get(material_id)
            failed.ingestion_status = "failed"
            failed.indexing_status = "pending"
            failed.chunk_count = self.chunks.count_for_material(material_id)
            failed.error_message = (
                str(exc)
                if isinstance(exc, MaterialProcessingError)
                else "资料处理失败，请查看后端日志后重试。"
            )
            touch_material(failed, self.clock.now())
            self.db.commit()
            logger.exception(
                "material_processing_failed material_id=%s filename=%s error_type=%s",
                failed.id,
                failed.original_filename,
                type(exc).__name__,
            )
            if isinstance(exc, MaterialProcessingError):
                raise AppError(
                    "material_processing_failed",
                    str(exc),
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                ) from exc
            raise AppError(
                "material_processing_failed",
                failed.error_message,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ) from exc
