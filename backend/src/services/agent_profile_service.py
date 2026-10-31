from typing import Sequence

from src.db.models.agent_profiles import AgentProfile
from src.db.models.skills import Skill
from src.db.models.tools_definition import ToolDefinition
from src.db.models.users import User
from src.repositories.agent_profile_repo import AgentProfileRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.services.errors import ConflictError, NotFoundError
from src.services.permissions import require_admin

UNAVAILABLE = "One or more selected items are unavailable"


class AgentProfileService:

    def __init__(
        self,
        agent_profile_repo: AgentProfileRepository,
        skill_repo: SkillRepository,
        tool_repo: ToolDefinitionRepository,
    ):
        self.agent_repo = agent_profile_repo
        self.skill_repo = skill_repo
        self.tool_repo = tool_repo

    async def list_profiles(
        self,
        actor: User,
        limit: int = 100,
        offset: int = 0,
        include_archived: bool = False,
    ) -> list[AgentProfile]:
        if include_archived:
            require_admin(actor)
            return await self.agent_repo.admin_list(
                limit=limit, offset=offset, include_archived=True
            )
        return await self.agent_repo.list_active(limit=limit, offset=offset)

    async def get_profile(self, actor: User, agent_id: int) -> AgentProfile:
        profile = await self.agent_repo.get_active(agent_id)
        if profile is None and actor.is_admin:
            profile = await self.agent_repo.admin_get_by_id(agent_id)
        if profile is None:
            raise NotFoundError("Agent profile not found")
        return profile

    async def create_profile(
        self,
        actor: User,
        name: str,
        description: str,
        skill_ids: Sequence[int] | None = None,
        tool_ids: Sequence[int] | None = None,
        is_neutral: bool = False,
    ) -> AgentProfile:
        require_admin(actor)

        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("Profile name must not be empty")

        if await self.agent_repo.admin_get_by_name(clean_name) is not None:
            raise ConflictError(f"Profile '{clean_name}' already exists")

        if is_neutral and await self.agent_repo.get_neutral() is not None:
            raise ConflictError("A neutral profile already exists")

        skills = await self._resolve_skills(skill_ids)
        tools = await self._resolve_tools(tool_ids)

        profile = await self.agent_repo.create(
            agent_name=clean_name,
            description=description,
            is_neutral=is_neutral,
        )
        profile = await self._get(profile.id)

        for skill in skills:
            await self.agent_repo.add_skill(profile, skill)
        for tool in tools:
            await self.agent_repo.add_tool(profile, tool)

        return await self._get(profile.id)

    async def update_profile(
        self,
        actor: User,
        agent_id: int,
        description: str | None = None,
        skill_ids: Sequence[int] | None = None,
        tool_ids: Sequence[int] | None = None,
    ) -> AgentProfile:
        require_admin(actor)
        profile = await self._get(agent_id)

        wanted_skills = await self._resolve_skills(skill_ids) if skill_ids is not None else None
        wanted_tools = await self._resolve_tools(tool_ids) if tool_ids is not None else None

        if description is not None and description != profile.description:
            await self.agent_repo.update(profile, description=description)

        if wanted_skills is not None:
            wanted_ids = {s.id for s in wanted_skills}
            current = {s.id: s for s in profile.skills}
            for skill in wanted_skills:
                if skill.id not in current:
                    await self.agent_repo.add_skill(profile, skill)
            for skill_id, skill in list(current.items()):
                if skill_id not in wanted_ids:
                    await self.agent_repo.remove_skill(profile, skill)

        if wanted_tools is not None:
            wanted_ids = {t.id for t in wanted_tools}
            current_tools = {t.id: t for t in profile.tools}
            for tool in wanted_tools:
                if tool.id not in current_tools:
                    await self.agent_repo.add_tool(profile, tool)
            for tool_id, tool in list(current_tools.items()):
                if tool_id not in wanted_ids:
                    await self.agent_repo.remove_tool(profile, tool)

        return await self._get(agent_id)

    async def archive_profile(self, actor: User, agent_id: int) -> AgentProfile:
        require_admin(actor)
        profile = await self._get(agent_id)
        if profile.is_neutral:
            raise ConflictError("The neutral profile cannot be archived")
        await self.agent_repo.archive(profile)
        return await self._get(agent_id)

    async def restore_profile(self, actor: User, agent_id: int) -> AgentProfile:
        require_admin(actor)
        profile = await self._get(agent_id)
        await self.agent_repo.restore(profile)
        return await self._get(agent_id)

    async def _get(self, agent_id: int) -> AgentProfile:
        profile = await self.agent_repo.admin_get_by_id(agent_id)
        if profile is None:
            raise NotFoundError("Agent profile not found")
        return profile

    async def _resolve_skills(self, skill_ids: Sequence[int] | None) -> list[Skill]:
        ids = list(dict.fromkeys(skill_ids or []))
        if not ids:
            return []
        found = await self.skill_repo.get_global_active_many(ids)
        if len(found) != len(ids):
            raise NotFoundError(UNAVAILABLE)
        return found

    async def _resolve_tools(self, tool_ids: Sequence[int] | None) -> list[ToolDefinition]:
        ids = list(dict.fromkeys(tool_ids or []))
        if not ids:
            return []
        found = await self.tool_repo.get_global_active_many(ids)
        if len(found) != len(ids):
            raise NotFoundError(UNAVAILABLE)
        return found