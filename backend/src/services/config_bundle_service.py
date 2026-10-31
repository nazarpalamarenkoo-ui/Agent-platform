from typing import Optional, Sequence

from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.repositories.agent_profile_repo import AgentProfileRepository
from src.db.models.config_bundles import ConfigBundle
from src.db.models.skills import Skill
from src.db.models.tools_definition import ToolDefinition
from src.db.models.knowledge_packs import KnowledgePack
from src.services.errors import ConflictError, NotFoundError

UNAVAILABLE = "One or more selected items are unavailable"
INHERITED = "Items inherited from the agent profile cannot be removed"


def _unique(ids: Optional[Sequence[int]]) -> list[int]:
    return list(dict.fromkeys(ids or []))


class ConfigBundleService:

    def __init__(
        self,
        config_bundle_repo: ConfigBundleRepository,
        skill_repo: SkillRepository,
        tool_repo: ToolDefinitionRepository,
        knowledge_pack_repo: KnowledgePackRepository,
        agent_profile_repo: AgentProfileRepository,
    ):
        self.config_bundle_repo = config_bundle_repo
        self.skill_repo = skill_repo
        self.tool_repo = tool_repo
        self.knowledge_pack_repo = knowledge_pack_repo
        self.agent_profile_repo = agent_profile_repo

    async def create_bundle(
        self,
        user_id: int,
        agent_id: int,
        name: str,
        description: str,
        skill_ids: list[int],
        tool_ids: list[int],
        knowledge_pack_ids: list[int] | None = None,
    ) -> ConfigBundle:
        name = self._clean_name(name)

        profile = await self.agent_profile_repo.get_active(agent_id)
        if profile is None:
            raise NotFoundError("Agent profile not found")

        await self._ensure_name_free(user_id, name)

        skills = await self._resolve_skills(user_id, skill_ids)
        tools = await self._resolve_tools(user_id, tool_ids)
        packs = await self._resolve_packs(knowledge_pack_ids)

        inherited_skill_ids = {s.id for s in profile.skills}
        inherited_tool_ids = {t.id for t in profile.tools}

        bundle = await self.config_bundle_repo.create(
            user_id=user_id,
            agent_id=profile.id,
            name=name,
            description=description,
        )

        for skill in skills:
            if skill.id not in inherited_skill_ids:
                await self.config_bundle_repo.add_skill(bundle, skill)
        for tool in tools:
            if tool.id not in inherited_tool_ids:
                await self.config_bundle_repo.add_tool(bundle, tool)
        for pack in packs:
            await self.config_bundle_repo.add_knowledge_pack(bundle, pack)

        return await self._load_owned(bundle.id, user_id)
    
    async def create_custom_agent(
        self,
        user_id: int,
        name: str,
        description: str,
        skill_ids: list[int] | None = None,
        tool_ids: list[int] | None = None,
        knowledge_pack_ids: list[int] | None = None,
    ) -> ConfigBundle:
        neutral = await self.agent_profile_repo.get_neutral()
        if neutral is None:
            raise NotFoundError("Neutral agent profile is not configured")
        return await self.create_bundle(
            user_id=user_id,
            agent_id=neutral.id,
            name=name,
            description=description,
            skill_ids=skill_ids or [],
            tool_ids=tool_ids or [],
            knowledge_pack_ids=knowledge_pack_ids or [],
        )
        
    async def create_from_agent(
        self,
        user_id: int,
        agent_id: int,
        name: str,
        description: str,
    ) -> ConfigBundle:
        return await self.create_bundle(
            user_id=user_id,
            agent_id=agent_id,
            name=name,
            description=description,
            skill_ids=[],
            tool_ids=[],
            knowledge_pack_ids=[],
        )

    async def clone_bundle(
        self,
        bundle_id: int,
        user_id: int,
        name: str,
        description: str | None = None,
    ) -> ConfigBundle:
        original = await self._load_owned(bundle_id, user_id)
        name = self._clean_name(name)
        await self._ensure_name_free(user_id, name)

        cloned = await self.config_bundle_repo.create(
            user_id=user_id,
            agent_id=original.agent_id,
            name=name,
            description=original.description if description is None else description,
        )

        for skill in list(original.skills):
            await self.config_bundle_repo.add_skill(cloned, skill)
        for tool in list(original.tools):
            await self.config_bundle_repo.add_tool(cloned, tool)
        for pack in list(original.knowledge_packs):
            await self.config_bundle_repo.add_knowledge_pack(cloned, pack)

        return await self._load_owned(cloned.id, user_id)

    async def get_bundle(self, bundle_id: int, user_id: int) -> ConfigBundle:
        return await self._load_owned(bundle_id, user_id)

    async def get_user_bundles(
        self,
        user_id: int,
        agent_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConfigBundle]:
        if agent_id is not None:
            return await self.config_bundle_repo.get_for_user_and_agent(user_id, agent_id)
        return await self.config_bundle_repo.list_for_user(user_id, limit=limit, offset=offset)

    async def update_bundle(
        self,
        bundle_id: int,
        user_id: int,
        name: str | None = None,
        description: str | None = None,
    ) -> ConfigBundle:
        bundle = await self._load_owned(bundle_id, user_id)
        changes: dict = {}

        if name is not None:
            name = self._clean_name(name)
            if name != bundle.name:
                await self._ensure_name_free(user_id, name, exclude_id=bundle.id)
                changes["name"] = name
        if description is not None and description != bundle.description:
            changes["description"] = description

        if changes:
            await self.config_bundle_repo.update(bundle, **changes)

        return await self._load_owned(bundle_id, user_id)

    async def delete_bundle(self, bundle_id: int, user_id: int) -> None:
        bundle = await self._load_owned(bundle_id, user_id)
        await self.config_bundle_repo.delete(bundle)

    async def add_to_bundle(
        self,
        bundle_id: int,
        user_id: int,
        skill_ids: list[int] | None = None,
        tool_ids: list[int] | None = None,
        knowledge_pack_ids: list[int] | None = None,
    ) -> ConfigBundle:
        bundle = await self._load_owned(bundle_id, user_id)
        profile = await self.agent_profile_repo.admin_get_by_id(bundle.agent_id)
        if profile is None:
            raise NotFoundError("Agent profile not found")

        skills = await self._resolve_skills(user_id, skill_ids)
        tools = await self._resolve_tools(user_id, tool_ids)
        packs = await self._resolve_packs(knowledge_pack_ids)

        inherited_skill_ids = {s.id for s in profile.skills}
        inherited_tool_ids = {t.id for t in profile.tools}

        for skill in skills:
            if skill.id not in inherited_skill_ids:
                await self.config_bundle_repo.add_skill(bundle, skill)
        for tool in tools:
            if tool.id not in inherited_tool_ids:
                await self.config_bundle_repo.add_tool(bundle, tool)
        for pack in packs:
            await self.config_bundle_repo.add_knowledge_pack(bundle, pack)

        return await self._load_owned(bundle_id, user_id)

    async def remove_from_bundle(
        self,
        bundle_id: int,
        user_id: int,
        skill_ids: list[int] | None = None,
        tool_ids: list[int] | None = None,
        knowledge_pack_ids: list[int] | None = None,
    ) -> ConfigBundle:
        bundle = await self._load_owned(bundle_id, user_id)
        profile = await self.agent_profile_repo.admin_get_by_id(bundle.agent_id)
        if profile is None:
            raise NotFoundError("Agent profile not found")

        own_skills = {s.id: s for s in bundle.skills}
        own_tools = {t.id: t for t in bundle.tools}
        own_packs = {p.id: p for p in bundle.knowledge_packs}
        inherited_skill_ids = {s.id for s in profile.skills}
        inherited_tool_ids = {t.id for t in profile.tools}

        skills_to_remove: list[Skill] = []
        for skill_id in _unique(skill_ids):
            if skill_id in own_skills:
                skills_to_remove.append(own_skills[skill_id])
            elif skill_id in inherited_skill_ids:
                raise ConflictError(INHERITED)

        tools_to_remove: list[ToolDefinition] = []
        for tool_id in _unique(tool_ids):
            if tool_id in own_tools:
                tools_to_remove.append(own_tools[tool_id])
            elif tool_id in inherited_tool_ids:
                raise ConflictError(INHERITED)

        packs_to_remove: list[KnowledgePack] = [
            own_packs[pack_id] for pack_id in _unique(knowledge_pack_ids) if pack_id in own_packs
        ]

        for skill in skills_to_remove:
            await self.config_bundle_repo.remove_skill(bundle, skill)
        for tool in tools_to_remove:
            await self.config_bundle_repo.remove_tool(bundle, tool)
        for pack in packs_to_remove:
            await self.config_bundle_repo.remove_knowledge_pack(bundle, pack)

        return await self._load_owned(bundle_id, user_id)

    async def _load_owned(self, bundle_id: int, user_id: int) -> ConfigBundle:
        bundle = await self.config_bundle_repo.get_owned(bundle_id, user_id)
        if bundle is None:
            raise NotFoundError("Config bundle not found")
        return bundle

    @staticmethod
    def _clean_name(name: str) -> str:
        cleaned = (name or "").strip()
        if not cleaned:
            raise ValueError("Bundle name must not be empty")
        return cleaned

    async def _ensure_name_free(
        self, user_id: int, name: str, exclude_id: int | None = None
    ) -> None:
        existing = await self.config_bundle_repo.get_by_user_and_name(user_id, name)
        if existing is not None and existing.id != exclude_id:
            raise ConflictError(f"Bundle '{name}' already exists")

    async def _resolve_skills(self, user_id: int, skill_ids: Optional[Sequence[int]]) -> list[Skill]:
        ids = _unique(skill_ids)
        if not ids:
            return []
        found = await self.skill_repo.get_visible_many(ids, user_id)
        if len(found) != len(ids):
            raise NotFoundError(UNAVAILABLE)
        return found

    async def _resolve_tools(self, user_id, tool_ids):
        ids = _unique(tool_ids)
        if not ids:
            return []
        found = await self.tool_repo.get_visible_many(ids, user_id)
        if len(found) != len(ids):
            raise NotFoundError(UNAVAILABLE)
        return found

    async def _resolve_packs(self, pack_ids: Optional[Sequence[int]]) -> list[KnowledgePack]:
        ids = _unique(pack_ids)
        if not ids:
            return []
        found = await self.knowledge_pack_repo.get_active_many(ids)
        if len(found) != len(ids):
            raise NotFoundError(UNAVAILABLE)
        return found