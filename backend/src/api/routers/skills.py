from fastapi import APIRouter, Depends, HTTPException, status
from src.db.models.skills import Skill
from src.services.skill_service import SkillService
from src.dependencies import get_skill_service
from src.schemas.skill import SkillRead, SkillCreate

router = APIRouter(prefix="/skills", tags=["skills"])

@router.post('', response_model=SkillRead, status_code=status.HTTP_201_CREATED)
async def create_skill(
    body: SkillCreate,
    service: SkillService = Depends(get_skill_service)
) -> SkillRead:
    try:
        skill = await service.create_skill(body.skill_name, body.description, body.domain_ids)
        return SkillRead.model_validate(skill)
    except ValueError as e:
        raise HTTPException(status_code = 400, detail = str(e))
    
@router.get('', response_model=list[SkillRead], status_code = status.HTTP_200_OK)
async def get_skills(
    limit: int = 100,
    offset: int = 0,
    service: SkillService = Depends(get_skill_service)
) -> list[SkillRead]:
    
    try: 
        skills = await service.get_all_skills(limit, offset)
        return [SkillRead.model_validate(s) for s in skills]
    except ValueError as e:
        raise HTTPException(status_code = 400, detail = str(e))
    
@router.get('/{skill_id}', response_model=SkillRead, status_code = status.HTTP_200_OK)
async def get_skill(
    skill_id: int,
    service: SkillService = Depends(get_skill_service)
) -> SkillRead:
    
    try:
        skill = await service.get_skill(skill_id)
        return SkillRead.model_validate(skill)
    except ValueError as e:
        raise HTTPException(status_code = 400, detail = str(e))
    
@router.get('/by-domain/{domain_id}', response_model=list[SkillRead], status_code=status.HTTP_200_OK)
async def get_skills_by_domain(
    domain_id: int,
    service: SkillService = Depends(get_skill_service)
) -> list[SkillRead]:
    try:
        skills = await service.get_skills_by_domain(domain_id)
        return [SkillRead.model_validate(s) for s in skills]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))