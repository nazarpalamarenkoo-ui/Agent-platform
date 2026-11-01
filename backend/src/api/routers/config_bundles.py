from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from src.api.auth.auth import get_current_user
from src.db.models.users import User
from src.dependencies import (
    get_bundle_export_service,
    get_config_bundle_service,
    get_effective_bundle_service,
)
from src.schemas.bundle_ops import BundleItems, ConfigBundleUpdate, EffectiveBundleRead
from src.schemas.config_bundle import (
    ConfigBundleClone,
    ConfigBundleCreate,
    ConfigBundleFromAgent,
    ConfigBundleRead,
)
from src.services.bundle_export_service import BundleExportService
from src.services.config_bundle_service import ConfigBundleService
from src.services.effective_bundle_service import EffectiveBundleService
from src.services.errors import ConflictError, NotFoundError

router = APIRouter(
    prefix="/config-bundles",
    tags=["config-bundles"],
    dependencies=[Depends(get_current_user)],
)


@router.post("", response_model=ConfigBundleRead, status_code=status.HTTP_201_CREATED)
async def create_bundle(
    body: ConfigBundleCreate,
    actor: User = Depends(get_current_user),
    service: ConfigBundleService = Depends(get_config_bundle_service),
) -> ConfigBundleRead:
    try:
        bundle = await service.create_bundle(
            actor.id,
            body.agent_id,
            body.name,
            body.description,
            body.skill_ids,
            body.tool_ids,
            body.knowledge_pack_ids,
        )
        return ConfigBundleRead.model_validate(bundle)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/from-agent", response_model=ConfigBundleRead, status_code=status.HTTP_201_CREATED)
async def create_from_agent(
    body: ConfigBundleFromAgent,
    actor: User = Depends(get_current_user),
    service: ConfigBundleService = Depends(get_config_bundle_service),
) -> ConfigBundleRead:
    try:
        bundle = await service.create_from_agent(
            actor.id, body.agent_id, body.name, body.description
        )
        return ConfigBundleRead.model_validate(bundle)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=list[ConfigBundleRead])
async def get_user_bundles(
    agent_id: int | None = None,
    user_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    actor: User = Depends(get_current_user),
    service: ConfigBundleService = Depends(get_config_bundle_service),
) -> list[ConfigBundleRead]:
    target_id = actor.id if user_id is None else user_id
    if target_id != actor.id and not actor.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")

    bundles = await service.get_user_bundles(target_id, agent_id, limit=limit, offset=offset)
    return [ConfigBundleRead.model_validate(b) for b in bundles]


@router.get("/{bundle_id}", response_model=ConfigBundleRead)
async def get_bundle(
    bundle_id: int,
    actor: User = Depends(get_current_user),
    service: ConfigBundleService = Depends(get_config_bundle_service),
) -> ConfigBundleRead:
    try:
        bundle = await service.get_bundle(bundle_id, actor.id)
        return ConfigBundleRead.model_validate(bundle)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{bundle_id}", response_model=ConfigBundleRead)
async def update_bundle(
    bundle_id: int,
    body: ConfigBundleUpdate,
    actor: User = Depends(get_current_user),
    service: ConfigBundleService = Depends(get_config_bundle_service),
) -> ConfigBundleRead:
    try:
        bundle = await service.update_bundle(
            bundle_id, actor.id, name=body.name, description=body.description
        )
        return ConfigBundleRead.model_validate(bundle)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{bundle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bundle(
    bundle_id: int,
    actor: User = Depends(get_current_user),
    service: ConfigBundleService = Depends(get_config_bundle_service),
) -> None:
    try:
        await service.delete_bundle(bundle_id, actor.id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{bundle_id}/clone",
    response_model=ConfigBundleRead,
    status_code=status.HTTP_201_CREATED,
)
async def clone_bundle(
    bundle_id: int,
    body: ConfigBundleClone,
    actor: User = Depends(get_current_user),
    service: ConfigBundleService = Depends(get_config_bundle_service),
) -> ConfigBundleRead:
    try:
        bundle = await service.clone_bundle(bundle_id, actor.id, body.name, body.description)
        return ConfigBundleRead.model_validate(bundle)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{bundle_id}/items", response_model=ConfigBundleRead)
async def add_items(
    bundle_id: int,
    body: BundleItems,
    actor: User = Depends(get_current_user),
    service: ConfigBundleService = Depends(get_config_bundle_service),
) -> ConfigBundleRead:
    try:
        bundle = await service.add_to_bundle(
            bundle_id,
            actor.id,
            skill_ids=body.skill_ids,
            tool_ids=body.tool_ids,
            knowledge_pack_ids=body.knowledge_pack_ids,
        )
        return ConfigBundleRead.model_validate(bundle)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{bundle_id}/items/remove", response_model=ConfigBundleRead)
async def remove_items(
    bundle_id: int,
    body: BundleItems,
    actor: User = Depends(get_current_user),
    service: ConfigBundleService = Depends(get_config_bundle_service),
) -> ConfigBundleRead:
    try:
        bundle = await service.remove_from_bundle(
            bundle_id,
            actor.id,
            skill_ids=body.skill_ids,
            tool_ids=body.tool_ids,
            knowledge_pack_ids=body.knowledge_pack_ids,
        )
        return ConfigBundleRead.model_validate(bundle)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{bundle_id}/effective", response_model=EffectiveBundleRead)
async def get_effective_bundle(
    bundle_id: int,
    actor: User = Depends(get_current_user),
    service: EffectiveBundleService = Depends(get_effective_bundle_service),
) -> EffectiveBundleRead:
    try:
        effective = await service.get_effective_for_user(bundle_id, actor.id)
        return EffectiveBundleRead.model_validate(effective)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{bundle_id}/export")
async def export_bundle(
    bundle_id: int,
    actor: User = Depends(get_current_user),
    service: BundleExportService = Depends(get_bundle_export_service),
) -> Response:
    try:
        result = await service.build_zip(bundle_id, actor.id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(
        content=result.content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
            "ETag": f'"{result.version_hash}"',
        },
    )