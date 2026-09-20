from fastapi import APIRouter, Depends, HTTPException, status
from src.services.config_bundle_service import ConfigBundleService
from src.dependencies import get_config_bundle_service
from src.schemas.config_bundle import ConfigBundleCreate, ConfigBundleFromAgent, ConfigBundleRead

router = APIRouter(prefix="/config-bundles", tags=["config-bundles"])

@router.post("", response_model=ConfigBundleRead, status_code=status.HTTP_201_CREATED)
async def create_bundle(
    user_id: int,
    body: ConfigBundleCreate,
    service: ConfigBundleService = Depends(get_config_bundle_service),
) -> ConfigBundleRead:
    try:
        bundle = await service.create_bundle(
            user_id, body.agent_id, body.name, body.description,
            body.skill_ids, body.tool_ids, body.knowledge_pack_ids
        )
        return ConfigBundleRead.model_validate(bundle)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/from-agent", response_model=ConfigBundleRead, status_code=status.HTTP_201_CREATED)
async def create_from_agent(
    user_id: int,
    body: ConfigBundleFromAgent,
    service: ConfigBundleService = Depends(get_config_bundle_service),
) -> ConfigBundleRead:
    try:
        bundle = await service.create_from_agent(user_id, body.agent_id, body.name, body.description)
        return ConfigBundleRead.model_validate(bundle)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{bundle_id}/clone", response_model=ConfigBundleRead, status_code=status.HTTP_201_CREATED)
async def clone_bundle(
    bundle_id: int,
    user_id: int,
    service: ConfigBundleService = Depends(get_config_bundle_service),
) -> ConfigBundleRead:
    try:
        bundle = await service.clone_bundle(bundle_id, user_id)
        return ConfigBundleRead.model_validate(bundle)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("", response_model=list[ConfigBundleRead])
async def get_user_bundles(
    user_id: int,
    agent_id: int,
    service: ConfigBundleService = Depends(get_config_bundle_service),
) -> list[ConfigBundleRead]:
    bundles = await service.get_user_bundles(user_id, agent_id)
    return [ConfigBundleRead.model_validate(b) for b in bundles]