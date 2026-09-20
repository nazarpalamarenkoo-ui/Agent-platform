from fastapi import APIRouter, Depends, HTTPException, status
from src.services.tool_service import ToolService
from src.dependencies import get_tool_service
from src.schemas.tool import ToolRead, ToolCreate

router = APIRouter(prefix="/tools", tags=["tools"])

@router.post('', response_model=ToolRead, status_code=status.HTTP_201_CREATED)
async def create_tool(
    body: ToolCreate,
    service: ToolService = Depends(get_tool_service)
) -> ToolRead:
    try:
        tool = await service.create_tool(body.tool_name, body.description, body.domain_ids)
        return ToolRead.model_validate(tool)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@router.get('', response_model=list[ToolRead], status_code = status.HTTP_200_OK)
async def get_tools(
    limit: int = 100,
    offset: int = 0,
    service: ToolService = Depends(get_tool_service)
) -> list[ToolRead]:
    
    try: 
        tools = await service.get_all_tools(limit, offset)
        return [ToolRead.model_validate(t) for t in tools]
    except ValueError as e:
        raise HTTPException(status_code = 400, detail = str(e))
    
@router.get('/{tool_id}', response_model=ToolRead, status_code = status.HTTP_200_OK)
async def get_tool(
    tool_id: int,
    service: ToolService = Depends(get_tool_service)
) -> ToolRead:
    
    try:
        tool = await service.get_tool(tool_id)
        return ToolRead.model_validate(tool)
    except ValueError as e:
        raise HTTPException(status_code = 400, detail = str(e))
    
@router.get('/by-domain/{domain_id}', response_model=list[ToolRead], status_code=status.HTTP_200_OK)
async def get_tools_by_domain(
    domain_id: int,
    service: ToolService = Depends(get_tool_service)
) -> list[ToolRead]:
    try:
        tools = await service.get_tools_by_domain(domain_id)
        return [ToolRead.model_validate(t) for t in tools]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))