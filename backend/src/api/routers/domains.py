from fastapi import APIRouter, Depends, HTTPException, status
from src.services.domain_service import DomainService
from src.dependencies import get_domain_service
from src.schemas.domain import DomainCreate, DomainRead

router = APIRouter(prefix="/domains", tags=["domains"])

@router.post("", response_model=DomainRead, status_code=status.HTTP_201_CREATED)
async def create_domain(
    body: DomainCreate,
    service: DomainService = Depends(get_domain_service),
):
    try:
        domain = await service.create_domain(body.slug, body.name, body.description, body.parent_domain_id)
        return DomainRead.model_validate(domain)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("", response_model=list[DomainRead])
async def get_all_domains(
    limit: int = 100,
    offset: int = 0,
    service: DomainService = Depends(get_domain_service),
):
    domains = await service.get_all_domains(limit=limit, offset=offset)
    return [DomainRead.model_validate(d) for d in domains]

@router.get("/roots", response_model=list[DomainRead])
async def get_root_domains(
    service: DomainService = Depends(get_domain_service),
):
    domains = await service.get_root_domains()
    return [DomainRead.model_validate(d) for d in domains]

@router.get("/{domain_id}", response_model=DomainRead)
async def get_domain(
    domain_id: int,
    service: DomainService = Depends(get_domain_service),
):
    try:
        domain = await service.get_domain(domain_id)
        return DomainRead.model_validate(domain)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))