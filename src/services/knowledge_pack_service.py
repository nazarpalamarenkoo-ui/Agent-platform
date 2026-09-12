from src.db.models.knowledge_packs import KnowledgePack
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository

class KnowledgePackService:
    
    def __init__(self, pack_repo: KnowledgePackRepository, domain_repo: KnowledgeDomainRepository):
        self.pack_repo = pack_repo
        self.domain_repo = domain_repo
        
    async def create_pack(self, name: str, domain_id: int, description: str, slug: str) -> KnowledgePack:
    
        domain = await self.domain_repo.get_by_id(domain_id)
        if domain is None:
            raise ValueError(f"Domain with id={domain_id} does not exist")
        
        existing_pack = await self.pack_repo.get_by_name_in_domain(domain_id, name)
        if existing_pack is not None:
            raise ValueError(f"Pack with name='{name}' already exists in domain {domain_id}")
        
        existing_slug = await self.pack_repo.get_by_slug(slug)
        if existing_slug is not None:
            raise ValueError(f"Pack with slug='{slug}' already exists")
        
        return await self.pack_repo.create(
            name=name,
            domain_id=domain_id,
            description=description,
            slug=slug,
        )

    async def get_pack_by_slug(self, slug: str) -> KnowledgePack:
    
        pack = await self.pack_repo.get_by_slug(slug)
        
        if pack is None:
            raise ValueError(f"Pack with slug='{slug}' not found")
        return pack
        
    async def get_packs_by_domain(self, domain_id: int) -> list[KnowledgePack]:
        
        return await self.pack_repo.list_by_domain(domain_id)
        
    async def get_pack_with_documents(self, pack_id: int) -> KnowledgePack:
        
        pack = await self.pack_repo.get_by_id_with_documents(pack_id)
        
        if pack is None:
            raise ValueError(f"Pack {pack_id} not found") 
        
        return pack