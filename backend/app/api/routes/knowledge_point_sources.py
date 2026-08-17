from fastapi import APIRouter, Query, Response, status

from app.api.deps import DbSession
from app.schemas.knowledge_point_source import (
    KnowledgePointSourceCreate,
    KnowledgePointSourceRead,
    SourceChunkPage,
)
from app.services.knowledge_point_sources import KnowledgePointSourceService


router = APIRouter(tags=["knowledge point sources"])


@router.get(
    "/knowledge-points/{knowledge_point_id}/sources",
    response_model=list[KnowledgePointSourceRead],
)
def list_knowledge_point_sources(
    knowledge_point_id: int, db: DbSession
) -> list[KnowledgePointSourceRead]:
    return KnowledgePointSourceService(db).list(knowledge_point_id)


@router.post(
    "/knowledge-points/{knowledge_point_id}/sources",
    response_model=KnowledgePointSourceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_knowledge_point_source(
    knowledge_point_id: int,
    payload: KnowledgePointSourceCreate,
    db: DbSession,
) -> KnowledgePointSourceRead:
    return KnowledgePointSourceService(db).create(knowledge_point_id, payload)


@router.delete(
    "/knowledge-points/{knowledge_point_id}/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_knowledge_point_source(
    knowledge_point_id: int, source_id: int, db: DbSession
) -> Response:
    KnowledgePointSourceService(db).delete(knowledge_point_id, source_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/knowledge-points/{knowledge_point_id}/source-chunks",
    response_model=SourceChunkPage,
)
def search_knowledge_point_source_chunks(
    knowledge_point_id: int,
    db: DbSession,
    material_id: int = Query(gt=0),
    search: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
) -> SourceChunkPage:
    return KnowledgePointSourceService(db).search_chunks(
        knowledge_point_id, material_id, search, page, page_size
    )
