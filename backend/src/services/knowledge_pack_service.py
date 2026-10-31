from src.db.models.knowledge_packs import KnowledgePack
from src.db.models.users import User
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.services.errors import ConflictError, NotFoundError
from src.services.permissions import require_admin


class KnowledgePackService:

    def __init__(self, pack_repo: KnowledgePackRepository, domain_repo: KnowledgeDomainRepository):
        self.pack_repo = pack_repo
        self.domain_repo = domain_repo

    async def create_pack(
        self,
        actor: User,
        name: str,
        domain_id: int,
        description: str,
        slug: str,
    ) -> KnowledgePack:
        require_admin(actor)

        domain = await self.domain_repo.get_by_id(domain_id)
        if domain is None:
            raise NotFoundError(f"Domain with id={domain_id} does not exist")

        if await self.pack_repo.get_by_name_in_domain(domain_id, name) is not None:
            raise ConflictError(f"Pack with name='{name}' already exists in domain {domain_id}")

        if await self.pack_repo.get_by_slug(slug) is not None:
            raise ConflictError(f"Pack with slug='{slug}' already exists")

        return await self.pack_repo.create(
            name=name,
            domain_id=domain_id,
            description=description,
            slug=slug,
        )

    async def list_packs(
        self,
        actor: User,
        limit: int = 100,
        offset: int = 0,
        include_archived: bool = False,
    ) -> list[KnowledgePack]:
        if include_archived:
            require_admin(actor)
            return list(await self.pack_repo.get_all(limit=limit, offset=offset))
        return await self.pack_repo.list_active(limit=limit, offset=offset)

    async def get_pack_by_slug(self, actor: User, slug: str) -> KnowledgePack:
        pack = await self.pack_repo.get_by_slug(slug)
        if pack is None or (pack.archived_at is not None and not actor.is_admin):
            raise NotFoundError(f"Pack with slug='{slug}' not found")
        return pack

    async def get_packs_by_domain(
        self, actor: User, domain_id: int, limit: int = 100, offset: int = 0
    ) -> list[KnowledgePack]:
        return await self.pack_repo.list_active(limit=limit, offset=offset, domain_id=domain_id)

    async def get_pack_with_documents(self, actor: User, pack_id: int) -> KnowledgePack:
        require_admin(actor)
        pack = await self.pack_repo.get_by_id_with_documents(pack_id)
        if pack is None:
            raise NotFoundError(f"Pack {pack_id} not found")
        return pack

    async def archive_pack(self, actor: User, pack_id: int) -> KnowledgePack:
        require_admin(actor)
        pack = await self._get(pack_id)
        return await self.pack_repo.archive(pack)

    async def restore_pack(self, actor: User, pack_id: int) -> KnowledgePack:
        require_admin(actor)
        pack = await self._get(pack_id)
        return await self.pack_repo.restore(pack)

    async def _get(self, pack_id: int) -> KnowledgePack:
        pack = await self.pack_repo.get_by_id(pack_id)
        if pack is None:
            raise NotFoundError(f"Pack {pack_id} not found")
        return pack