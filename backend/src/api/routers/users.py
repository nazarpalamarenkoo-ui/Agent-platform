from fastapi import APIRouter, Depends, HTTPException, status
from src.dependencies import get_user_service
from src.schemas.user import UserCreate, UserRead, UserUpdate, ChangePassword
from src.services.user_service import UserService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    service: UserService = Depends(get_user_service),
) -> UserRead:
    try:
        user = await service.create_user(body.username, body.email, body.password)
        return UserRead.model_validate(user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@router.get('/{user_id}', response_model=UserRead)
async def get_user(
    user_id: int,
    service: UserService = Depends(get_user_service)
) -> UserRead:
    
    try:
        user = await service.get_user(user_id)
        return UserRead.model_validate(user)
    except ValueError as e:
        raise HTTPException(status_code = 400, detail=str(e))
    
@router.patch('/{user_id}', response_model=UserRead)
async def update_user(
    user_id: int,
    body: UserUpdate,
    service: UserService = Depends(get_user_service)
) -> UserRead:
    
    try:
        user = await service.update_user(user_id, body.username, body.email)
        return UserRead.model_validate(user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@router.post('/{user_id}/change-password', status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    user_id: int,
    body: ChangePassword,
    service: UserService = Depends(get_user_service)
):
    try:
        await service.change_password(user_id, body.old_password, body.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    service: UserService = Depends(get_user_service),
):
    try:
        await service.delete_user(user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))