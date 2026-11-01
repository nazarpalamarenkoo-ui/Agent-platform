from fastapi import APIRouter, Depends, HTTPException, Query
from src.api.auth.admin.auth import require_super_admin, require_admin
from src.db.models.users import User
from src.dependencies import get_user_service
from src.schemas.user import AdminUserRead, RoleUpdate, TokenLimitUpdate
from src.services.errors import ConflictError, ForbiddenError, NotFoundError
from src.services.user_service import UserService

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/admins", response_model=list[AdminUserRead])
async def list_admins(
    actor: User = Depends(require_super_admin),
    service: UserService = Depends(get_user_service),
) -> list[AdminUserRead]:
    users = await service.list_admins()
    return [AdminUserRead.model_validate(u) for u in users]


@router.put("/users/{user_id}/role", response_model=AdminUserRead)
async def set_user_role(
    user_id: int,
    body: RoleUpdate,
    actor: User = Depends(require_super_admin),
    service: UserService = Depends(get_user_service),
) -> AdminUserRead:
    try:
        user = await service.set_role(actor, user_id, body.role)
        return AdminUserRead.model_validate(user)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/users", response_model=list[AdminUserRead])
async def list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    actor: User = Depends(require_admin),
    service: UserService = Depends(get_user_service),
) -> list[AdminUserRead]:
    users = await service.list_users(limit=limit, offset=offset)
    return [AdminUserRead.model_validate(u) for u in users]


@router.get("/users/{user_id}", response_model=AdminUserRead)
async def get_user(
    user_id: int,
    actor: User = Depends(require_admin),
    service: UserService = Depends(get_user_service),
) -> AdminUserRead:
    try:
        user = await service.get_user_for(actor, user_id)
        return AdminUserRead.model_validate(user)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.put("/users/{user_id}/token-limit", response_model=AdminUserRead)
async def set_token_limit(
    user_id: int,
    body: TokenLimitUpdate,
    actor: User = Depends(require_admin),
    service: UserService = Depends(get_user_service),
) -> AdminUserRead:
    try:
        user = await service.set_token_limit(actor, user_id, body.token_limit)
        return AdminUserRead.model_validate(user)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/users/{user_id}/reset-usage", response_model=AdminUserRead)
async def reset_usage(
    user_id: int,
    actor: User = Depends(require_admin),
    service: UserService = Depends(get_user_service),
) -> AdminUserRead:
    try:
        user = await service.reset_usage(actor, user_id)
        return AdminUserRead.model_validate(user)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))