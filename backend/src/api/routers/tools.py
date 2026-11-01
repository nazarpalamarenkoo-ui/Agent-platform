from fastapi import APIRouter, Depends, Query, status

from src.api.auth.auth import get_current_user, require_admin
from src.api.routers.errors import to_http
from src.db.models.users import User
from src.dependencies import get_tool_service
from src.schemas.catalog_ops import ToolUpdate
from src.schemas.tool import ToolCreate, ToolRead
from src.services.tool_service import ToolService

router = APIRouter(
    prefix="/tools",
    tags=["tools"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[ToolRead])
async def get_tools(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    domain_id: int | None = None,
    include_archived: bool = False,
    actor: User = Depends(get_current_user),
    service: ToolService = Depends(get_tool_service),
) -> list[ToolRead]:
    try:
        tools = await service.list_tools(
            actor,
            limit=limit,
            offset=offset,
            domain_id=domain_id,
            include_archived=include_archived,
        )
        return [ToolRead.model_validate(t) for t in tools]
    except ValueError as e:
        raise to_http(e)


@router.get("/by-domain/{domain_id}", response_model=list[ToolRead])
async def get_tools_by_domain(
    domain_id: int,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    actor: User = Depends(get_current_user),
    service: ToolService = Depends(get_tool_service),
) -> list[ToolRead]:
    try:
        tools = await service.list_tools(actor, limit=limit, offset=offset, domain_id=domain_id)
        return [ToolRead.model_validate(t) for t in tools]
    except ValueError as e:
        raise to_http(e)


@router.post(
    "",
    response_model=ToolRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_tool(
    body: ToolCreate,
    actor: User = Depends(get_current_user),
    service: ToolService = Depends(get_tool_service),
) -> ToolRead:
    try:
        tool = await service.create_tool(
            actor,
            body.tool_name,
            body.description,
            body.url,
            body.auth_type,
            body.auth_description,
            body.domain_ids,
        )
        return ToolRead.model_validate(tool)
    except ValueError as e:
        raise to_http(e)


@router.get("/{tool_id}", response_model=ToolRead)
async def get_tool(
    tool_id: int,
    actor: User = Depends(get_current_user),
    service: ToolService = Depends(get_tool_service),
) -> ToolRead:
    try:
        tool = await service.get_tool(actor, tool_id)
        return ToolRead.model_validate(tool)
    except ValueError as e:
        raise to_http(e)


@router.put(
    "/{tool_id}",
    response_model=ToolRead,
    dependencies=[Depends(require_admin)],
)
async def update_tool(
    tool_id: int,
    body: ToolUpdate,
    actor: User = Depends(get_current_user),
    service: ToolService = Depends(get_tool_service),
) -> ToolRead:
    try:
        tool = await service.update_tool(
            actor,
            tool_id,
            description=body.description,
            url=body.url,
            auth_type=body.auth_type,
            auth_description=body.auth_description,
        )
        return ToolRead.model_validate(tool)
    except ValueError as e:
        raise to_http(e)


@router.post(
    "/{tool_id}/archive",
    response_model=ToolRead,
    dependencies=[Depends(require_admin)],
)
async def archive_tool(
    tool_id: int,
    actor: User = Depends(get_current_user),
    service: ToolService = Depends(get_tool_service),
) -> ToolRead:
    try:
        tool = await service.archive_tool(actor, tool_id)
        return ToolRead.model_validate(tool)
    except ValueError as e:
        raise to_http(e)


@router.post(
    "/{tool_id}/restore",
    response_model=ToolRead,
    dependencies=[Depends(require_admin)],
)
async def restore_tool(
    tool_id: int,
    actor: User = Depends(get_current_user),
    service: ToolService = Depends(get_tool_service),
) -> ToolRead:
    try:
        tool = await service.restore_tool(actor, tool_id)
        return ToolRead.model_validate(tool)
    except ValueError as e:
        raise to_http(e)