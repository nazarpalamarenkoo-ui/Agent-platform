import pytest

from src.repositories.agent_profile_repo import AgentProfileRepository
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.services.effective_bundle_service import (
    EffectivePack,
    EffectiveSkill,
    EffectiveTool,
    EffectiveBundleService,
    compute_version_hash,
)
from src.services.errors import NotFoundError


@pytest.fixture
def service(db_session):
    return EffectiveBundleService(
        ConfigBundleRepository(db_session),
        SkillRepository(db_session),
        ToolDefinitionRepository(db_session),
        KnowledgePackRepository(db_session),
        AgentProfileRepository(db_session),
    )


class TestComputeVersionHash:
    def test_is_independent_of_item_order(self):
        s1, s2 = EffectiveSkill(1, "a", "h1", False), EffectiveSkill(2, "b", "h2", False)

        assert compute_version_hash(1, (s1, s2), (), ()) == compute_version_hash(1, (s2, s1), (), ())

    def test_changes_when_skill_content_hash_changes(self):
        before = compute_version_hash(1, (EffectiveSkill(1, "a", "h1", False),), (), ())
        after = compute_version_hash(1, (EffectiveSkill(1, "a", "h2", False),), (), ())
        assert before != after

    def test_changes_when_tool_url_changes(self):
        t1 = EffectiveTool(1, "t", "https://a", "none", False)
        t2 = EffectiveTool(1, "t", "https://b", "none", False)
        assert compute_version_hash(1, (), (t1,), ()) != compute_version_hash(1, (), (t2,), ())

    def test_changes_when_pack_version_changes(self):
        p1, p2 = EffectivePack(1, "p", 1, False), EffectivePack(1, "p", 2, False)
        assert compute_version_hash(1, (), (), (p1,)) != compute_version_hash(1, (), (), (p2,))

    def test_changes_with_agent_id(self):
        assert compute_version_hash(1, (), (), ()) != compute_version_hash(2, (), (), ())

    def test_archived_flag_does_not_affect_hash(self):
        a = compute_version_hash(1, (EffectiveSkill(1, "a", "h", False),), (), ())
        b = compute_version_hash(1, (EffectiveSkill(1, "a", "h", True),), (), ())
        assert a == b


class TestGetEffective:
    async def test_contains_bundle_items_and_agent_info(
        self, service, config_bundle_with_skill_and_tool, config_bundle_with_knowledge_pack,
        sample_skill, sample_tool, sample_knowledge_pack, sample_agent_profile,
    ):
        effective = await service.get_effective(config_bundle_with_skill_and_tool.id)

        assert effective.bundle_id == config_bundle_with_skill_and_tool.id
        assert effective.agent_id == sample_agent_profile.id
        assert effective.agent_name == sample_agent_profile.agent_name
        assert sample_skill.id in {s.id for s in effective.skills}
        assert sample_tool.id in {t.id for t in effective.tools}
        assert sample_knowledge_pack.id in {p.id for p in effective.packs}
        assert len(effective.version_hash) == 64

    async def test_marks_custom_tools(
        self, service, sample_user, sample_config_bundle, make_tool, db_session
    ):
        custom = await make_tool(owner=sample_user)
        global_tool = await make_tool()
        repo = ConfigBundleRepository(db_session)
        await repo.add_tool(sample_config_bundle, custom)
        await repo.add_tool(sample_config_bundle, global_tool)

        effective = await service.get_effective(sample_config_bundle.id)

        by_id = {t.id: t for t in effective.tools}
        assert by_id[custom.id].custom is True
        assert by_id[global_tool.id].custom is False

    async def test_hash_is_stable_between_calls(self, service, config_bundle_with_skill_and_tool):
        first = await service.get_effective(config_bundle_with_skill_and_tool.id)
        second = await service.get_effective(config_bundle_with_skill_and_tool.id)

        assert first.version_hash == second.version_hash

    async def test_hash_changes_when_item_added(
        self, service, sample_config_bundle, make_skill, db_session
    ):
        before = await service.get_effective(sample_config_bundle.id)

        await ConfigBundleRepository(db_session).add_skill(
            sample_config_bundle, await make_skill()
        )
        after = await service.get_effective(sample_config_bundle.id)

        assert before.version_hash != after.version_hash

    async def test_flags_archived_skill_without_changing_hash(
        self, service, sample_config_bundle, make_skill, db_session
    ):
        skill = await make_skill()
        await ConfigBundleRepository(db_session).add_skill(sample_config_bundle, skill)
        before = await service.get_effective(sample_config_bundle.id)

        await SkillRepository(db_session).archive(skill)
        after = await service.get_effective(sample_config_bundle.id)

        flags = {s.id: s.archived for s in after.skills}
        assert flags[skill.id] is True
        assert before.version_hash == after.version_hash

    async def test_raises_for_unknown_bundle(self, service):
        with pytest.raises(NotFoundError, match="Config bundle not found"):
            await service.get_effective(999_999)


class TestGetEffectiveForUser:
    async def test_returns_for_owner(self, service, sample_config_bundle, sample_user):
        effective = await service.get_effective_for_user(
            sample_config_bundle.id, sample_user.id
        )
        assert effective.bundle_id == sample_config_bundle.id

    async def test_raises_for_non_owner(self, service, sample_config_bundle, another_user):
        with pytest.raises(NotFoundError):
            await service.get_effective_for_user(sample_config_bundle.id, another_user.id)