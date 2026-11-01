from fastapi import APIRouter, Depends, Query, status

from src.api.auth.auth import get_current_user, require_admin
from src.api.routers.errors import to_http
from src.db.models.users import User
from src.dependencies import get_knowledge_pack_service
from src.schemas.knowledge_pack import KnowledgePackCreate, KnowledgePackRead
from src.services.knowledge_pack_service import KnowledgePackService

router = APIRouter(
    prefix="/knowledge-packs",
    tags=["knowledge-packs"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[KnowledgePackRead])
async def get_packs(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_archived: bool = False,
    actor: User = Depends(get_current_user),
    service: KnowledgePackService = Depends(get_knowledge_pack_service),
):
    try:
        packs = await service.list_packs(
            actor, limit=limit, offset=offset, include_archived=include_archived
        )
        return [KnowledgePackRead.model_validate(p) for p in packs]
    except ValueError as e:
        raise to_http(e)


@router.post(
    "",
    response_model=KnowledgePackRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_pack(
    body: KnowledgePackCreate,
    actor: User = Depends(get_current_user),
    service: KnowledgePackService = Depends(get_knowledge_pack_service),
):
    try:
        pack = await service.create_pack(
            actor, body.name, body.domain_id, body.description, body.slug
        )
        return KnowledgePackRead.model_validate(pack)
    except ValueError as e:
        raise to_http(e)


@router.get("/by-domain/{domain_id}", response_model=list[KnowledgePackRead])
async def get_packs_by_domain(
    domain_id: int,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    actor: User = Depends(get_current_user),
    service: KnowledgePackService = Depends(get_knowledge_pack_service),
):
    try:
        packs = await service.get_packs_by_domain(actor, domain_id, limit=limit, offset=offset)
        return [KnowledgePackRead.model_validate(p) for p in packs]
    except ValueError as e:
        raise to_http(e)


@router.get("/{slug}", response_model=KnowledgePackRead)
async def get_pack_by_slug(
    slug: str,
    actor: User = Depends(get_current_user),
    service: KnowledgePackService = Depends(get_knowledge_pack_service),
):
    try:
        pack = await service.get_pack_by_slug(actor, slug)
        return KnowledgePackRead.model_validate(pack)
    except ValueError as e:
        raise to_http(e)


@router.post(
    "/{pack_id}/archive",
    response_model=KnowledgePackRead,
    dependencies=[Depends(require_admin)],
)
async def archive_pack(
    pack_id: int,
    actor: User = Depends(get_current_user),
    service: KnowledgePackService = Depends(get_knowledge_pack_service),
):
    try:
        pack = await service.archive_pack(actor, pack_id)
        return KnowledgePackRead.model_validate(pack)
    except ValueError as e:
        raise to_http(e)


@router.post(
    "/{pack_id}/restore",
    response_model=KnowledgePackRead,
    dependencies=[Depends(require_admin)],
)
async def restore_pack(
    pack_id: int,
    actor: User = Depends(get_current_user),
    service: KnowledgePackService = Depends(get_knowledge_pack_service),
):
    try:
        pack = await service.restore_pack(actor, pack_id)
        return KnowledgePackRead.model_validate(pack)
    except ValueError as e:
        raise to_http(e)