from fastapi import APIRouter, Depends, Query, Response, status

from src.api.auth.auth import get_current_user, require_admin
from src.api.routers.errors import to_http
from src.db.models.users import User
from src.dependencies import get_skill_service
from src.schemas.catalog_ops import SkillUpdate
from src.schemas.skill import SkillCreate, SkillRead
from src.services.skill_service import SkillService

router = APIRouter(
    prefix="/skills",
    tags=["skills"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[SkillRead])
async def get_skills(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    domain_id: int | None = None,
    include_archived: bool = False,
    actor: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> list[SkillRead]:
    try:
        skills = await service.list_skills(
            actor,
            limit=limit,
            offset=offset,
            domain_id=domain_id,
            include_archived=include_archived,
        )
        return [SkillRead.model_validate(s) for s in skills]
    except ValueError as e:
        raise to_http(e)


@router.get("/by-domain/{domain_id}", response_model=list[SkillRead])
async def get_skills_by_domain(
    domain_id: int,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    actor: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> list[SkillRead]:
    try:
        skills = await service.list_skills(actor, limit=limit, offset=offset, domain_id=domain_id)
        return [SkillRead.model_validate(s) for s in skills]
    except ValueError as e:
        raise to_http(e)


@router.post(
    "",
    response_model=SkillRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_skill(
    body: SkillCreate,
    actor: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> SkillRead:
    try:
        skill = await service.create_global_skill(
            actor, body.skill_name, body.description, body.content, body.domain_ids
        )
        return SkillRead.model_validate(skill)
    except ValueError as e:
        raise to_http(e)


@router.get("/{skill_id}/download")
async def download_skill(
    skill_id: int,
    actor: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> Response:
    try:
        text = await service.export_skill_md(actor, skill_id)
    except ValueError as e:
        raise to_http(e)
    return Response(
        content=text,
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="SKILL.md"'},
    )


@router.get("/{skill_id}", response_model=SkillRead)
async def get_skill(
    skill_id: int,
    actor: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> SkillRead:
    try:
        skill = await service.get_skill(actor, skill_id)
        return SkillRead.model_validate(skill)
    except ValueError as e:
        raise to_http(e)


@router.put(
    "/{skill_id}",
    response_model=SkillRead,
    dependencies=[Depends(require_admin)],
)
async def update_skill(
    skill_id: int,
    body: SkillUpdate,
    actor: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> SkillRead:
    try:
        skill = await service.update_global_skill(
            actor, skill_id, description=body.description, content=body.content
        )
        return SkillRead.model_validate(skill)
    except ValueError as e:
        raise to_http(e)


@router.post(
    "/{skill_id}/archive",
    response_model=SkillRead,
    dependencies=[Depends(require_admin)],
)
async def archive_skill(
    skill_id: int,
    actor: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> SkillRead:
    try:
        skill = await service.archive_skill(actor, skill_id)
        return SkillRead.model_validate(skill)
    except ValueError as e:
        raise to_http(e)


@router.post(
    "/{skill_id}/restore",
    response_model=SkillRead,
    dependencies=[Depends(require_admin)],
)
async def restore_skill(
    skill_id: int,
    actor: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service),
) -> SkillRead:
    try:
        skill = await service.restore_skill(actor, skill_id)
        return SkillRead.model_validate(skill)
    except ValueError as e:
        raise to_http(e)