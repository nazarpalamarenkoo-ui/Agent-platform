from fastapi import APIRouter, Depends, HTTPException, status
from src.services.device_auth_service import DeviceAuthService
from src.dependencies import get_device_auth_service
from src.schemas.device import DeviceCodeInitiate, DeviceCodeRead, DeviceTokenResponse, DeviceVerify

router = APIRouter(prefix="/device", tags=["device"])

@router.post('/initiate', response_model=DeviceCodeRead)
async def initiate_flow(
    body: DeviceCodeInitiate,
    service: DeviceAuthService = Depends(get_device_auth_service),
) -> DeviceCodeRead:
    try:
        device = await service.initiate_flow(body.user_id, body.scope)
        return DeviceCodeRead.model_validate(device)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@router.post('/verify', response_model=DeviceTokenResponse)
async def verify_device_code(
    body: DeviceVerify,
    service: DeviceAuthService = Depends(get_device_auth_service),
) -> DeviceTokenResponse:
    try:
        token = await service.verify_and_approve(body.device_code)
        return DeviceTokenResponse(access_token=token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))