from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.effective_bundle_service import (
    EffectiveBundle,
    EffectiveBundleService,
    EffectivePack,
    EffectiveSkill,
    EffectiveTool,
    compute_version_hash,
)
from src.services.errors import NotFoundError

S1 = EffectiveSkill(id=1, name="a", content_hash="h1", archived=False)
S2 = EffectiveSkill(id=2, name="b", content_hash="h2", archived=False)
T1 = EffectiveTool(id=10, name="t", url="https://x.io", auth_type="none", archived=False)
P1 = EffectivePack(id=20, slug="p", version=1, archived=False)


def digest(agent_id=1, skills=(S1, S2), tools=(T1,), packs=(P1,)):
    return compute_version_hash(agent_id, tuple(skills), tuple(tools), tuple(packs))


class TestComputeVersionHash:
    def test_is_sha256_hex_and_deterministic(self):
        assert digest() == digest()
        assert len(digest()) == 64
        int(digest(), 16)

    def test_independent_of_item_order(self):
        assert digest(skills=(S1, S2)) == digest(skills=(S2, S1))

    def test_changes_with_agent(self):
        assert digest(agent_id=1) != digest(agent_id=2)

    def test_changes_with_skill_content(self):
        assert digest() != digest(skills=(replace(S1, content_hash="new"), S2))

    def test_changes_when_skill_added(self):
        assert digest(skills=(S1,)) != digest(skills=(S1, S2))

    def test_changes_with_tool_url_and_auth(self):
        assert digest() != digest(tools=(replace(T1, url="https://y.io"),))
        assert digest() != digest(tools=(replace(T1, auth_type="bearer"),))

    def test_changes_with_pack_version(self):
        assert digest() != digest(packs=(replace(P1, version=2),))

    def test_ignores_names_and_archived_flags(self):
        # documents current behaviour: archiving an item does not change the hash
        assert digest() == digest(skills=(replace(S1, name="zzz", archived=True), S2))
        assert digest() == digest(tools=(replace(T1, archived=True, name="q"),))

    def test_empty_bundle_is_hashable(self):
        assert len(digest(skills=(), tools=(), packs=())) == 64


@pytest.fixture
def repos():
    return SimpleNamespace(
        bundle=AsyncMock(), skill=AsyncMock(), tool=AsyncMock(),
        pack=AsyncMock(), agent=AsyncMock(),
    )


@pytest.fixture
def service(repos):
    repos.bundle.get_by_id.return_value = SimpleNamespace(id=5, agent_id=3)
    repos.bundle.get_owned.return_value = SimpleNamespace(id=5, agent_id=3)
    repos.agent.admin_get_by_id.return_value = SimpleNamespace(id=3, agent_name="Agent")
    repos.skill.list_manifest_for_bundle.return_value = []
    repos.tool.list_manifest_for_bundle.return_value = []
    repos.pack.list_manifest_for_bundle.return_value = []
    return EffectiveBundleService(repos.bundle, repos.skill, repos.tool, repos.pack, repos.agent)


class TestGetEffective:
    async def test_builds_bundle_from_manifest_rows(self, service, repos):
        repos.skill.list_manifest_for_bundle.return_value = [
            SimpleNamespace(id=1, skill_name="s", content_hash="h", archived_at=None),
            SimpleNamespace(id=2, skill_name="old", content_hash="h2", archived_at="2026-01-01"),
        ]
        repos.tool.list_manifest_for_bundle.return_value = [
            SimpleNamespace(
                id=10, tool_name="global", url="https://a.io",
                auth_type=SimpleNamespace(value="none"), archived_at=None, owner_id=None,
            ),
            SimpleNamespace(
                id=11, tool_name="mine", url="https://b.io",
                auth_type=SimpleNamespace(value="bearer"), archived_at=None, owner_id=9,
            ),
        ]
        repos.pack.list_manifest_for_bundle.return_value = [
            SimpleNamespace(id=20, slug="p", version=3, archived_at=None)
        ]

        result = await service.get_effective(5)

        assert isinstance(result, EffectiveBundle)
        assert (result.bundle_id, result.agent_id, result.agent_name) == (5, 3, "Agent")
        assert result.skills == (
            EffectiveSkill(1, "s", "h", False),
            EffectiveSkill(2, "old", "h2", True),
        )
        assert result.tools[0].custom is False
        assert result.tools[1].custom is True
        assert result.tools[1].auth_type == "bearer"
        assert result.packs == (EffectivePack(20, "p", 3, False),)
        repos.skill.list_manifest_for_bundle.assert_awaited_once_with(5)

    async def test_version_hash_matches_compute_version_hash(self, service, repos):
        repos.skill.list_manifest_for_bundle.return_value = [
            SimpleNamespace(id=1, skill_name="s", content_hash="h", archived_at=None)
        ]

        result = await service.get_effective(5)

        assert result.version_hash == compute_version_hash(3, result.skills, result.tools, result.packs)

    async def test_raises_when_bundle_missing(self, service, repos):
        repos.bundle.get_by_id.return_value = None

        with pytest.raises(NotFoundError, match="Config bundle not found"):
            await service.get_effective(5)

    async def test_raises_when_agent_profile_missing(self, service, repos):
        repos.agent.admin_get_by_id.return_value = None

        with pytest.raises(NotFoundError, match="Agent profile not found"):
            await service.get_effective(5)


class TestGetEffectiveForUser:
    async def test_uses_ownership_check(self, service, repos):
        result = await service.get_effective_for_user(5, 42)

        repos.bundle.get_owned.assert_awaited_once_with(5, 42)
        repos.bundle.get_by_id.assert_not_awaited()
        assert result.bundle_id == 5

    async def test_raises_when_not_owned(self, service, repos):
        repos.bundle.get_owned.return_value = None

        with pytest.raises(NotFoundError, match="Config bundle not found"):
            await service.get_effective_for_user(5, 42)

        repos.skill.list_manifest_for_bundle.assert_not_awaited()