from typing import Sequence
from urllib.parse import urlparse

from src.db.enums.notification_type import NotificationType
from src.db.enums.tool_auth_type import ToolAuthType
from src.db.enums.tool_visibility import ToolVisibility
from src.db.models.knowledge_domains import KnowledgeDomain
from src.db.models.tools_definition import ToolDefinition
from src.db.models.users import User
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.notification_repo import NotificationRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.services.errors import ConflictError, NotFoundError
from src.services.permissions import require_admin

MAX_URL_LENGTH = 2048


class ToolService:

    def __init__(
        self,
        tool_repo: ToolDefinitionRepository,
        domain_repo: KnowledgeDomainRepository,
        config_bundle_repo: ConfigBundleRepository,
        notification_repo: NotificationRepository,
    ):
        self.tool_repo = tool_repo
        self.domain_repo = domain_repo
        self.config_bundle_repo = config_bundle_repo
        self.notification_repo = notification_repo

    async def list_tools(self, actor, limit=100, offset=0, domain_id=None, include_archived=False):
        if include_archived:
            require_admin(actor)
            return await self.tool_repo.admin_list_global(limit=limit, offset=offset, include_archived=True)
        return await self.tool_repo.list_visible(actor.id, limit=limit, offset=offset, domain_id=domain_id)


    async def get_tool(self, actor, tool_id):
        tool = await self.tool_repo.get_visible(tool_id, actor.id)
        if tool is None and actor.is_admin:
            candidate = await self.tool_repo.admin_get_by_id(tool_id)
            if candidate is not None and candidate.owner_id is None:
                tool = candidate
        if tool is None:
            raise NotFoundError("Tool not found")
        return tool

    async def create_tool(
        self,
        actor: User,
        tool_name: str,
        description: str,
        url: str,
        auth_type: ToolAuthType = ToolAuthType.NONE,
        auth_description: str | None = None,
        domain_ids: Sequence[int] | None = None,
    ) -> ToolDefinition:
        require_admin(actor)

        name = (tool_name or "").strip()
        if not name:
            raise ValueError("Tool name must not be empty")
        clean_url = self._clean_url(url)

        if await self.tool_repo.get_global_by_name(name) is not None:
            raise ConflictError(f"Tool '{name}' already exists")

        domains = await self._resolve_domains(domain_ids)

        tool = await self.tool_repo.create(
            tool_name=name,
            description=description,
            url=clean_url,
            auth_type=auth_type,
            auth_description=auth_description,
            visibility=ToolVisibility.GLOBAL, 
            owner_id=None
        )
        for domain in domains:
            await self.tool_repo.add_domain(tool, domain)

        return await self._reload(tool.id)

    async def update_tool(
        self,
        actor: User,
        tool_id: int,
        description: str | None = None,
        url: str | None = None,
        auth_type: ToolAuthType | None = None,
        auth_description: str | None = None,
    ) -> ToolDefinition:
        require_admin(actor)
        tool = await self._get(tool_id)

        changes: dict = {}
        if description is not None:
            changes["description"] = description
        if url is not None:
            changes["url"] = self._clean_url(url)
        if auth_type is not None:
            changes["auth_type"] = auth_type
        if auth_description is not None:
            changes["auth_description"] = auth_description
        if changes:
            await self.tool_repo.update(tool, **changes)

        return await self._reload(tool.id)

    async def archive_tool(self, actor: User, tool_id: int) -> ToolDefinition:
        require_admin(actor)
        tool = await self._get(tool_id)

        if tool.archived_at is None:
            await self.tool_repo.archive(tool)
            user_ids = await self.config_bundle_repo.list_user_ids_with_tool(tool.id)
            await self.notification_repo.create_missing(
                user_ids, NotificationType.TOOL_ARCHIVED, tool_id=tool.id
            )

        return await self._reload(tool.id)

    async def restore_tool(self, actor: User, tool_id: int) -> ToolDefinition:
        require_admin(actor)
        tool = await self._get(tool_id)

        if tool.archived_at is not None:
            await self.tool_repo.restore(tool)
            await self.notification_repo.delete_for_item(
                NotificationType.TOOL_ARCHIVED, tool_id=tool.id
            )

        return await self._reload(tool.id)

    async def _get(self, tool_id: int) -> ToolDefinition:
        tool = await self.tool_repo.admin_get_by_id(tool_id)
        if tool is None or tool.owner_id is not None:
            raise NotFoundError("Tool not found")
        return tool

    async def _reload(self, tool_id: int) -> ToolDefinition:
        return await self._get(tool_id)

    async def _resolve_domains(self, domain_ids: Sequence[int] | None) -> list[KnowledgeDomain]:
        domains: list[KnowledgeDomain] = []
        for domain_id in dict.fromkeys(domain_ids or []):
            domain = await self.domain_repo.get_by_id(domain_id)
            if domain is None:
                raise NotFoundError(f"Domain {domain_id} not found")
            domains.append(domain)
        return domains

    @staticmethod
    def _clean_url(url: str) -> str:
        cleaned = (url or "").strip()
        parsed = urlparse(cleaned)
        if (
            not cleaned
            or len(cleaned) > MAX_URL_LENGTH
            or parsed.scheme not in ("http", "https")
            or not parsed.hostname
        ):
            raise ValueError("Tool URL must be an absolute http(s) URL")
        return cleaned