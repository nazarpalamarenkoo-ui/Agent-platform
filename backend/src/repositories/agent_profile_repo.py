from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.repositories.base_repo import BaseRepository

from src.db.models.agent_profiles import AgentProfile
from src.db.models.skills import Skill
from src.db.models.tools_definition import ToolDefinition

class AgentProfileRepository(BaseRepository[AgentProfile]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, AgentProfile)

    async def get_by_id(self, agent_id: int) -> Optional[AgentProfile]:

        result = await self.session.execute(
            select(AgentProfile)
            .options(
                selectinload(AgentProfile.skills),
                selectinload(AgentProfile.tools),
            )
            .where(
                AgentProfile.id == agent_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, agent_name: str) -> Optional[AgentProfile]:
        result = await self.session.execute(
            select(AgentProfile)
            .options(
                selectinload(AgentProfile.skills),
                selectinload(AgentProfile.tools),
            )
            .where(AgentProfile.agent_name == agent_name)
        )
        return result.scalar_one_or_none()

    async def add_skill(self, profile: AgentProfile, skill: Skill) -> AgentProfile:
        await self.session.refresh(profile, attribute_names=["skills"])
        if skill in profile.skills:
            return profile
        profile.skills.append(skill)
        await self.session.flush()
        return profile

    async def remove_skill(self, profile: AgentProfile, skill: Skill) -> AgentProfile:
        await self.session.refresh(profile, attribute_names=["skills"])
        if skill not in profile.skills:
            return profile
        profile.skills.remove(skill)
        await self.session.flush()
        return profile

    async def add_tool(self, profile: AgentProfile, tool: ToolDefinition) -> AgentProfile:
        await self.session.refresh(profile, attribute_names=["tools"])
        if tool in profile.tools:
            return profile
        profile.tools.append(tool)
        await self.session.flush()
        return profile

    async def remove_tool(self, profile: AgentProfile, tool: ToolDefinition) -> AgentProfile:
        await self.session.refresh(profile, attribute_names=["tools"])
        if tool not in profile.tools:
            return profile
        profile.tools.remove(tool)
        await self.session.flush()
        return profile