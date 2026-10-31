from typing import Sequence

from src.catalog.hint.skill_markdown import clean_skill_body, render_skill_md, split_frontmatter
from src.db.enums.skill_visibility import SkillVisibility
from src.db.models.knowledge_domains import KnowledgeDomain
from src.db.models.skills import Skill
from src.db.models.users import User
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.skill_repo import SkillRepository
from src.services.errors import ConflictError, NotFoundError

MAX_PRIVATE_SKILLS = 50
MAX_NAME_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 255


class UserSkillService:

    def __init__(
        self,
        skill_repo: SkillRepository,
        domain_repo: KnowledgeDomainRepository,
        max_private_skills: int = MAX_PRIVATE_SKILLS,
    ):
        self.skill_repo = skill_repo
        self.domain_repo = domain_repo
        self.max_private_skills = max_private_skills

    async def list_skills(
        self,
        actor: User,
        limit: int = 100,
        offset: int = 0,
        include_archived: bool = False,
    ) -> list[Skill]:
        return await self.skill_repo.list_owned(
            actor.id, limit=limit, offset=offset, include_archived=include_archived
        )

    async def get_skill(self, actor: User, skill_id: int) -> Skill:
        return await self._get(actor, skill_id)

    async def create_skill(
        self,
        actor: User,
        skill_name: str,
        description: str,
        content: str,
        domain_ids: Sequence[int] | None = None,
    ) -> Skill:
        name = self._clean_name(skill_name)
        text_description = self._clean_description(description)
        body = clean_skill_body(content)

        if await self.skill_repo.get_owned_by_name(name, actor.id) is not None:
            raise ConflictError(f"You already have a skill named '{name}'")
        await self._ensure_quota(actor)
        domains = await self._resolve_domains(domain_ids)

        skill = await self.skill_repo.create(
            skill_name=name,
            description=text_description,
            content=body,
            visibility=SkillVisibility.PRIVATE,
            owner_id=actor.id,
        )
        for domain in domains:
            await self.skill_repo.add_domain(skill, domain)

        return await self._get(actor, skill.id)

    async def import_markdown(
        self,
        actor: User,
        markdown: str,
        skill_name: str | None = None,
        description: str | None = None,
        domain_ids: Sequence[int] | None = None,
    ) -> Skill:
        meta, body = split_frontmatter(markdown or "")
        name = (skill_name or meta.get("name") or "").strip()
        text_description = (description or meta.get("description") or "").strip()
        if not name or not text_description:
            raise ValueError(
                "Skill name and description are required: pass them explicitly or "
                "provide them in the frontmatter"
            )
        return await self.create_skill(actor, name, text_description, body, domain_ids)

    async def update_skill(
        self,
        actor: User,
        skill_id: int,
        skill_name: str | None = None,
        description: str | None = None,
        content: str | None = None,
    ) -> Skill:
        skill = await self._get(actor, skill_id)

        changes: dict = {}
        if skill_name is not None:
            name = self._clean_name(skill_name)
            if name != skill.skill_name:
                existing = await self.skill_repo.get_owned_by_name(name, actor.id)
                if existing is not None and existing.id != skill.id:
                    raise ConflictError(f"You already have a skill named '{name}'")
                changes["skill_name"] = name
        if description is not None:
            changes["description"] = self._clean_description(description)
        if content is not None:
            changes["content"] = clean_skill_body(content)

        if changes:
            await self.skill_repo.update(skill, **changes)

        return await self._get(actor, skill_id)

    async def archive_skill(self, actor: User, skill_id: int) -> Skill:
        skill = await self._get(actor, skill_id)
        await self.skill_repo.archive(skill)
        return await self._get(actor, skill_id)

    async def restore_skill(self, actor: User, skill_id: int) -> Skill:
        skill = await self._get(actor, skill_id)
        if skill.archived_at is not None:
            await self._ensure_quota(actor)
            await self.skill_repo.restore(skill)
        return await self._get(actor, skill_id)

    async def export_markdown(self, actor: User, skill_id: int) -> str:
        skill = await self._get(actor, skill_id)
        return render_skill_md(skill.skill_name, skill.description, skill.content)

    async def _get(self, actor: User, skill_id: int) -> Skill:
        skill = await self.skill_repo.get_owned_by_id(skill_id, actor.id)
        if skill is None:
            raise NotFoundError("Skill not found")
        return skill

    async def _ensure_quota(self, actor: User) -> None:
        if await self.skill_repo.count_owned_active(actor.id) >= self.max_private_skills:
            raise ConflictError(
                f"You can have at most {self.max_private_skills} active private skills"
            )

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
        if len(cleaned) > MAX_NAME_LENGTH:
            raise ValueError(f"Skill name must not exceed {MAX_NAME_LENGTH} characters")
        return cleaned

    @staticmethod
    def _clean_description(description: str) -> str:
        cleaned = " ".join((description or "").split())
        if not cleaned:
            raise ValueError("Skill description must not be empty")
        if len(cleaned) > MAX_DESCRIPTION_LENGTH:
            raise ValueError(
                f"Skill description must not exceed {MAX_DESCRIPTION_LENGTH} characters"
            )
        return cleaned