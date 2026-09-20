from fastapi import APIRouter, Depends, HTTPException, status
from src.services.knowledge_pack_service import KnowledgePackService
from src.dependencies import get_knowledge_pack_service
from src.schemas.knowledge_pack import KnowledgePackCreate, KnowledgePackRead

router = APIRouter(prefix="/knowledge-packs", tags=["knowledge-packs"])

@router.post("", response_model=KnowledgePackRead, status_code=status.HTTP_201_CREATED)
async def create_pack(
    body: KnowledgePackCreate,
    service: KnowledgePackService = Depends(get_knowledge_pack_service),
):
    try:
        pack = await service.create_pack(body.name, body.domain_id, body.description, body.slug)
        return KnowledgePackRead.model_validate(pack)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/by-domain/{domain_id}", response_model=list[KnowledgePackRead])
async def get_packs_by_domain(
    domain_id: int,
    service: KnowledgePackService = Depends(get_knowledge_pack_service),
):
    packs = await service.get_packs_by_domain(domain_id)
    return [KnowledgePackRead.model_validate(p) for p in packs]

@router.get("/{slug}", response_model=KnowledgePackRead)
async def get_pack_by_slug(
    slug: str,
    service: KnowledgePackService = Depends(get_knowledge_pack_service),
):
    try:
        pack = await service.get_pack_by_slug(slug)
        return KnowledgePackRead.model_validate(pack)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))