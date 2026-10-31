from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.enums.notification_type import NotificationType
from src.db.enums.user_role import UserRole
from src.db.models.config_bundles import ConfigBundle
from src.db.models.skills import Skill
from src.db.models.token_usage_events import TokenUsageEvent  # перевірте шлях
from src.db.models.tools_definition import ToolDefinition
from src.db.models.users import User
from src.repositories.notification_repo import NotificationRepository
from src.repositories.skill_access_log_repo import SkillAccessLogRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.repositories.user_repo import UserRepository
from src.schemas.admin_skills import AdminToolItem, UserOverview
from src.services.errors import ForbiddenError, NotFoundError
from src.services.permissions import require_admin


def mask_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "***" if parts.query else "", ""))


class AdminUserContentService:

    def __init__(
        self,
        session: AsyncSession,
        user_repo: UserRepository,
        skill_repo: SkillRepository,
        tool_repo: ToolDefinitionRepository,
        log_repo: SkillAccessLogRepository,
        notification_repo: NotificationRepository,
    ):
        self.session = session
        self.user_repo = user_repo
        self.skill_repo = skill_repo
        self.tool_repo = tool_repo
        self.log_repo = log_repo
        self.notification_repo = notification_repo

    async def _target(self, actor: User, user_id: int) -> User:
        require_admin(actor)
        target = await self.user_repo.get_by_id(user_id)
        if target is None:
            raise NotFoundError("User not found")
        if (
            target.id != actor.id
            and target.role != UserRole.USER
            and not actor.is_super_admin
        ):
            raise ForbiddenError("Only a super admin can inspect other admins")
        return target

    async def list_skills(self, actor, user_id, include_archived=False, limit=100, offset=0):
        target = await self._target(actor, user_id)
        skills = await self.skill_repo.list_owned(
            target.id, limit=limit, offset=offset, include_archived=include_archived
        )
        await self.log_repo.record(actor.id, target.id, "list")
        return skills

    async def get_skill(self, actor, user_id, skill_id) -> Skill:
        target = await self._target(actor, user_id)
        skill = await self.skill_repo.get_owned_by_id(skill_id, target.id)
        if skill is None:
            raise NotFoundError("Skill not found")
        await self.log_repo.record(actor.id, target.id, "view", skill_id=skill.id)
        return skill

    async def archive_for_violation(self, actor, user_id, skill_id, reason: str) -> Skill:
        target = await self._target(actor, user_id)
        skill = await self.skill_repo.get_owned_by_id(skill_id, target.id)
        if skill is None:
            raise NotFoundError("Skill not found")
        await self.skill_repo.archive(skill)
        await self.log_repo.record(
            actor.id, target.id, "archive", skill_id=skill.id, note=reason.strip()[:255]
        )
        await self.notification_repo.create_missing(
            [target.id], NotificationType.SKILL_ARCHIVED, skill_id=skill.id
        )
        return skill

    async def list_tools(self, actor, user_id, include_archived=False, limit=100, offset=0):
        target = await self._target(actor, user_id)
        tools = await self.tool_repo.list_owned(
            target.id, limit=limit, offset=offset, include_archived=include_archived
        )
        return [
            AdminToolItem(
                id=t.id, tool_name=t.tool_name, description=t.description,
                url_masked=mask_url(t.url), archived_at=t.archived_at,
            )
            for t in tools
        ]

    async def overview(self, actor, user_id) -> UserOverview:
        target = await self._target(actor, user_id)

        async def count(model, *conds) -> int:
            result = await self.session.execute(
                select(func.count()).select_from(model).where(*conds)
            )
            return int(result.scalar_one())

        return UserOverview(
            user_id=target.id,
            private_skills=await count(Skill, Skill.owner_id == target.id, Skill.archived_at.is_(None)),
            private_tools=await count(
                ToolDefinition, ToolDefinition.owner_id == target.id,
                ToolDefinition.archived_at.is_(None),
            ),
            bundles=await count(ConfigBundle, ConfigBundle.user_id == target.id),
            token_events=await count(TokenUsageEvent, TokenUsageEvent.user_id == target.id),
            tokens_used=target.tokens_used,
            token_limit=target.token_limit,
        )