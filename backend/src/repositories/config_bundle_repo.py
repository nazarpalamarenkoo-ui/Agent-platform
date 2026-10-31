from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.config_bundles import ConfigBundle
from src.db.models.config_bundle_skills import ConfigBundleSkill
from src.db.models.config_bunlde_tools import ConfigBundleTool
from src.db.models.agent_profile_skills import AgentProfileSkill
from src.db.models.agent_profile_tools import AgentProfileTool
from src.db.models.skills import Skill
from src.db.models.tools_definition import ToolDefinition
from src.db.models.knowledge_packs import KnowledgePack

from src.repositories.base_repo import BaseRepository


class ConfigBundleRepository(BaseRepository[ConfigBundle]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, ConfigBundle)

    def _with_relations(self, stmt):
        return stmt.options(
            selectinload(ConfigBundle.skills),
            selectinload(ConfigBundle.tools),
            selectinload(ConfigBundle.knowledge_packs),
        )

    async def get_owned(self, bundle_id: int, user_id: int) -> Optional[ConfigBundle]:
        result = await self.session.execute(
            self._with_relations(
                select(ConfigBundle).where(
                    ConfigBundle.id == bundle_id, ConfigBundle.user_id == user_id
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: int, limit: int = 100, offset: int = 0
    ) -> list[ConfigBundle]:
        result = await self.session.execute(
            self._with_relations(
                select(ConfigBundle)
                .where(ConfigBundle.user_id == user_id)
                .order_by(ConfigBundle.created_at.desc(), ConfigBundle.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return list(result.scalars().all())

    async def get_for_user_and_agent(self, user_id: int, agent_id: int) -> list[ConfigBundle]:
        result = await self.session.execute(
            self._with_relations(
                select(ConfigBundle).where(
                    ConfigBundle.user_id == user_id,
                    ConfigBundle.agent_id == agent_id,
                )
            )
        )
        return list(result.scalars().all())

    async def get_by_user_and_name(self, user_id: int, name: str) -> Optional[ConfigBundle]:
        result = await self.session.execute(
            select(ConfigBundle).where(
                ConfigBundle.user_id == user_id, ConfigBundle.name == name
            )
        )
        return result.scalar_one_or_none()

    async def get_unscoped_with_relations(self, config_id: int) -> Optional[ConfigBundle]:

        result = await self.session.execute(
            self._with_relations(
                select(ConfigBundle).where(ConfigBundle.id == config_id)
            )
        )
        return result.scalar_one_or_none()

    async def list_user_ids_with_skill(self, skill_id: int) -> list[int]:
        direct = (
            select(ConfigBundle.user_id)
            .join(
                ConfigBundleSkill,
                ConfigBundleSkill.config_bundle_id == ConfigBundle.id,
            )
            .where(ConfigBundleSkill.skill_id == skill_id)
        )
        via_profile = (
            select(ConfigBundle.user_id)
            .join(
                AgentProfileSkill,
                AgentProfileSkill.agent_id == ConfigBundle.agent_id,
            )
            .where(AgentProfileSkill.skill_id == skill_id)
        )
        result = await self.session.execute(direct.union(via_profile))
        return [row[0] for row in result.all()]

    async def list_user_ids_with_tool(self, tool_id: int) -> list[int]:
        direct = (
            select(ConfigBundle.user_id)
            .join(
                ConfigBundleTool,
                ConfigBundleTool.config_bundle_id == ConfigBundle.id,
            )
            .where(ConfigBundleTool.tool_id == tool_id)
        )
        via_profile = (
            select(ConfigBundle.user_id)
            .join(
                AgentProfileTool,
                AgentProfileTool.agent_id == ConfigBundle.agent_id,
            )
            .where(AgentProfileTool.tool_id == tool_id)
        )
        result = await self.session.execute(direct.union(via_profile))
        return [row[0] for row in result.all()]

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

    async def add_knowledge_pack(self, config: ConfigBundle, pack: KnowledgePack) -> ConfigBundle:
        await self.session.refresh(config, attribute_names=["knowledge_packs"])
        if pack in config.knowledge_packs:
            return config
        config.knowledge_packs.append(pack)
        await self.session.flush()
        return config

    async def remove_knowledge_pack(self, config: ConfigBundle, pack: KnowledgePack) -> ConfigBundle:
        await self.session.refresh(config, attribute_names=["knowledge_packs"])
        if pack not in config.knowledge_packs:
            return config
        config.knowledge_packs.remove(pack)
        await self.session.flush()
        return config