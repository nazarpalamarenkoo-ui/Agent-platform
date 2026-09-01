from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.config_bundles import ConfigBundle
from src.db.models.skills import Skill
from src.db.models.tools_definition import ToolDefinition

from src.repositories.base_repo import BaseRepository

class ConfigBundleRepository(BaseRepository[ConfigBundle]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, ConfigBundle)

    async def get_for_user_and_agent(self, user_id: int, agent_id: int) -> list[ConfigBundle]:

        result = await self.session.execute(
            select(ConfigBundle)
            .options(
                selectinload(ConfigBundle.skills),
                selectinload(ConfigBundle.tools),
            )
            .where(
                ConfigBundle.user_id == user_id,
                ConfigBundle.agent_id == agent_id
            )
        )
        return list(result.scalars().all())

    async def add_skill(self, config: ConfigBundle, skill: Skill) -> ConfigBundle:
        await self.session.refresh(config, attribute_names=["skills"])
        if skill in config.skills:
            return config
        config.skills.append(skill)
        await self.session.flush()
        return config

    async def remove_skill(self, config: ConfigBundle, skill: Skill) -> ConfigBundle:
        await self.session.refresh(config, attribute_names=["skills"])
        if skill not in config.skills:
            return config
        config.skills.remove(skill)
        await self.session.flush()
        return config

    async def add_tool(self, config: ConfigBundle, tool: ToolDefinition) -> ConfigBundle:
        await self.session.refresh(config, attribute_names=["tools"])
        if tool in config.tools:
            return config
        config.tools.append(tool)
        await self.session.flush()
        return config

    async def remove_tool(self, config: ConfigBundle, tool: ToolDefinition) -> ConfigBundle:
        await self.session.refresh(config, attribute_names=["tools"])
        if tool not in config.tools:
            return config
        config.tools.remove(tool)
        await self.session.flush()
        return config

    async def get_by_id_with_relations(self, config_id: int) -> Optional[ConfigBundle]:

        result = await self.session.execute(
            select(ConfigBundle)
            .options(
                selectinload(ConfigBundle.skills),
                selectinload(ConfigBundle.tools)
            )
            .where(
                ConfigBundle.id == config_id
            )
        )

        return result.scalar_one_or_none()