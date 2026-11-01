from fastapi import APIRouter, Depends, Query, status

from src.api.auth.auth import get_current_user
from src.api.routers.errors import to_http
from src.db.models.users import User
from src.dependencies import get_user_tool_service
from src.schemas.user_tools import MyToolCreate, MyToolRead, MyToolResponse, MyToolUpdate
from src.services.user_tool_service import UserToolService

router = APIRouter(
    prefix="/my/tools",
    tags=["my-tools"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[MyToolRead])
async def list_my_tools(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_archived: bool = False,
    actor: User = Depends(get_current_user),
    service: UserToolService = Depends(get_user_tool_service),
):
    tools = await service.list_tools(
        actor, limit=limit, offset=offset, include_archived=include_archived
    )
    return [MyToolRead.model_validate(t) for t in tools]


@router.post("", response_model=MyToolResponse, status_code=status.HTTP_201_CREATED)
async def create_my_tool(
    body: MyToolCreate,
    actor: User = Depends(get_current_user),
    service: UserToolService = Depends(get_user_tool_service),
):
    try:
        tool, warnings = await service.create_tool(
            actor, body.tool_name, body.description, body.url,
            body.auth_type, body.auth_description, body.domain_ids,
        )
    except ValueError as e:
        raise to_http(e)
    return MyToolResponse(tool=MyToolRead.model_validate(tool), warnings=warnings)


@router.get("/{tool_id}", response_model=MyToolRead)
async def get_my_tool(
    tool_id: int,
    actor: User = Depends(get_current_user),
    service: UserToolService = Depends(get_user_tool_service),
):
    try:
        return MyToolRead.model_validate(await service.get_tool(actor, tool_id))
    except ValueError as e:
        raise to_http(e)


@router.put("/{tool_id}", response_model=MyToolResponse)
async def update_my_tool(
    tool_id: int,
    body: MyToolUpdate,
    actor: User = Depends(get_current_user),
    service: UserToolService = Depends(get_user_tool_service),
):
    try:
        tool, warnings = await service.update_tool(
            actor, tool_id,
            description=body.description, url=body.url,
            auth_type=body.auth_type, auth_description=body.auth_description,
        )
    except ValueError as e:
        raise to_http(e)
    return MyToolResponse(tool=MyToolRead.model_validate(tool), warnings=warnings)


@router.post("/{tool_id}/archive", response_model=MyToolRead)
async def archive_my_tool(
    tool_id: int,
    actor: User = Depends(get_current_user),
    service: UserToolService = Depends(get_user_tool_service),
):
    try:
        return MyToolRead.model_validate(await service.archive_tool(actor, tool_id))
    except ValueError as e:
        raise to_http(e)


@router.post("/{tool_id}/restore", response_model=MyToolRead)
async def restore_my_tool(
    tool_id: int,
    actor: User = Depends(get_current_user),
    service: UserToolService = Depends(get_user_tool_service),
):
    try:
        return MyToolRead.model_validate(await service.restore_tool(actor, tool_id))
    except ValueError as e:
        raise to_http(e)