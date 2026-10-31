from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from src.repositories.base_repo import BaseRepository
from src.db.enums.skill_visibility import SkillVisibility
from src.db.models.skills import Skill
from src.db.models.skills_domain import SkillDomain
from src.db.models.skill_usage_events import SkillUsageEvent
from src.db.models.knowledge_domains import KnowledgeDomain
from src.db.models.config_bundles import ConfigBundle
from src.db.models.config_bundle_skills import ConfigBundleSkill
from src.db.models.agent_profile_skills import AgentProfileSkill


def _visible_to(viewer_id: int):
    return and_(
        Skill.archived_at.is_(None),
        or_(
            Skill.visibility == SkillVisibility.GLOBAL,
            Skill.owner_id == viewer_id,
        ),
    )


def _in_effective_set(bundle_id: int):
    direct = select(ConfigBundleSkill.skill_id).where(
        ConfigBundleSkill.config_bundle_id == bundle_id
    )
    via_profile = (
        select(AgentProfileSkill.skill_id)
        .join(ConfigBundle, ConfigBundle.agent_id == AgentProfileSkill.agent_id)
        .where(ConfigBundle.id == bundle_id)
    )
    return or_(Skill.id.in_(direct), Skill.id.in_(via_profile))


class SkillRepository(BaseRepository[Skill]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, Skill)

    async def get_by_id(self, entity_id: int):  # type: ignore[override]
        raise NotImplementedError("Use get_visible, get_for_bundle or admin_get_by_id")

    async def get_all(self, limit: int = 100, offset: int = 0):  # type: ignore[override]
        raise NotImplementedError("Use list_visible or admin_list_global")

    def _visible_select(self, viewer_id: int, *columns):
        return select(*columns).where(_visible_to(viewer_id))

    async def list_visible(
        self,
        viewer_id: int,
        limit: int = 100,
        offset: int = 0,
        domain_id: int | None = None,
    ) -> list[Skill]:
        stmt = self._visible_select(viewer_id, Skill).options(defer(Skill.content))
        if domain_id is not None:
            stmt = stmt.where(
                Skill.id.in_(
                    select(SkillDomain.skill_id).where(SkillDomain.domain_id == domain_id)
                )
            )
        stmt = stmt.order_by(Skill.skill_name, Skill.id).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_visible(self, skill_id: int, viewer_id: int) -> Optional[Skill]:
        result = await self.session.execute(
            self._visible_select(viewer_id, Skill).where(Skill.id == skill_id)
        )
        return result.scalar_one_or_none()

    async def get_visible_many(
        self, skill_ids: Sequence[int], viewer_id: int
    ) -> list[Skill]:
        ids = list(set(skill_ids))
        if not ids:
            return []
        result = await self.session.execute(
            self._visible_select(viewer_id, Skill)
            .options(defer(Skill.content))
            .where(Skill.id.in_(ids))
        )
        return list(result.scalars().all())

    async def list_candidates(self, viewer_id: int):
        result = await self.session.execute(
            self._visible_select(
                viewer_id, Skill.id, Skill.skill_name, Skill.description
            ).order_by(Skill.id)
        )
        return list(result.all())

    async def count_candidates(self, viewer_id: int) -> int:
        from sqlalchemy import func

        result = await self.session.execute(
            self._visible_select(viewer_id, func.count(Skill.id))
        )
        return int(result.scalar_one())

    async def get_global_active_many(self, skill_ids: Sequence[int]) -> list[Skill]:
        ids = list(set(skill_ids))
        if not ids:
            return []
        result = await self.session.execute(
            select(Skill)
            .options(defer(Skill.content))
            .where(
                Skill.id.in_(ids),
                Skill.visibility == SkillVisibility.GLOBAL,
                Skill.archived_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def get_for_bundle(self, skill_id: int, bundle_id: int) -> Optional[Skill]:
        result = await self.session.execute(
            select(Skill).where(Skill.id == skill_id, _in_effective_set(bundle_id))
        )
        return result.scalar_one_or_none()

    async def list_for_bundle(self, bundle_id: int) -> list[Skill]:
        result = await self.session.execute(
            select(Skill)
            .options(defer(Skill.content))
            .where(_in_effective_set(bundle_id))
            .order_by(Skill.skill_name, Skill.id)
        )
        return list(result.scalars().all())

    async def list_with_content_for_bundle(self, bundle_id: int) -> list[Skill]:
        result = await self.session.execute(
            select(Skill)
            .where(_in_effective_set(bundle_id))
            .order_by(Skill.id)
        )
        return list(result.scalars().all())

    async def list_manifest_for_bundle(self, bundle_id: int):
        result = await self.session.execute(
            select(
                Skill.id, Skill.skill_name, Skill.content_hash, Skill.archived_at
            )
            .where(_in_effective_set(bundle_id))
            .order_by(Skill.id)
        )
        return list(result.all())

    async def admin_get_by_id(self, skill_id: int) -> Optional[Skill]:
        result = await self.session.execute(select(Skill).where(Skill.id == skill_id))
        return result.scalar_one_or_none()

    async def admin_list_global(
        self, limit: int = 100, offset: int = 0, include_archived: bool = False
    ) -> list[Skill]:
        stmt = (
            select(Skill)
            .options(defer(Skill.content))
            .where(Skill.visibility == SkillVisibility.GLOBAL)
        )
        if not include_archived:
            stmt = stmt.where(Skill.archived_at.is_(None))
        stmt = stmt.order_by(Skill.skill_name, Skill.id).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_owned_by_id(self, skill_id: int, owner_id: int) -> Optional[Skill]:
        result = await self.session.execute(
            select(Skill).where(Skill.id == skill_id, Skill.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def list_owned(
        self,
        owner_id: int,
        limit: int = 100,
        offset: int = 0,
        include_archived: bool = False,
    ) -> list[Skill]:
        stmt = select(Skill).options(defer(Skill.content)).where(Skill.owner_id == owner_id)
        if not include_archived:
            stmt = stmt.where(Skill.archived_at.is_(None))
        stmt = stmt.order_by(Skill.skill_name, Skill.id).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_owned_active(self, owner_id: int) -> int:
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count(Skill.id)).where(
                Skill.owner_id == owner_id, Skill.archived_at.is_(None)
            )
        )
        return int(result.scalar_one())

    async def get_global_by_name(self, skill_name: str) -> Optional[Skill]:
        result = await self.session.execute(
            select(Skill).where(
                Skill.skill_name == skill_name, Skill.owner_id.is_(None)
            )
        )
        return result.scalar_one_or_none()

    async def get_owned_by_name(
        self, skill_name: str, owner_id: int
    ) -> Optional[Skill]:
        result = await self.session.execute(
            select(Skill).where(
                Skill.skill_name == skill_name, Skill.owner_id == owner_id
            )
        )
        return result.scalar_one_or_none()

    async def archive(self, skill: Skill) -> Skill:
        if skill.archived_at is None:
            skill.archived_at = datetime.now(timezone.utc)
            await self.session.flush()
        return skill

    async def restore(self, skill: Skill) -> Skill:
        if skill.archived_at is not None:
            skill.archived_at = None
            await self.session.flush()
        return skill

    async def record_selection(
        self,
        skill_id: int,
        user_id: int,
        config_bundle_id: int | None = None,
    ) -> Optional[Skill]:
        self.session.add(
            SkillUsageEvent(
                skill_id=skill_id,
                user_id=user_id,
                config_bundle_id=config_bundle_id,
            )
        )
        skill = await self.admin_get_by_id(skill_id)
        if skill is not None:
            skill.skill_selected_freq += 1
        await self.session.flush()
        return skill

    async def add_domain(self, skill: Skill, domain: KnowledgeDomain) -> Skill:
        await self.session.refresh(skill, attribute_names=["domains"])
        if domain not in skill.domains:
            skill.domains.append(domain)
        await self.session.flush()
        return skill