from fastapi import APIRouter, Depends, HTTPException, status
from src.services.agent_profile_service import AgentProfileService
from src.dependencies import get_agent_profile_service
from src.schemas.agent import AgentCreate, AgentRead

router = APIRouter(prefix="/agents", tags=["agents"])

@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: AgentCreate,
    service: AgentProfileService = Depends(get_agent_profile_service),
) -> AgentRead:
    try:
        agent = await service.create_profile(body.name, body.description, body.skill_ids, body.tool_ids)
        return AgentRead.model_validate(agent)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("", response_model=list[AgentRead])
async def get_agents(
    limit: int = 100,
    offset: int = 0,
    service: AgentProfileService = Depends(get_agent_profile_service),
) -> list[AgentRead]:
    agents = await service.get_all_profiles(limit=limit, offset=offset)
    return [AgentRead.model_validate(a) for a in agents]

@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(
    agent_id: int,
    service: AgentProfileService = Depends(get_agent_profile_service),
) -> AgentRead:
    try:
        agent = await service.get_profile(agent_id)
        return AgentRead.model_validate(agent)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))