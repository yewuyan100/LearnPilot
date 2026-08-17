from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


NoteType = Literal["quick", "study", "course", "knowledge_point", "material", "reflection"]
NoteStatus = Literal["active", "archived"]


class NoteLinkCreate(BaseModel):
    entity_type: str = Field(min_length=1, max_length=48)
    entity_id: int = Field(gt=0)
    relation_type: str = Field(default="context", min_length=1, max_length=48)


class NoteSourceCreate(BaseModel):
    material_id: int = Field(gt=0)
    chunk_id: int | None = Field(default=None, gt=0)
    source_title: str | None = Field(default=None, max_length=500)
    source_locator: str | None = Field(default=None, max_length=500)
    quoted_text: str = Field(min_length=1, max_length=12000)


class NoteCreate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    content_markdown: str = Field(default="", max_length=200000)
    note_type: NoteType = "quick"
    is_pinned: bool = False
    tags: list[str] = Field(default_factory=list, max_length=30)
    links: list[NoteLinkCreate] = Field(default_factory=list, max_length=30)
    sources: list[NoteSourceCreate] = Field(default_factory=list, max_length=30)


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    content_markdown: str | None = Field(default=None, max_length=200000)
    note_type: NoteType | None = None
    status: NoteStatus | None = None
    is_pinned: bool | None = None
    tags: list[str] | None = Field(default=None, max_length=30)


class NoteLinkRead(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    relation_type: str
    entity_title: str
    source_available: bool
    created_at: datetime


class NoteSourceRead(BaseModel):
    id: int
    material_id: int | None
    chunk_id: int | None
    source_title: str
    source_locator: str | None
    quoted_text: str
    source_available: bool
    created_at: datetime


class NoteRead(BaseModel):
    id: int
    title: str
    content_markdown: str
    note_type: str
    status: str
    is_pinned: bool
    archived_at: datetime | None
    tags: list[str]
    links: list[NoteLinkRead]
    sources: list[NoteSourceRead]
    created_at: datetime
    updated_at: datetime


class NotePage(BaseModel):
    items: list[NoteRead]
    total: int
    page: int
    page_size: int
    pages: int
