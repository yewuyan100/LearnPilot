from fastapi import APIRouter, Response, status

from app.api.deps import DbSession
from app.schemas.material_learning import (
    EffectiveMaterialRead,
    MaterialLearningBatchItemRead,
    MaterialLearningBatchMaterialsCreate,
    MaterialLearningBatchResultRead,
    MaterialLearningContextRead,
    MaterialLearningLinkBulkCreate,
    MaterialLearningLinkCreate,
    MaterialLearningLinkRead,
    MaterialLearningLinkUpdate,
)
from app.core.errors import AppError
from app.services.material_learning import MaterialLearningLinkService, MaterialScopeResolver


router = APIRouter(tags=["material learning"])


@router.get(
    "/material-learning-links",
    response_model=list[MaterialLearningContextRead],
    summary="List direct material learning contexts in one bounded query",
)
def list_all_material_learning_links(
    db: DbSession, material_ids: str | None = None
) -> list[MaterialLearningContextRead]:
    parsed = None
    if material_ids is not None:
        try:
            parsed = list(dict.fromkeys(int(item) for item in material_ids.split(",") if item))
        except ValueError as exc:
            raise AppError(
                "material_ids_invalid", "material_ids must be comma-separated integers.",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            ) from exc
    return MaterialScopeResolver(db).list_all_direct_contexts(parsed)


@router.post(
    "/material-learning-links/bulk-materials",
    response_model=MaterialLearningBatchResultRead,
    summary="Link several selected materials and report every result",
)
def bulk_link_materials(
    payload: MaterialLearningBatchMaterialsCreate, db: DbSession
) -> MaterialLearningBatchResultRead:
    service = MaterialLearningLinkService(db)
    items: list[MaterialLearningBatchItemRead] = []
    for material_id in payload.material_ids:
        try:
            link = service.create_link(material_id, payload.link)
            items.append(MaterialLearningBatchItemRead(
                material_id=material_id, success=True, link=link
            ))
        except AppError as exc:
            items.append(MaterialLearningBatchItemRead(
                material_id=material_id,
                success=False,
                error_code=exc.code,
                error_message=exc.message,
            ))
    succeeded = sum(item.success for item in items)
    return MaterialLearningBatchResultRead(
        requested=len(items), succeeded=succeeded, failed=len(items) - succeeded, items=items
    )


@router.get(
    "/materials/{material_id}/learning-links",
    response_model=list[MaterialLearningLinkRead],
    summary="List direct learning ownership for a material",
)
def list_material_learning_links(
    material_id: int, db: DbSession
) -> list[MaterialLearningLinkRead]:
    return MaterialLearningLinkService(db).list_material_links(material_id)


@router.post(
    "/materials/{material_id}/learning-links",
    response_model=MaterialLearningLinkRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user-confirmed material learning link",
    description=(
        "Single-user local write boundary. The service validates the material, target and "
        "learning hierarchy before persisting a direct relationship."
    ),
)
def create_material_learning_link(
    material_id: int, payload: MaterialLearningLinkCreate, db: DbSession
) -> MaterialLearningLinkRead:
    return MaterialLearningLinkService(db).create_link(material_id, payload)


@router.post(
    "/materials/{material_id}/learning-links/bulk",
    response_model=list[MaterialLearningLinkRead],
    status_code=status.HTTP_201_CREATED,
    summary="Atomically create material learning links",
)
def bulk_create_material_learning_links(
    material_id: int, payload: MaterialLearningLinkBulkCreate, db: DbSession
) -> list[MaterialLearningLinkRead]:
    return MaterialLearningLinkService(db).bulk_create_links(material_id, payload.links)


@router.patch(
    "/materials/{material_id}/learning-links/{link_id}",
    response_model=MaterialLearningLinkRead,
    summary="Update relationship metadata without changing its target",
)
def update_material_learning_link(
    material_id: int,
    link_id: int,
    payload: MaterialLearningLinkUpdate,
    db: DbSession,
) -> MaterialLearningLinkRead:
    return MaterialLearningLinkService(db).update_link(material_id, link_id, payload)


@router.delete(
    "/materials/{material_id}/learning-links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a relationship without deleting the material or target",
)
def delete_material_learning_link(
    material_id: int, link_id: int, db: DbSession
) -> Response:
    MaterialLearningLinkService(db).delete_link(material_id, link_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/learning-goals/{goal_id}/materials",
    response_model=list[EffectiveMaterialRead],
    summary="List direct and descendant materials visible to a learning goal",
)
def list_learning_goal_materials(
    goal_id: int, db: DbSession
) -> list[EffectiveMaterialRead]:
    return MaterialScopeResolver(db).list_target_materials("learning_goal", goal_id)


@router.get(
    "/courses/{course_id}/materials",
    response_model=list[EffectiveMaterialRead],
    summary="List direct, inherited and descendant materials visible to a course",
)
def list_course_materials(course_id: int, db: DbSession) -> list[EffectiveMaterialRead]:
    return MaterialScopeResolver(db).list_target_materials("course", course_id)


@router.get(
    "/knowledge-points/{knowledge_point_id}/materials",
    response_model=list[EffectiveMaterialRead],
    summary="List direct and inherited materials visible to a knowledge point",
)
def list_knowledge_point_materials(
    knowledge_point_id: int, db: DbSession
) -> list[EffectiveMaterialRead]:
    return MaterialScopeResolver(db).list_target_materials(
        "knowledge_point", knowledge_point_id
    )
