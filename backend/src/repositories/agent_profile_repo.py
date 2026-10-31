from datetime import datetime, timezone
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

    async def get_by_id(self, entity_id: int):  # type: ignore[override]
        raise NotImplementedError("Use get_active or admin_get_by_id")

    async def get_all(self, limit: int = 100, offset: int = 0):  # type: ignore[override]
        raise NotImplementedError("Use list_active or admin_list")

    def _with_content(self, stmt):
        return stmt.options(
            selectinload(AgentProfile.skills),
            selectinload(AgentProfile.tools),
        )

    async def list_active(self, limit: int = 100, offset: int = 0) -> list[AgentProfile]:
        result = await self.session.execute(
            self._with_content(
                select(AgentProfile)
                .where(AgentProfile.archived_at.is_(None))
                .order_by(AgentProfile.agent_name, AgentProfile.id)
                .limit(limit)
                .offset(offset)
            )
        )
        return list(result.scalars().all())

    async def get_active(self, agent_id: int) -> Optional[AgentProfile]:
        result = await self.session.execute(
            self._with_content(
                select(AgentProfile).where(
                    AgentProfile.id == agent_id,
                    AgentProfile.archived_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_candidates(self):
        result = await self.session.execute(
            select(
                AgentProfile.id, AgentProfile.agent_name, AgentProfile.description
            )
            .where(AgentProfile.archived_at.is_(None))
            .order_by(AgentProfile.id)
        )
        return list(result.all())

    async def get_neutral(self) -> Optional[AgentProfile]:
        result = await self.session.execute(
            self._with_content(
                select(AgentProfile).where(
                    AgentProfile.is_neutral.is_(True),
                    AgentProfile.archived_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def admin_get_by_id(self, agent_id: int) -> Optional[AgentProfile]:
        result = await self.session.execute(
            self._with_content(
                select(AgentProfile).where(AgentProfile.id == agent_id)
            )
        )
        return result.scalar_one_or_none()

    async def admin_list(
        self, limit: int = 100, offset: int = 0, include_archived: bool = False
    ) -> list[AgentProfile]:
        stmt = select(AgentProfile)
        if not include_archived:
            stmt = stmt.where(AgentProfile.archived_at.is_(None))
        stmt = stmt.order_by(AgentProfile.agent_name, AgentProfile.id)
        result = await self.session.execute(
            self._with_content(stmt.limit(limit).offset(offset))
        )
        return list(result.scalars().all())

    async def admin_get_by_name(self, agent_name: str) -> Optional[AgentProfile]:
        result = await self.session.execute(
            self._with_content(
                select(AgentProfile).where(AgentProfile.agent_name == agent_name)
            )
        )
        return result.scalar_one_or_none()

    async def archive(self, profile: AgentProfile) -> AgentProfile:
        if profile.archived_at is None:
            profile.archived_at = datetime.now(timezone.utc)
            await self.session.flush()
        return profile

    async def restore(self, profile: AgentProfile) -> AgentProfile:
        if profile.archived_at is not None:
            profile.archived_at = None
            await self.session.flush()
        return profile

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