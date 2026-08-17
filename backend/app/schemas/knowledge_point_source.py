from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


KnowledgePointSourceType = Literal["material", "chunk", "manual_reference"]


class KnowledgePointSourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_id: int = Field(gt=0)
    material_chunk_id: int | None = Field(default=None, gt=0)
    source_type: KnowledgePointSourceType
    source_locator: str | None = Field(default=None, max_length=500)
    quoted_text: str | None = Field(default=None, max_length=4000)
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_source(self) -> "KnowledgePointSourceCreate":
        if self.source_type == "chunk" and self.material_chunk_id is None:
            raise ValueError("chunk sources require material_chunk_id")
        if self.source_type != "chunk" and self.material_chunk_id is not None:
            raise ValueError("material_chunk_id is only valid for chunk sources")
        for field_name in ("source_locator", "quoted_text", "note"):
            value = getattr(self, field_name)
            if value is not None:
                setattr(self, field_name, value.strip() or None)
        return self


class KnowledgePointSourceRead(BaseModel):
    id: int
    knowledge_point_id: int
    knowledge_point_title: str
    material_id: int
    material_title: str
    original_filename: str
    material_chunk_id: int | None
    chunk_index: int | None
    source_type: KnowledgePointSourceType
    source_locator: str | None
    quoted_text: str | None
    note: str | None
    source_available: bool
    context_url: str
    created_at: datetime
    updated_at: datetime


class SourceChunkRead(BaseModel):
    id: int
    material_id: int
    material_title: str
    chunk_index: int
    content: str
    page_number: int | None
    section_title: str | None
    source_locator: str
    previous_chunk_id: int | None
    next_chunk_id: int | None


class SourceChunkPage(BaseModel):
    items: list[SourceChunkRead]
    total: int
    page: int
    page_size: int
    pages: int
