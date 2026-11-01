from fastapi import APIRouter, Depends, HTTPException

from src.schemas.user import AdminUserRead, RoleUpdate
from src.api.auth.admin.auth import require_super_admin
from src.db.models.users import User
from src.dependencies import get_user_service
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