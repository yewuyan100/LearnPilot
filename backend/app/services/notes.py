from __future__ import annotations

import re
from math import ceil

from fastapi import status
from sqlalchemy import func, or_, select

from app.core.clock import Clock, clock_from_settings
from app.core.errors import AppError
from app.models import (
    Course,
    DailyTask,
    KnowledgePoint,
    LearningActivity,
    LearningGoal,
    LearningSession,
    Material,
    MaterialChunk,
    Note,
    NoteLink,
    NoteSource,
    NoteTag,
    RagMessage,
)
from app.schemas.note import (
    NoteCreate,
    NoteLinkCreate,
    NoteLinkRead,
    NotePage,
    NoteRead,
    NoteSourceCreate,
    NoteSourceRead,
    NoteUpdate,
)


ENTITY_MODELS = {
    "learning_goal": LearningGoal,
    "course": Course,
    "knowledge_point": KnowledgePoint,
    "material": Material,
    "material_chunk": MaterialChunk,
    "daily_task": DailyTask,
    "learning_session": LearningSession,
    "learning_activity": LearningActivity,
    "rag_message": RagMessage,
}


class NoteService:
    def __init__(self, db, settings, clock: Clock | None = None):
        self.db = db
        self.settings = settings
        self.clock = clock or clock_from_settings(settings)

    def _get(self, note_id: int) -> Note:
        note = self.db.get(Note, note_id)
        if note is None:
            raise AppError("note_not_found", "笔记不存在", status.HTTP_404_NOT_FOUND)
        return note

    @staticmethod
    def _clean_markdown(value: str) -> str:
        if "\x00" in value:
            raise AppError(
                "note_content_invalid", "笔记内容包含无效字符",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return value.replace("\r\n", "\n")

    @staticmethod
    def _title(value: str | None, content: str) -> str:
        if value and value.strip():
            return value.strip()
        for line in content.splitlines():
            candidate = re.sub(r"^#{1,6}\s*", "", line).strip()
            if candidate:
                return candidate[:300]
        return "未命名笔记"

    @staticmethod
    def _normalized_tags(values: list[str]) -> list[str]:
        result: list[str] = []
        keys: set[str] = set()
        for raw in values:
            value = raw.strip()
            if not value:
                continue
            if len(value) > 64:
                raise AppError(
                    "note_tag_invalid", "标签不能超过 64 个字符",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            key = value.casefold()
            if key not in keys:
                keys.add(key)
                result.append(value)
        return result

    def _entity(self, entity_type: str, entity_id: int, *, required: bool):
        model = ENTITY_MODELS.get(entity_type)
        if model is None:
            raise AppError(
                "note_link_type_invalid", "不支持关联此类学习对象",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {"entity_type": entity_type},
            )
        entity = self.db.get(model, entity_id)
        if required and entity is None:
            raise AppError(
                "note_link_target_not_found", "关联的学习对象不存在",
                status.HTTP_404_NOT_FOUND,
                {"entity_type": entity_type, "entity_id": entity_id},
            )
        return entity

    @staticmethod
    def _entity_title(entity_type: str, entity_id: int, entity) -> str:
        if entity is None:
            return "来源已失效"
        if hasattr(entity, "title"):
            return str(entity.title)
        if entity_type == "material_chunk":
            return f"资料片段 {entity.chunk_index + 1}"
        if entity_type == "learning_session":
            return f"学习会话 #{entity_id}"
        if entity_type == "rag_message":
            return (entity.content.strip() or f"资料问答消息 #{entity_id}")[:80]
        return f"学习对象 #{entity_id}"

    def _touch(self, note: Note) -> None:
        note.updated_at = self.clock.now()

    def _replace_tags(self, note: Note, values: list[str]) -> None:
        self.db.query(NoteTag).filter(NoteTag.note_id == note.id).delete(
            synchronize_session=False
        )
        for value in self._normalized_tags(values):
            self.db.add(NoteTag(note_id=note.id, tag=value))
        self._touch(note)

    def _new_link(self, note: Note, payload: NoteLinkCreate) -> NoteLink:
        self._entity(payload.entity_type, payload.entity_id, required=True)
        existing = self.db.scalar(
            select(NoteLink).where(
                NoteLink.note_id == note.id,
                NoteLink.entity_type == payload.entity_type,
                NoteLink.entity_id == str(payload.entity_id),
                NoteLink.relation_type == payload.relation_type,
            )
        )
        if existing:
            return existing
        link = NoteLink(
            note_id=note.id,
            entity_type=payload.entity_type,
            entity_id=str(payload.entity_id),
            relation_type=payload.relation_type,
        )
        self.db.add(link)
        self.db.flush()
        self._touch(note)
        return link

    def _new_source(self, note: Note, payload: NoteSourceCreate) -> NoteSource:
        material = self.db.get(Material, payload.material_id)
        if material is None:
            raise AppError(
                "note_source_material_not_found", "摘录资料不存在",
                status.HTTP_404_NOT_FOUND,
            )
        chunk = None
        if payload.chunk_id:
            chunk = self.db.get(MaterialChunk, payload.chunk_id)
            if chunk is None or chunk.material_id != material.id:
                raise AppError(
                    "note_source_chunk_invalid", "资料片段不存在或不属于该资料",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
        locator = payload.source_locator
        if not locator and chunk:
            parts = []
            if chunk.page_number:
                parts.append(f"第 {chunk.page_number} 页")
            if chunk.section_title:
                parts.append(chunk.section_title)
            parts.append(f"片段 {chunk.chunk_index + 1}")
            locator = " · ".join(parts)
        source = NoteSource(
            note_id=note.id,
            material_id=material.id,
            chunk_id=chunk.id if chunk else None,
            source_title=(payload.source_title or material.title or material.original_filename).strip(),
            source_locator=locator.strip() if locator else None,
            quoted_text=payload.quoted_text.strip(),
        )
        self.db.add(source)
        self.db.flush()
        self._touch(note)
        return source

    def create(self, payload: NoteCreate) -> NoteRead:
        content = self._clean_markdown(payload.content_markdown)
        note = Note(
            title=self._title(payload.title, content),
            content_markdown=content,
            note_type=payload.note_type,
            status="active",
            is_pinned=payload.is_pinned,
        )
        self.db.add(note)
        self.db.flush()
        self._replace_tags(note, payload.tags)
        for link in payload.links:
            self._new_link(note, link)
        for source in payload.sources:
            self._new_source(note, source)
        self.db.commit()
        self.db.refresh(note)
        return self.serialize(note)

    def update(self, note_id: int, payload: NoteUpdate) -> NoteRead:
        note = self._get(note_id)
        values = payload.model_dump(exclude_unset=True)
        if "content_markdown" in values:
            note.content_markdown = self._clean_markdown(values["content_markdown"] or "")
        if "title" in values:
            if not values["title"] or not values["title"].strip():
                raise AppError(
                    "note_title_invalid", "笔记标题不能为空",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            note.title = values["title"].strip()
        if values.get("note_type") is not None:
            note.note_type = values["note_type"]
        if values.get("is_pinned") is not None:
            note.is_pinned = values["is_pinned"]
        if values.get("status") is not None:
            note.status = values["status"]
            note.archived_at = self.clock.now() if note.status == "archived" else None
        if "tags" in values:
            self._replace_tags(note, values["tags"] or [])
        self._touch(note)
        self.db.commit()
        self.db.refresh(note)
        return self.serialize(note)

    def archive_or_delete(self, note_id: int, *, permanent: bool, confirmed: bool) -> None:
        note = self._get(note_id)
        if permanent:
            if not confirmed:
                raise AppError(
                    "note_delete_confirmation_required", "永久删除笔记需要确认",
                    status.HTTP_409_CONFLICT,
                )
            self.db.delete(note)
        else:
            note.status = "archived"
            note.archived_at = note.archived_at or self.clock.now()
            self._touch(note)
        self.db.commit()

    def add_link(self, note_id: int, payload: NoteLinkCreate) -> NoteLinkRead:
        note = self._get(note_id)
        link = self._new_link(note, payload)
        self.db.commit()
        self.db.refresh(link)
        return self._link_read(link)

    def delete_link(self, note_id: int, link_id: int) -> None:
        note = self._get(note_id)
        link = self.db.get(NoteLink, link_id)
        if link is None or link.note_id != note.id:
            raise AppError("note_link_not_found", "笔记关联不存在", status.HTTP_404_NOT_FOUND)
        self.db.delete(link)
        self._touch(note)
        self.db.commit()

    def add_source(self, note_id: int, payload: NoteSourceCreate) -> NoteSourceRead:
        note = self._get(note_id)
        source = self._new_source(note, payload)
        self.db.commit()
        self.db.refresh(source)
        return self._source_read(source)

    def delete_source(self, note_id: int, source_id: int) -> None:
        note = self._get(note_id)
        source = self.db.get(NoteSource, source_id)
        if source is None or source.note_id != note.id:
            raise AppError("note_source_not_found", "笔记摘录不存在", status.HTTP_404_NOT_FOUND)
        self.db.delete(source)
        self._touch(note)
        self.db.commit()

    def page(
        self, *, query: str | None, note_type: str | None, tag: str | None,
        entity_type: str | None, entity_id: int | None, pinned: bool | None,
        archived: bool | None, sort: str, page: int, page_size: int,
    ) -> NotePage:
        statement = select(Note)
        if query and query.strip():
            token = f"%{query.strip()}%"
            statement = statement.where(
                or_(Note.title.ilike(token), Note.content_markdown.ilike(token))
            )
        if note_type:
            statement = statement.where(Note.note_type == note_type)
        if pinned is not None:
            statement = statement.where(Note.is_pinned.is_(pinned))
        if archived is not None:
            statement = statement.where(
                Note.status == ("archived" if archived else "active")
            )
        if tag:
            note_ids = select(NoteTag.note_id).where(func.lower(NoteTag.tag) == tag.strip().lower())
            statement = statement.where(Note.id.in_(note_ids))
        if entity_type or entity_id:
            if not entity_type or not entity_id:
                raise AppError(
                    "note_link_filter_invalid", "关联筛选需要同时提供类型和 ID",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            self._entity(entity_type, entity_id, required=False)
            note_ids = select(NoteLink.note_id).where(
                NoteLink.entity_type == entity_type,
                NoteLink.entity_id == str(entity_id),
            )
            statement = statement.where(Note.id.in_(note_ids))
        total = self.db.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        ) or 0
        orders = {
            "updated_desc": (Note.is_pinned.desc(), Note.updated_at.desc(), Note.id.desc()),
            "updated_asc": (Note.updated_at.asc(), Note.id.asc()),
            "created_desc": (Note.created_at.desc(), Note.id.desc()),
            "title": (Note.title.asc(), Note.id.asc()),
        }
        rows = self.db.scalars(
            statement.order_by(*orders[sort])
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return NotePage(
            items=[self.serialize(row) for row in rows],
            total=int(total), page=page, page_size=page_size,
            pages=ceil(total / page_size) if total else 0,
        )

    def detail(self, note_id: int) -> NoteRead:
        return self.serialize(self._get(note_id))

    def _link_read(self, link: NoteLink) -> NoteLinkRead:
        entity_id = int(link.entity_id)
        entity = self._entity(link.entity_type, entity_id, required=False)
        return NoteLinkRead(
            id=link.id, entity_type=link.entity_type, entity_id=entity_id,
            relation_type=link.relation_type,
            entity_title=self._entity_title(link.entity_type, entity_id, entity),
            source_available=entity is not None, created_at=link.created_at,
        )

    def _source_read(self, source: NoteSource) -> NoteSourceRead:
        available = bool(source.material_id and self.db.get(Material, source.material_id))
        return NoteSourceRead(
            id=source.id, material_id=source.material_id, chunk_id=source.chunk_id,
            source_title=source.source_title, source_locator=source.source_locator,
            quoted_text=source.quoted_text, source_available=available,
            created_at=source.created_at,
        )

    def serialize(self, note: Note) -> NoteRead:
        tags = list(self.db.scalars(
            select(NoteTag.tag).where(NoteTag.note_id == note.id).order_by(NoteTag.tag)
        ))
        links = self.db.scalars(
            select(NoteLink).where(NoteLink.note_id == note.id).order_by(NoteLink.id)
        ).all()
        sources = self.db.scalars(
            select(NoteSource).where(NoteSource.note_id == note.id).order_by(NoteSource.id)
        ).all()
        return NoteRead(
            id=note.id, title=note.title, content_markdown=note.content_markdown,
            note_type=note.note_type, status=note.status, is_pinned=note.is_pinned,
            archived_at=note.archived_at, tags=tags,
            links=[self._link_read(item) for item in links],
            sources=[self._source_read(item) for item in sources],
            created_at=note.created_at, updated_at=note.updated_at,
        )
