import logging

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.auth.auth import get_current_user
from src.db.models.users import User
from src.dependencies import get_user_service
from src.schemas.user import ChangePassword, UserRead, UserUpdate
from src.services.errors import ConflictError, ForbiddenError, NotFoundError
from src.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", response_model=UserRead)
async def get_me(actor: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(actor)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: int,
    actor: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> UserRead:
    try:
        user = await service.get_user_for(actor, user_id)
        return UserRead.model_validate(user)
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    body: UserUpdate,
    actor: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> UserRead:
    try:
        user = await service.update_user(actor, user_id, body.username, body.email)
        return UserRead.model_validate(user)
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{user_id}/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    user_id: int,
    body: ChangePassword,
    actor: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> None:
    if actor.id != user_id:
        raise HTTPException(status_code=403, detail="You can change only your own password")
    try:
        await service.change_password(user_id, body.old_password, body.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    actor: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> None:
    try:
        await service.delete_user(actor, user_id)
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))