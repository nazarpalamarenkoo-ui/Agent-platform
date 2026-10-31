from typing import Sequence

from src.catalog.hint.skill_markdown import clean_skill_body, render_skill_md
from src.db.enums.notification_type import NotificationType
from src.db.enums.skill_visibility import SkillVisibility
from src.db.models.knowledge_domains import KnowledgeDomain
from src.db.models.skills import Skill
from src.db.models.users import User
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.notification_repo import NotificationRepository
from src.repositories.skill_repo import SkillRepository
from src.services.errors import ConflictError, NotFoundError
from src.services.permissions import require_admin

MAX_CONTENT_CHARS = 50_000


class SkillService:

    def __init__(
        self,
        skill_repo: SkillRepository,
        domain_repo: KnowledgeDomainRepository,
        config_bundle_repo: ConfigBundleRepository,
        notification_repo: NotificationRepository,
    ):
        self.skill_repo = skill_repo
        self.domain_repo = domain_repo
        self.config_bundle_repo = config_bundle_repo
        self.notification_repo = notification_repo

    async def list_skills(
        self,
        actor: User,
        limit: int = 100,
        offset: int = 0,
        domain_id: int | None = None,
        include_archived: bool = False,
    ) -> list[Skill]:
        if include_archived:
            require_admin(actor)
            return await self.skill_repo.admin_list_global(
                limit=limit, offset=offset, include_archived=True
            )
        return await self.skill_repo.list_visible(
            actor.id, limit=limit, offset=offset, domain_id=domain_id
        )

    async def get_skill(self, actor: User, skill_id: int) -> Skill:
        skill = await self.skill_repo.get_visible(skill_id, actor.id)
        if skill is None and actor.is_admin:
            candidate = await self.skill_repo.admin_get_by_id(skill_id)
            if candidate is not None and candidate.visibility == SkillVisibility.GLOBAL:
                skill = candidate
        if skill is None:
            raise NotFoundError("Skill not found")
        return skill

    async def export_skill_md(self, actor: User, skill_id: int) -> str:
        skill = await self.get_skill(actor, skill_id)
        return render_skill_md(skill.skill_name, skill.description, skill.content)

    async def create_global_skill(
        self,
        actor: User,
        skill_name: str,
        description: str,
        content: str,
        domain_ids: Sequence[int] | None = None,
    ) -> Skill:
        require_admin(actor)

        name = self._clean_name(skill_name)
        text = self._clean_content(content)

        if await self.skill_repo.get_global_by_name(name) is not None:
            raise ConflictError(f"Skill '{name}' already exists")

        domains = await self._resolve_domains(domain_ids)

        skill = await self.skill_repo.create(
            skill_name=name,
            description=description,
            content=text,
            visibility=SkillVisibility.GLOBAL,
            owner_id=None,
        )
        for domain in domains:
            await self.skill_repo.add_domain(skill, domain)

        return await self._reload(skill.id)

    async def update_global_skill(
        self,
        actor: User,
        skill_id: int,
        description: str | None = None,
        content: str | None = None,
    ) -> Skill:
        require_admin(actor)
        skill = await self._get_global(skill_id)

        changes: dict = {}
        if description is not None:
            changes["description"] = description
        if content is not None:
            changes["content"] = self._clean_content(content)
        if changes:
            await self.skill_repo.update(skill, **changes)

        return await self._reload(skill.id)

    async def archive_skill(self, actor: User, skill_id: int) -> Skill:
        require_admin(actor)
        skill = await self._get_global(skill_id)

        if skill.archived_at is None:
            await self.skill_repo.archive(skill)
            user_ids = await self.config_bundle_repo.list_user_ids_with_skill(skill.id)
            await self.notification_repo.create_missing(
                user_ids, NotificationType.SKILL_ARCHIVED, skill_id=skill.id
            )

        return await self._reload(skill.id)

    async def restore_skill(self, actor: User, skill_id: int) -> Skill:
        require_admin(actor)
        skill = await self._get_global(skill_id)

        if skill.archived_at is not None:
            await self.skill_repo.restore(skill)
            await self.notification_repo.delete_for_item(
                NotificationType.SKILL_ARCHIVED, skill_id=skill.id
            )

        return await self._reload(skill.id)

    async def _get_global(self, skill_id: int) -> Skill:
        skill = await self.skill_repo.admin_get_by_id(skill_id)
        if skill is None or skill.visibility != SkillVisibility.GLOBAL:
            raise NotFoundError("Skill not found")
        return skill

    async def _reload(self, skill_id: int) -> Skill:
        skill = await self.skill_repo.admin_get_by_id(skill_id)
        if skill is None:
            raise NotFoundError("Skill not found")
        return skill

    async def _resolve_domains(self, domain_ids: Sequence[int] | None) -> list[KnowledgeDomain]:
        domains: list[KnowledgeDomain] = []
        for domain_id in dict.fromkeys(domain_ids or []):
            domain = await self.domain_repo.get_by_id(domain_id)
            if domain is None:
                raise NotFoundError(f"Domain {domain_id} not found")
            domains.append(domain)
        return domains

    @staticmethod
    def _clean_name(name: str) -> str:
        cleaned = (name or "").strip()
        if not cleaned:
            raise ValueError("Skill name must not be empty")
        return cleaned

    @staticmethod
    def _clean_content(content: str) -> str:
        return clean_skill_body(content, MAX_CONTENT_CHARS)