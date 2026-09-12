from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.db.models.knowledge_domains import KnowledgeDomain

class DomainService:
    
    def __init__(self, domain_repo: KnowledgeDomainRepository):
        
        self.domain_repo = domain_repo
        
    async def create_domain(
        self,
        slug: str,
        name: str,
        description: str,
        parent_domain_id: int | None = None
    ) -> KnowledgeDomain:
        
        if parent_domain_id is not None:
            parent = await self.domain_repo.get_by_id(parent_domain_id)
            if not parent:
                raise ValueError(f"Parent domain {parent_domain_id} not found")

        existing = await self.domain_repo.get_by_slug(slug)
        if existing:
            raise ValueError(f'Domain with slug {slug} already exists')
        
        return await self.domain_repo.create(
            slug=slug,
            name=name,
            description=description,
            parent_domain_id=parent_domain_id
        )
        
    async def get_domain(self, domain_id: int) -> KnowledgeDomain:
        domain = await self.domain_repo.get_by_id(domain_id)
        if not domain:
            raise ValueError(f"Domain {domain_id} not found")
        return domain

    async def get_root_domains(self) -> list[KnowledgeDomain]:
        return await self.domain_repo.get_root_domains()

    async def get_all_domains(self, limit: int = 100, offset: int = 0) -> list[KnowledgeDomain]:
        return list(await self.domain_repo.get_all(limit=limit, offset=offset))