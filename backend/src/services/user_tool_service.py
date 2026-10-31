import ipaddress
from typing import Sequence
from urllib.parse import parse_qsl, urlparse

from src.config import settings
from src.db.enums.tool_auth_type import ToolAuthType
from src.db.enums.tool_visibility import ToolVisibility
from src.db.models.tools_definition import ToolDefinition
from src.db.models.users import User
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.services.errors import ConflictError, NotFoundError

MAX_PRIVATE_TOOLS = 20
MAX_NAME = 100
MAX_DESCRIPTION = 255
MAX_URL = 2048
SENSITIVE_PARAMS = {
    "token", "access_token", "api_key", "apikey", "key", "secret",
    "password", "pwd", "auth", "authorization", "sig", "signature",
}
LOCAL_HOSTS = {"localhost", "localhost.localdomain"}


def inspect_url(url: str, allow_private_hosts: bool) -> tuple[str, list[str]]:
    cleaned = (url or "").strip()
    if not cleaned or len(cleaned) > MAX_URL or any(c.isspace() or ord(c) < 32 for c in cleaned):
        raise ValueError("Tool URL must be an absolute http(s) URL")
    parsed = urlparse(cleaned)
    try:
        parsed.port
    except ValueError:
        raise ValueError("Tool URL has an invalid port")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Tool URL must be an absolute http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("Tool URL must not contain a login or password")

    host = parsed.hostname.lower()
    if not allow_private_hosts:
        private = host in LOCAL_HOSTS or host.endswith(".local")
        try:
            ip = ipaddress.ip_address(host)
            private = private or ip.is_private or ip.is_loopback or ip.is_link_local
        except ValueError:
            pass
        if private:
            raise ValueError("Local and private addresses are not allowed")

    warnings: list[str] = []
    leaked = sorted({k for k, _ in parse_qsl(parsed.query) if k.lower() in SENSITIVE_PARAMS})
    if leaked:
        warnings.append(
            f"URL contains credential-like parameters ({', '.join(leaked)}). "
            "The URL is stored in the database and included in exported bundles."
        )
    if parsed.scheme == "http" and host not in LOCAL_HOSTS:
        warnings.append("The URL uses plain http: traffic is not encrypted.")
    return cleaned, warnings


class UserToolService:

    def __init__(
        self,
        tool_repo: ToolDefinitionRepository,
        domain_repo: KnowledgeDomainRepository,
        max_private_tools: int = MAX_PRIVATE_TOOLS,
        allow_private_hosts: bool | None = None,
    ):
        self.tool_repo = tool_repo
        self.domain_repo = domain_repo
        self.max_private_tools = max_private_tools
        self.allow_private_hosts = (
            getattr(settings, "ALLOW_PRIVATE_TOOL_HOSTS", True)
            if allow_private_hosts is None else allow_private_hosts
        )

    async def list_tools(self, actor: User, limit=100, offset=0, include_archived=False):
        return await self.tool_repo.list_owned(
            actor.id, limit=limit, offset=offset, include_archived=include_archived)

    async def get_tool(self, actor: User, tool_id: int) -> ToolDefinition:
        tool = await self.tool_repo.get_owned_by_id(tool_id, actor.id)
        if tool is None:
            raise NotFoundError("Tool not found")
        return tool

    async def create_tool(
        self, actor: User, tool_name: str, description: str, url: str,
        auth_type: ToolAuthType = ToolAuthType.NONE,
        auth_description: str | None = None,
        domain_ids: Sequence[int] | None = None,
    ) -> tuple[ToolDefinition, list[str]]:
        name = self._clean_name(tool_name)
        desc = self._clean_description(description)
        clean_url, warnings = inspect_url(url, self.allow_private_hosts)

        if await self.tool_repo.get_owned_by_name(name, actor.id) is not None:
            raise ConflictError(f"You already have a tool named '{name}'")
        await self._ensure_quota(actor)
        domains = await self._resolve_domains(domain_ids)

        tool = await self.tool_repo.create(
            tool_name=name, description=desc, url=clean_url,
            auth_type=auth_type, auth_description=auth_description,
            visibility=ToolVisibility.PRIVATE, owner_id=actor.id,
        )
        for domain in domains:
            await self.tool_repo.add_domain(tool, domain)
        return await self.get_tool(actor, tool.id), warnings

    async def update_tool(
        self, actor: User, tool_id: int, description: str | None = None,
        url: str | None = None, auth_type: ToolAuthType | None = None,
        auth_description: str | None = None,
    ) -> tuple[ToolDefinition, list[str]]:
        tool = await self.get_tool(actor, tool_id)
        warnings: list[str] = []
        changes: dict = {}
        if description is not None:
            changes["description"] = self._clean_description(description)
        if url is not None:
            changes["url"], warnings = inspect_url(url, self.allow_private_hosts)
        if auth_type is not None:
            changes["auth_type"] = auth_type
        if auth_description is not None:
            changes["auth_description"] = auth_description
        if changes:
            await self.tool_repo.update(tool, **changes)
        return await self.get_tool(actor, tool_id), warnings

    async def archive_tool(self, actor: User, tool_id: int) -> ToolDefinition:
        tool = await self.get_tool(actor, tool_id)
        await self.tool_repo.archive(tool)
        return await self.get_tool(actor, tool_id)

    async def restore_tool(self, actor: User, tool_id: int) -> ToolDefinition:
        tool = await self.get_tool(actor, tool_id)
        if tool.archived_at is not None:
            await self._ensure_quota(actor)
            await self.tool_repo.restore(tool)
        return await self.get_tool(actor, tool_id)

    async def _ensure_quota(self, actor: User) -> None:
        if await self.tool_repo.count_owned_active(actor.id) >= self.max_private_tools:
            raise ConflictError(f"You can have at most {self.max_private_tools} active private tools")

    async def _resolve_domains(self, domain_ids):
        domains = []
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
            raise ValueError("Tool name must not be empty")
        if len(cleaned) > MAX_NAME:
            raise ValueError(f"Tool name must not exceed {MAX_NAME} characters")
        return cleaned

    @staticmethod
    def _clean_description(description: str) -> str:
        cleaned = " ".join((description or "").split())
        if not cleaned:
            raise ValueError("Tool description must not be empty")
        if len(cleaned) > MAX_DESCRIPTION:
            raise ValueError(f"Tool description must not exceed {MAX_DESCRIPTION} characters")
        return cleaned