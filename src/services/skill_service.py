from src.repositories.skill_repo import SkillRepository
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.db.models.skills import Skill


class SkillService:

    def __init__(
        self,
        skill_repo: SkillRepository,
        domain_repo: KnowledgeDomainRepository,
    ):
        self.skill_repo = skill_repo
        self.domain_repo = domain_repo

    async def create_skill(
        self,
        skill_name: str,
        description: str,
        domain_ids: list[int],
    ) -> Skill:
        existing = await self.skill_repo.get_by_name(skill_name)
        if existing:
            raise ValueError(f"Skill '{skill_name}' already exists")

        skill = await self.skill_repo.create(
            skill_name=skill_name,
            description=description,
        )

        for domain_id in domain_ids:
            domain = await self.domain_repo.get_by_id(domain_id)
            if not domain:
                raise ValueError(f"Domain {domain_id} not found")
            await self.skill_repo.add_domain(skill, domain)

        return skill

    async def get_skills_by_domain(self, domain_id: int) -> list[Skill]:
        return await self.skill_repo.list_by_domain(domain_id)

    async def get_skill(self, skill_id: int) -> Skill:
        skill = await self.skill_repo.get_by_id(skill_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")
        return skill

    async def get_all_skills(self, limit: int = 100, offset: int = 0) -> list[Skill]:
        return list(await self.skill_repo.get_all(limit=limit, offset=offset))