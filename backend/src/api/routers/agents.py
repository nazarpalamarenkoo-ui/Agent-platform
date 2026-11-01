from fastapi import APIRouter, Depends, Query, status

from src.api.auth.auth import get_current_user, require_admin
from src.api.routers.errors import to_http
from src.db.models.users import User
from src.dependencies import get_agent_profile_service, get_config_bundle_service
from src.schemas.agent import AgentCreate, AgentRead, CustomAgentCreate, CustomAgentRead
from src.services.config_bundle_service import ConfigBundleService
from src.schemas.catalog_ops import AgentUpdate
from src.services.agent_profile_service import AgentProfileService

router = APIRouter(
    prefix="/agents",
    tags=["agents"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[AgentRead])
async def get_agents(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_archived: bool = False,
    actor: User = Depends(get_current_user),
    service: AgentProfileService = Depends(get_agent_profile_service),
) -> list[AgentRead]:
    try:
        agents = await service.list_profiles(
            actor, limit=limit, offset=offset, include_archived=include_archived
        )
        return [AgentRead.model_validate(a) for a in agents]
    except ValueError as e:
        raise to_http(e)


@router.post(
    "",
    response_model=AgentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_agent(
    body: AgentCreate,
    actor: User = Depends(get_current_user),
    service: AgentProfileService = Depends(get_agent_profile_service),
) -> AgentRead:
    try:
        agent = await service.create_profile(
            actor, body.name, body.description, body.skill_ids, body.tool_ids
        )
        return AgentRead.model_validate(agent)
    except ValueError as e:
        raise to_http(e)

@router.post("/custom", response_model=CustomAgentRead, status_code=status.HTTP_201_CREATED)
async def create_custom_agent(
    body: CustomAgentCreate,
    actor: User = Depends(get_current_user),
    service: ConfigBundleService = Depends(get_config_bundle_service),
):
    try:
        bundle = await service.create_custom_agent(
            actor.id, body.name, body.description,
            body.skill_ids, body.tool_ids, body.knowledge_pack_ids,
        )
        return CustomAgentRead.model_validate(bundle)
    except ValueError as e:
        raise to_http(e)
    
@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(
    agent_id: int,
    actor: User = Depends(get_current_user),
    service: AgentProfileService = Depends(get_agent_profile_service),
) -> AgentRead:
    try:
        agent = await service.get_profile(actor, agent_id)
        return AgentRead.model_validate(agent)
    except ValueError as e:
        raise to_http(e)


@router.put(
    "/{agent_id}",
    response_model=AgentRead,
    dependencies=[Depends(require_admin)],
)
async def update_agent(
    agent_id: int,
    body: AgentUpdate,
    actor: User = Depends(get_current_user),
    service: AgentProfileService = Depends(get_agent_profile_service),
) -> AgentRead:
    try:
        agent = await service.update_profile(
            actor,
            agent_id,
            description=body.description,
            skill_ids=body.skill_ids,
            tool_ids=body.tool_ids,
        )
        return AgentRead.model_validate(agent)
    except ValueError as e:
        raise to_http(e)


@router.post(
    "/{agent_id}/archive",
    response_model=AgentRead,
    dependencies=[Depends(require_admin)],
)
async def archive_agent(
    agent_id: int,
    actor: User = Depends(get_current_user),
    service: AgentProfileService = Depends(get_agent_profile_service),
) -> AgentRead:
    try:
        agent = await service.archive_profile(actor, agent_id)
        return AgentRead.model_validate(agent)
    except ValueError as e:
        raise to_http(e)


@router.post(
    "/{agent_id}/restore",
    response_model=AgentRead,
    dependencies=[Depends(require_admin)],
)
async def restore_agent(
    agent_id: int,
    actor: User = Depends(get_current_user),
    service: AgentProfileService = Depends(get_agent_profile_service),
) -> AgentRead:
    try:
        agent = await service.restore_profile(actor, agent_id)
        return AgentRead.model_validate(agent)
    except ValueError as e:
        raise to_http(e)