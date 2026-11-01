from fastapi import APIRouter, Depends, HTTPException

from src.api.auth.admin.auth import require_admin
from src.db.models.users import User
from src.dependencies import get_admin_user_content_service
from src.schemas.admin_skills import (
    AdminSkillListItem, AdminSkillRead, AdminToolItem, ArchiveForViolation, UserOverview,
)
from src.services.admin_user_content_service import AdminUserContentService
from src.services.errors import ConflictError, ForbiddenError, NotFoundError

router = APIRouter(prefix="/admin/users", tags=["admin-user-content"])


def _http(e: Exception) -> HTTPException:
    code = {NotFoundError: 404, ForbiddenError: 403, ConflictError: 409}.get(type(e), 400)
    return HTTPException(status_code=code, detail=str(e))


@router.get("/{user_id}/overview", response_model=UserOverview)
async def overview(user_id: int, actor: User = Depends(require_admin),
                   service: AdminUserContentService = Depends(get_admin_user_content_service)):
    try:
        return await service.overview(actor, user_id)
    except (NotFoundError, ForbiddenError) as e:
        raise _http(e)


@router.get("/{user_id}/skills", response_model=list[AdminSkillListItem])
async def list_skills(user_id: int, include_archived: bool = False, limit: int = 100,
                      offset: int = 0, actor: User = Depends(require_admin),
                      service: AdminUserContentService = Depends(get_admin_user_content_service)):
    try:
        return await service.list_skills(actor, user_id, include_archived, limit, offset)
    except (NotFoundError, ForbiddenError) as e:
        raise _http(e)


@router.get("/{user_id}/skills/{skill_id}", response_model=AdminSkillRead)
async def get_skill(user_id: int, skill_id: int, actor: User = Depends(require_admin),
                    service: AdminUserContentService = Depends(get_admin_user_content_service)):
    try:
        return await service.get_skill(actor, user_id, skill_id)
    except (NotFoundError, ForbiddenError) as e:
        raise _http(e)


@router.post("/{user_id}/skills/{skill_id}/archive", response_model=AdminSkillListItem)
async def archive_skill(user_id: int, skill_id: int, body: ArchiveForViolation,
                        actor: User = Depends(require_admin),
                        service: AdminUserContentService = Depends(get_admin_user_content_service)):
    try:
        return await service.archive_for_violation(actor, user_id, skill_id, body.reason)
    except (NotFoundError, ForbiddenError) as e:
        raise _http(e)


@router.get("/{user_id}/tools", response_model=list[AdminToolItem])
async def list_tools(user_id: int, include_archived: bool = False,
                     actor: User = Depends(require_admin),
                     service: AdminUserContentService = Depends(get_admin_user_content_service)):
    try:
        return await service.list_tools(actor, user_id, include_archived)
    except (NotFoundError, ForbiddenError) as e:
        raise _http(e)