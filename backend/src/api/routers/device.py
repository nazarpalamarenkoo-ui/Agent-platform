from fastapi import APIRouter, Depends, Query, status

from src.api.auth.auth import get_current_user
from src.api.routers.errors import to_http
from src.db.models.users import User
from src.dependencies import get_config_bundle_service, get_device_auth_service
from src.schemas.device import DeviceRead, DeviceTokenCreate, DeviceTokenIssued
from src.services.config_bundle_service import ConfigBundleService
from src.services.device_auth_service import DeviceAuthService

router = APIRouter(
    prefix="/device",
    tags=["device"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/tokens", response_model=DeviceTokenIssued, status_code=status.HTTP_201_CREATED)
async def issue_token(
    body: DeviceTokenCreate,
    actor: User = Depends(get_current_user),
    service: DeviceAuthService = Depends(get_device_auth_service),
    bundle_service: ConfigBundleService = Depends(get_config_bundle_service),
) -> DeviceTokenIssued:
    try:
        if body.config_bundle_id is not None:
            await bundle_service.get_bundle(body.config_bundle_id, actor.id)
        device, token = await service.issue_token(
            actor.id, body.scope, body.name, body.config_bundle_id
        )
    except ValueError as e:
        raise to_http(e)
    return DeviceTokenIssued(
        **DeviceRead.model_validate(device).model_dump(), access_token=token
    )


@router.get("", response_model=list[DeviceRead])
async def list_devices(
    active_only: bool = True,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    actor: User = Depends(get_current_user),
    service: DeviceAuthService = Depends(get_device_auth_service),
) -> list[DeviceRead]:
    devices = await service.list_devices(
        actor.id, active_only=active_only, limit=limit, offset=offset
    )
    return [DeviceRead.model_validate(d) for d in devices]


@router.post("/{device_id}/revoke", response_model=DeviceRead)
async def revoke_device(
    device_id: int,
    actor: User = Depends(get_current_user),
    service: DeviceAuthService = Depends(get_device_auth_service),
) -> DeviceRead:
    try:
        device = await service.revoke_device(actor.id, device_id)
    except ValueError as e:
        raise to_http(e)
    return DeviceRead.model_validate(device)