import hashlib
import json
from dataclasses import dataclass

from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.repositories.agent_profile_repo import AgentProfileRepository
from src.services.errors import NotFoundError

HASH_VERSION = 1


@dataclass(frozen=True)
class EffectiveSkill:
    id: int
    name: str
    content_hash: str
    archived: bool


@dataclass(frozen=True)
class EffectiveTool:
    id: int
    name: str
    url: str
    auth_type: str
    archived: bool
    custom: bool = False


@dataclass(frozen=True)
class EffectivePack:
    id: int
    slug: str
    version: int
    archived: bool


@dataclass(frozen=True)
class EffectiveBundle:
    bundle_id: int
    agent_id: int
    agent_name: str
    skills: tuple[EffectiveSkill, ...]
    tools: tuple[EffectiveTool, ...]
    packs: tuple[EffectivePack, ...]
    version_hash: str


def compute_version_hash(
    agent_id: int,
    skills: tuple[EffectiveSkill, ...],
    tools: tuple[EffectiveTool, ...],
    packs: tuple[EffectivePack, ...],
) -> str:
    payload = {
        "v": HASH_VERSION,
        "agent": agent_id,
        "skills": sorted([s.id, s.content_hash] for s in skills),
        "tools": sorted([t.id, t.url, t.auth_type] for t in tools),
        "packs": sorted([p.id, p.version] for p in packs),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class EffectiveBundleService:

    def __init__(
        self,
        config_bundle_repo: ConfigBundleRepository,
        skill_repo: SkillRepository,
        tool_repo: ToolDefinitionRepository,
        knowledge_pack_repo: KnowledgePackRepository,
        agent_profile_repo: AgentProfileRepository,
    ):
        self.config_bundle_repo = config_bundle_repo
        self.skill_repo = skill_repo
        self.tool_repo = tool_repo
        self.knowledge_pack_repo = knowledge_pack_repo
        self.agent_profile_repo = agent_profile_repo

    async def get_effective(self, bundle_id: int) -> EffectiveBundle:
        bundle = await self.config_bundle_repo.get_by_id(bundle_id)
        if bundle is None:
            raise NotFoundError("Config bundle not found")
        return await self._build(bundle.id, bundle.agent_id)

    async def get_effective_for_user(self, bundle_id: int, user_id: int) -> EffectiveBundle:
        bundle = await self.config_bundle_repo.get_owned(bundle_id, user_id)
        if bundle is None:
            raise NotFoundError("Config bundle not found")
        return await self._build(bundle.id, bundle.agent_id)

    async def _build(self, bundle_id: int, agent_id: int) -> EffectiveBundle:
        profile = await self.agent_profile_repo.admin_get_by_id(agent_id)
        if profile is None:
            raise NotFoundError("Agent profile not found")

        skills = tuple(
            EffectiveSkill(
                id=row.id,
                name=row.skill_name,
                content_hash=row.content_hash,
                archived=row.archived_at is not None,
            )
            for row in await self.skill_repo.list_manifest_for_bundle(bundle_id)
        )
        tools = tuple(
            EffectiveTool(
                id=row.id,
                name=row.tool_name,
                url=row.url,
                auth_type=row.auth_type.value,
                archived=row.archived_at is not None,
                custom=row.owner_id is not None,
            )
            for row in await self.tool_repo.list_manifest_for_bundle(bundle_id)
        )
        packs = tuple(
            EffectivePack(
                id=row.id,
                slug=row.slug,
                version=row.version,
                archived=row.archived_at is not None,
            )
            for row in await self.knowledge_pack_repo.list_manifest_for_bundle(bundle_id)
        )

        return EffectiveBundle(
            bundle_id=bundle_id,
            agent_id=profile.id,
            agent_name=profile.agent_name,
            skills=skills,
            tools=tools,
            packs=packs,
            version_hash=compute_version_hash(profile.id, skills, tools, packs),
        )