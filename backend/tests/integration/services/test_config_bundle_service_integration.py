import pytest

from src.repositories.agent_profile_repo import AgentProfileRepository
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.services.config_bundle_service import (
    INHERITED,
    UNAVAILABLE,
    ConfigBundleService,
)
from src.services.errors import ConflictError, NotFoundError


@pytest.fixture
def service(db_session):
    return ConfigBundleService(
        ConfigBundleRepository(db_session),
        SkillRepository(db_session),
        ToolDefinitionRepository(db_session),
        KnowledgePackRepository(db_session),
        AgentProfileRepository(db_session),
    )


class TestCreateBundle:
    async def test_persists_bundle_with_skills_tools_and_packs(
        self, service, sample_user, sample_agent_profile,
        sample_skill, sample_tool, sample_knowledge_pack,
    ):
        bundle = await service.create_bundle(
            sample_user.id, sample_agent_profile.id, "  bundle-1 ", "desc",
            [sample_skill.id, sample_skill.id], [sample_tool.id],
            [sample_knowledge_pack.id],
        )

        assert bundle.name == "bundle-1"
        assert bundle.user_id == sample_user.id
        assert [s.id for s in bundle.skills] == [sample_skill.id]
        assert [t.id for t in bundle.tools] == [sample_tool.id]
        assert [p.id for p in bundle.knowledge_packs] == [sample_knowledge_pack.id]

    async def test_does_not_duplicate_items_inherited_from_profile(
        self, service, sample_user, agent_profile_with_skill_and_tool,
        sample_skill, sample_tool, make_skill,
    ):
        extra = await make_skill()

        bundle = await service.create_bundle(
            sample_user.id, agent_profile_with_skill_and_tool.id, "inh", "d",
            [sample_skill.id, extra.id], [sample_tool.id],
        )

        assert [s.id for s in bundle.skills] == [extra.id]
        assert bundle.tools == []

    async def test_raises_for_unknown_agent(self, service, sample_user):
        with pytest.raises(NotFoundError, match="Agent profile not found"):
            await service.create_bundle(sample_user.id, 999_999, "n", "d", [], [])

    async def test_raises_for_empty_name(self, service, sample_user, sample_agent_profile):
        with pytest.raises(ValueError, match="Bundle name must not be empty"):
            await service.create_bundle(
                sample_user.id, sample_agent_profile.id, "  ", "d", [], []
            )

    async def test_raises_on_duplicate_name_for_same_user(
        self, service, sample_user, sample_agent_profile
    ):
        await service.create_bundle(sample_user.id, sample_agent_profile.id, "dup", "d", [], [])

        with pytest.raises(ConflictError, match="Bundle 'dup' already exists"):
            await service.create_bundle(
                sample_user.id, sample_agent_profile.id, "dup", "d", [], []
            )

    async def test_same_name_allowed_for_different_users(
        self, service, sample_user, another_user, sample_agent_profile
    ):
        await service.create_bundle(sample_user.id, sample_agent_profile.id, "same", "d", [], [])
        other = await service.create_bundle(
            another_user.id, sample_agent_profile.id, "same", "d", [], []
        )
        assert other.user_id == another_user.id

    async def test_raises_for_missing_pack(self, service, sample_user, sample_agent_profile):
        with pytest.raises(NotFoundError, match=UNAVAILABLE):
            await service.create_bundle(
                sample_user.id, sample_agent_profile.id, "b", "d", [], [], [999_999]
            )

    async def test_cannot_use_foreign_private_skill_or_tool(
        self, service, sample_user, another_user, sample_agent_profile, make_skill, make_tool
    ):
        foreign_skill = await make_skill(owner=another_user)
        foreign_tool = await make_tool(owner=another_user)

        with pytest.raises(NotFoundError, match=UNAVAILABLE):
            await service.create_bundle(
                sample_user.id, sample_agent_profile.id, "b1", "d", [foreign_skill.id], []
            )
        with pytest.raises(NotFoundError, match=UNAVAILABLE):
            await service.create_bundle(
                sample_user.id, sample_agent_profile.id, "b2", "d", [], [foreign_tool.id]
            )

    async def test_can_use_own_private_skill(
        self, service, sample_user, sample_agent_profile, make_skill
    ):
        private = await make_skill(owner=sample_user)

        bundle = await service.create_bundle(
            sample_user.id, sample_agent_profile.id, "mine", "d", [private.id], []
        )

        assert [s.id for s in bundle.skills] == [private.id]


class TestCreateCustomAgentAndFromAgent:
    async def test_custom_agent_uses_neutral_profile(
        self, service, sample_user, make_agent, sample_skill
    ):
        neutral = await make_agent(is_neutral=True)

        bundle = await service.create_custom_agent(
            sample_user.id, "custom", "d", skill_ids=[sample_skill.id]
        )

        assert bundle.agent_id == neutral.id
        assert [s.id for s in bundle.skills] == [sample_skill.id]

    async def test_custom_agent_raises_without_neutral_profile(self, service, sample_user):
        with pytest.raises(NotFoundError, match="Neutral agent profile is not configured"):
            await service.create_custom_agent(sample_user.id, "custom", "d")

    async def test_create_from_agent_has_no_own_items(
        self, service, sample_user, agent_profile_with_skill_and_tool
    ):
        bundle = await service.create_from_agent(
            sample_user.id, agent_profile_with_skill_and_tool.id, "from-agent", "d"
        )

        assert bundle.agent_id == agent_profile_with_skill_and_tool.id
        assert bundle.skills == []
        assert bundle.tools == []


class TestCloneBundle:
    async def test_clone_copies_relations_and_description(
        self, service, config_bundle_with_skill_and_tool, sample_user,
        sample_knowledge_pack, db_session,
    ):
        original = config_bundle_with_skill_and_tool
        await ConfigBundleRepository(db_session).add_knowledge_pack(
            original, sample_knowledge_pack
        )

        clone = await service.clone_bundle(original.id, sample_user.id, "clone")

        assert clone.id != original.id
        assert clone.description == original.description
        assert clone.agent_id == original.agent_id
        assert {s.id for s in clone.skills} == {s.id for s in original.skills}
        assert {t.id for t in clone.tools} == {t.id for t in original.tools}
        assert [p.id for p in clone.knowledge_packs] == [sample_knowledge_pack.id]

    async def test_clone_overrides_description(
        self, service, sample_config_bundle, sample_user
    ):
        clone = await service.clone_bundle(
            sample_config_bundle.id, sample_user.id, "clone", description="new"
        )
        assert clone.description == "new"

    async def test_clone_is_independent_from_original(
        self, service, config_bundle_with_skill_and_tool, sample_user, sample_skill
    ):
        clone = await service.clone_bundle(
            config_bundle_with_skill_and_tool.id, sample_user.id, "clone"
        )

        await service.remove_from_bundle(clone.id, sample_user.id, skill_ids=[sample_skill.id])

        original = await service.get_bundle(config_bundle_with_skill_and_tool.id, sample_user.id)
        assert [s.id for s in original.skills] == [sample_skill.id]

    async def test_clone_raises_on_name_conflict(
        self, service, sample_config_bundle, sample_user
    ):
        with pytest.raises(ConflictError):
            await service.clone_bundle(
                sample_config_bundle.id, sample_user.id, sample_config_bundle.name
            )

    async def test_cannot_clone_foreign_bundle(
        self, service, sample_config_bundle, another_user
    ):
        with pytest.raises(NotFoundError, match="Config bundle not found"):
            await service.clone_bundle(sample_config_bundle.id, another_user.id, "stolen")


class TestGetBundles:
    async def test_get_bundle_is_scoped_to_owner(
        self, service, sample_config_bundle, another_user
    ):
        with pytest.raises(NotFoundError):
            await service.get_bundle(sample_config_bundle.id, another_user.id)

    async def test_filters_by_user_and_agent(
        self, service, sample_user, another_user, sample_agent_profile,
        another_agent_profile, sample_config_bundle,
    ):
        other = await service.create_bundle(
            another_user.id, another_agent_profile.id, "unrelated", "d", [], []
        )

        result = await service.get_user_bundles(
            sample_user.id, agent_id=sample_agent_profile.id
        )

        ids = [b.id for b in result]
        assert sample_config_bundle.id in ids
        assert other.id not in ids

    async def test_lists_all_for_user_with_pagination(
        self, service, sample_user, sample_agent_profile
    ):
        for i in range(3):
            await service.create_bundle(
                sample_user.id, sample_agent_profile.id, f"b{i}", "d", [], []
            )

        page1 = await service.get_user_bundles(sample_user.id, limit=2, offset=0)
        page2 = await service.get_user_bundles(sample_user.id, limit=2, offset=2)

        assert len(page1) == 2
        assert len(page2) == 1


class TestUpdateAndDelete:
    async def test_update_name_and_description(
        self, service, sample_config_bundle, sample_user
    ):
        updated = await service.update_bundle(
            sample_config_bundle.id, sample_user.id, name=" renamed ", description="new"
        )

        assert updated.name == "renamed"
        assert updated.description == "new"

    async def test_update_to_taken_name_conflicts(
        self, service, sample_config_bundle, sample_user, sample_agent_profile
    ):
        other = await service.create_bundle(
            sample_user.id, sample_agent_profile.id, "other", "d", [], []
        )

        with pytest.raises(ConflictError):
            await service.update_bundle(other.id, sample_user.id, name=sample_config_bundle.name)

    async def test_update_with_same_name_is_allowed(
        self, service, sample_config_bundle, sample_user
    ):
        updated = await service.update_bundle(
            sample_config_bundle.id, sample_user.id, name=sample_config_bundle.name
        )
        assert updated.id == sample_config_bundle.id

    async def test_delete_removes_bundle(self, service, sample_config_bundle, sample_user):
        await service.delete_bundle(sample_config_bundle.id, sample_user.id)

        with pytest.raises(NotFoundError):
            await service.get_bundle(sample_config_bundle.id, sample_user.id)

    async def test_cannot_delete_foreign_bundle(
        self, service, sample_config_bundle, another_user
    ):
        with pytest.raises(NotFoundError):
            await service.delete_bundle(sample_config_bundle.id, another_user.id)


class TestAddToBundle:
    async def test_adds_items(
        self, service, sample_config_bundle, sample_user, sample_skill,
        sample_tool, sample_knowledge_pack,
    ):
        bundle = await service.add_to_bundle(
            sample_config_bundle.id, sample_user.id,
            skill_ids=[sample_skill.id], tool_ids=[sample_tool.id],
            knowledge_pack_ids=[sample_knowledge_pack.id],
        )

        assert [s.id for s in bundle.skills] == [sample_skill.id]
        assert [t.id for t in bundle.tools] == [sample_tool.id]
        assert [p.id for p in bundle.knowledge_packs] == [sample_knowledge_pack.id]

    async def test_skips_items_inherited_from_profile(
        self, service, sample_user, agent_profile_with_skill_and_tool, sample_skill, make_bundle
    ):
        bundle = await make_bundle(sample_user, agent_profile_with_skill_and_tool)

        updated = await service.add_to_bundle(
            bundle.id, sample_user.id, skill_ids=[sample_skill.id]
        )

        assert updated.skills == []

    async def test_raises_for_unavailable_items(
        self, service, sample_config_bundle, sample_user
    ):
        with pytest.raises(NotFoundError, match=UNAVAILABLE):
            await service.add_to_bundle(
                sample_config_bundle.id, sample_user.id, skill_ids=[999_999]
            )

    async def test_noop_without_arguments(self, service, sample_config_bundle, sample_user):
        bundle = await service.add_to_bundle(sample_config_bundle.id, sample_user.id)
        assert bundle.skills == []


class TestRemoveFromBundle:
    async def test_removes_own_items(
        self, service, config_bundle_with_skill_and_tool, sample_user,
        sample_skill, sample_tool,
    ):
        bundle = await service.remove_from_bundle(
            config_bundle_with_skill_and_tool.id, sample_user.id,
            skill_ids=[sample_skill.id], tool_ids=[sample_tool.id],
        )

        assert bundle.skills == []
        assert bundle.tools == []

    async def test_removes_knowledge_pack(
        self, service, config_bundle_with_knowledge_pack, sample_user, sample_knowledge_pack
    ):
        bundle = await service.remove_from_bundle(
            config_bundle_with_knowledge_pack.id, sample_user.id,
            knowledge_pack_ids=[sample_knowledge_pack.id],
        )
        assert bundle.knowledge_packs == []

    async def test_cannot_remove_inherited_skill(
        self, service, sample_user, agent_profile_with_skill_and_tool, sample_skill, make_bundle
    ):
        bundle = await make_bundle(sample_user, agent_profile_with_skill_and_tool)

        with pytest.raises(ConflictError, match=INHERITED):
            await service.remove_from_bundle(
                bundle.id, sample_user.id, skill_ids=[sample_skill.id]
            )

    async def test_cannot_remove_inherited_tool(
        self, service, sample_user, agent_profile_with_skill_and_tool, sample_tool, make_bundle
    ):
        bundle = await make_bundle(sample_user, agent_profile_with_skill_and_tool)

        with pytest.raises(ConflictError, match=INHERITED):
            await service.remove_from_bundle(
                bundle.id, sample_user.id, tool_ids=[sample_tool.id]
            )

    async def test_ignores_items_not_in_bundle(
        self, service, sample_config_bundle, sample_user, sample_skill
    ):
        bundle = await service.remove_from_bundle(
            sample_config_bundle.id, sample_user.id, skill_ids=[sample_skill.id]
        )
        assert bundle.skills == []

    async def test_failed_removal_changes_nothing(
        self, service, sample_user, agent_profile_with_skill_and_tool,
        sample_skill, make_skill, make_bundle, db_session,
    ):
        extra = await make_skill()
        bundle = await make_bundle(sample_user, agent_profile_with_skill_and_tool)
        await ConfigBundleRepository(db_session).add_skill(bundle, extra)

        with pytest.raises(ConflictError):
            await service.remove_from_bundle(
                bundle.id, sample_user.id, skill_ids=[extra.id, sample_skill.id]
            )

        reloaded = await service.get_bundle(bundle.id, sample_user.id)
        assert [s.id for s in reloaded.skills] == [extra.id]