from src.catalog.hint.models import CandidateKind, CatalogCandidate
from src.repositories.agent_profile_repo import AgentProfileRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository


class CandidateCollector:
    def __init__(
        self,
        skill_repo: SkillRepository,
        tool_repo: ToolDefinitionRepository,
        pack_repo: KnowledgePackRepository,
        agent_repo: AgentProfileRepository,
    ):
        self.skill_repo = skill_repo
        self.tool_repo = tool_repo
        self.pack_repo = pack_repo
        self.agent_repo = agent_repo

    async def collect(self, viewer_id: int) -> list[CatalogCandidate]:
        profiles = await self._collect_profiles()
        skills = await self._collect_skills(viewer_id)
        tools = await self._collect_tools(viewer_id)
        packs = await self._collect_packs()
        return profiles + skills + tools + packs

    async def _collect_profiles(self) -> list[CatalogCandidate]:
        rows = await self.agent_repo.list_candidates()
        return [
            CatalogCandidate(
                key=CatalogCandidate.build_key(CandidateKind.PROFILE, row.id),
                kind=CandidateKind.PROFILE,
                entity_id=row.id,
                name=row.agent_name,
                description=row.description,
            )
            for row in rows
        ]

    async def _collect_skills(self, viewer_id: int) -> list[CatalogCandidate]:
        rows = await self.skill_repo.list_candidates(viewer_id)
        return [
            CatalogCandidate(
                key=CatalogCandidate.build_key(CandidateKind.SKILL, row.id),
                kind=CandidateKind.SKILL,
                entity_id=row.id,
                name=row.skill_name,
                description=row.description,
            )
            for row in rows
        ]

    async def _collect_tools(self, viewer_id: int) -> list[CatalogCandidate]:
        rows = await self.tool_repo.list_candidates(viewer_id)
        return [
            CatalogCandidate(
                key=CatalogCandidate.build_key(CandidateKind.TOOL, row.id),
                kind=CandidateKind.TOOL,
                entity_id=row.id,
                name=row.tool_name,
                description=row.description,
            )
            for row in rows
        ]

    async def _collect_packs(self) -> list[CatalogCandidate]:
        rows = await self.pack_repo.list_candidates()
        return [
            CatalogCandidate(
                key=CatalogCandidate.build_key(CandidateKind.PACK, row.id),
                kind=CandidateKind.PACK,
                entity_id=row.id,
                name=row.name,
                description=row.description,
            )
            for row in rows
        ]