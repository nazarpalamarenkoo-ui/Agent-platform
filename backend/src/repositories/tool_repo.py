from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import and_, func, or_, select
from src.db.enums.tool_visibility import ToolVisibility
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.base_repo import BaseRepository
from src.db.models.tools_definition import ToolDefinition
from src.db.models.tool_domain import ToolDomain
from src.db.models.tool_usage_events import ToolUsageEvent
from src.db.models.knowledge_domains import KnowledgeDomain
from src.db.models.config_bundles import ConfigBundle
from src.db.models.config_bunlde_tools import ConfigBundleTool
from src.db.models.agent_profile_tools import AgentProfileTool

def _visible_to(viewer_id: int):
    return and_(
        ToolDefinition.archived_at.is_(None),
        or_(
            ToolDefinition.visibility == ToolVisibility.GLOBAL,
            ToolDefinition.owner_id == viewer_id,
        ),
    )
    
def _in_effective_set(bundle_id: int):
    direct = select(ConfigBundleTool.tool_id).where(
        ConfigBundleTool.config_bundle_id == bundle_id
    )
    via_profile = (
        select(AgentProfileTool.tool_id)
        .join(ConfigBundle, ConfigBundle.agent_id == AgentProfileTool.agent_id)
        .where(ConfigBundle.id == bundle_id)
    )
    return or_(
        ToolDefinition.id.in_(direct), ToolDefinition.id.in_(via_profile)
    )


class ToolDefinitionRepository(BaseRepository[ToolDefinition]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, ToolDefinition)

    async def get_by_id(self, entity_id: int):  # type: ignore[override]
        raise NotImplementedError(
            "ToolDefinitionRepository.get_by_id is disabled: use get_active / "
            "get_for_bundle or admin_get_by_id."
        )

    async def get_all(self, limit: int = 100, offset: int = 0):  # type: ignore[override]
        raise NotImplementedError(
            "ToolDefinitionRepository.get_all is disabled: use list_active or admin_list."
        )

    async def list_active(self, limit: int = 100, offset: int = 0, domain_id: int | None = None):
        stmt = select(ToolDefinition).where(
            ToolDefinition.archived_at.is_(None),
            ToolDefinition.owner_id.is_(None),
        )
        if domain_id is not None:
            stmt = stmt.where(ToolDefinition.id.in_(
                select(ToolDomain.tool_id).where(ToolDomain.domain_id == domain_id)))
        stmt = stmt.order_by(ToolDefinition.tool_name, ToolDefinition.id)
        result = await self.session.execute(stmt.limit(limit).offset(offset))
        return list(result.scalars().all())

    async def get_active(self, tool_id: int) -> Optional[ToolDefinition]:
        result = await self.session.execute(
            select(ToolDefinition).where(
                ToolDefinition.id == tool_id,
                ToolDefinition.archived_at.is_(None),
                ToolDefinition.owner_id.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_active_many(self, tool_ids: Sequence[int]) -> list[ToolDefinition]:
        return await self.get_global_active_many(tool_ids)

    async def list_visible(self, viewer_id: int, limit=100, offset=0, domain_id=None):
        stmt = select(ToolDefinition).where(_visible_to(viewer_id))
        if domain_id is not None:
            stmt = stmt.where(ToolDefinition.id.in_(
                select(ToolDomain.tool_id).where(ToolDomain.domain_id == domain_id)))
        stmt = stmt.order_by(ToolDefinition.tool_name, ToolDefinition.id).limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_visible(self, tool_id: int, viewer_id: int):
        result = await self.session.execute(
            select(ToolDefinition).where(_visible_to(viewer_id), ToolDefinition.id == tool_id))
        return result.scalar_one_or_none()

    async def get_visible_many(self, tool_ids: Sequence[int], viewer_id: int):
        ids = list(set(tool_ids))
        if not ids:
            return []
        result = await self.session.execute(
            select(ToolDefinition).where(_visible_to(viewer_id), ToolDefinition.id.in_(ids)))
        return list(result.scalars().all())

    async def get_global_active_many(self, tool_ids: Sequence[int]):
        ids = list(set(tool_ids))
        if not ids:
            return []
        result = await self.session.execute(
            select(ToolDefinition).where(
                ToolDefinition.id.in_(ids),
                ToolDefinition.visibility == ToolVisibility.GLOBAL,
                ToolDefinition.archived_at.is_(None)))
        return list(result.scalars().all())

    async def list_candidates(self, viewer_id: int):
        result = await self.session.execute(
            select(ToolDefinition.id, ToolDefinition.tool_name, ToolDefinition.description)
            .where(_visible_to(viewer_id)).order_by(ToolDefinition.id))
        return list(result.all())

    async def admin_list_global(self, limit=100, offset=0, include_archived=False):
        stmt = select(ToolDefinition).where(ToolDefinition.visibility == ToolVisibility.GLOBAL)
        if not include_archived:
            stmt = stmt.where(ToolDefinition.archived_at.is_(None))
        stmt = stmt.order_by(ToolDefinition.tool_name, ToolDefinition.id).limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_global_by_name(self, name: str):
        result = await self.session.execute(select(ToolDefinition).where(
            ToolDefinition.tool_name == name, ToolDefinition.owner_id.is_(None)))
        return result.scalar_one_or_none()

    async def get_owned_by_name(self, name: str, owner_id: int):
        result = await self.session.execute(select(ToolDefinition).where(
            ToolDefinition.tool_name == name, ToolDefinition.owner_id == owner_id))
        return result.scalar_one_or_none()

    async def get_owned_by_id(self, tool_id: int, owner_id: int):
        result = await self.session.execute(select(ToolDefinition).where(
            ToolDefinition.id == tool_id, ToolDefinition.owner_id == owner_id))
        return result.scalar_one_or_none()

    async def list_owned(self, owner_id: int, limit=100, offset=0, include_archived=False):
        stmt = select(ToolDefinition).where(ToolDefinition.owner_id == owner_id)
        if not include_archived:
            stmt = stmt.where(ToolDefinition.archived_at.is_(None))
        stmt = stmt.order_by(ToolDefinition.tool_name, ToolDefinition.id).limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_owned_active(self, owner_id: int) -> int:
        result = await self.session.execute(select(func.count(ToolDefinition.id)).where(
            ToolDefinition.owner_id == owner_id, ToolDefinition.archived_at.is_(None)))
        return int(result.scalar_one())

    async def count_candidates(self, viewer_id: int) -> int:
        result = await self.session.execute(
            select(func.count(ToolDefinition.id)).where(_visible_to(viewer_id))
        )
        return int(result.scalar_one())

    async def list_for_bundle(self, bundle_id: int) -> list[ToolDefinition]:
        result = await self.session.execute(
            select(ToolDefinition)
            .where(_in_effective_set(bundle_id))
            .order_by(ToolDefinition.tool_name, ToolDefinition.id)
        )
        return list(result.scalars().all())

    async def get_for_bundle(
        self, tool_id: int, bundle_id: int
    ) -> Optional[ToolDefinition]:
        result = await self.session.execute(
            select(ToolDefinition).where(
                ToolDefinition.id == tool_id, _in_effective_set(bundle_id)
            )
        )
        return result.scalar_one_or_none()

    async def list_manifest_for_bundle(self, bundle_id: int):
        result = await self.session.execute(
            select(
                ToolDefinition.id,
                ToolDefinition.tool_name,
                ToolDefinition.url,
                ToolDefinition.auth_type,
                ToolDefinition.owner_id,
                ToolDefinition.archived_at,
            )
            .where(_in_effective_set(bundle_id))
            .order_by(ToolDefinition.id)
        )
        return list(result.all())

    async def admin_get_by_id(self, tool_id: int) -> Optional[ToolDefinition]:
        result = await self.session.execute(
            select(ToolDefinition).where(ToolDefinition.id == tool_id)
        )
        return result.scalar_one_or_none()

    async def admin_list(
        self, limit: int = 100, offset: int = 0, include_archived: bool = False
    ) -> list[ToolDefinition]:
        stmt = select(ToolDefinition)
        if not include_archived:
            stmt = stmt.where(ToolDefinition.archived_at.is_(None))
        stmt = stmt.order_by(ToolDefinition.tool_name, ToolDefinition.id)
        result = await self.session.execute(stmt.limit(limit).offset(offset))
        return list(result.scalars().all())

    async def admin_get_by_name(self, tool_name: str) -> Optional[ToolDefinition]:
        return await self.get_global_by_name(tool_name)

    async def archive(self, tool: ToolDefinition) -> ToolDefinition:
        if tool.archived_at is None:
            tool.archived_at = datetime.now(timezone.utc)
            await self.session.flush()
        return tool

    async def restore(self, tool: ToolDefinition) -> ToolDefinition:
        if tool.archived_at is not None:
            tool.archived_at = None
            await self.session.flush()
        return tool

    async def record_selection(
        self,
        tool_id: int,
        user_id: int,
        config_bundle_id: int | None = None,
    ) -> Optional[ToolDefinition]:
        self.session.add(
            ToolUsageEvent(
                tool_id=tool_id,
                user_id=user_id,
                config_bundle_id=config_bundle_id,
            )
        )
        tool = await self.admin_get_by_id(tool_id)
        if tool is not None:
            tool.tool_selected_freq += 1
        await self.session.flush()
        return tool

    async def add_domain(
        self, tool: ToolDefinition, domain: KnowledgeDomain
    ) -> ToolDefinition:
        await self.session.refresh(tool, attribute_names=["domains"])
        if domain not in tool.domains:
            tool.domains.append(domain)
        await self.session.flush()
        return tool