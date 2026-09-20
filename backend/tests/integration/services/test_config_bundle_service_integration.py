import pytest

from src.services.config_bundle_service import ConfigBundleService
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.repositories.agent_profile_repo import AgentProfileRepository


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
        self,
        service,
        sample_user,
        sample_agent_profile,
        sample_skill,
        sample_tool,
        sample_knowledge_pack,
    ):
        bundle = await service.create_bundle(
            user_id=sample_user.id,
            agent_id=sample_agent_profile.id,
            name="bundle-1",
            description="desc",
            skill_ids=[sample_skill.id],
            tool_ids=[sample_tool.id],
            knowledge_pack_ids=[sample_knowledge_pack.id],
        )

        bundles = await service.get_user_bundles(
            user_id=sample_user.id, agent_id=sample_agent_profile.id
        )
        assert bundle.id in [b.id for b in bundles]

    async def test_raises_when_knowledge_pack_missing(
        self, service, sample_user, sample_agent_profile
    ):
        with pytest.raises(
            ValueError, match="Knowledge pack with ID 999999 does not exist"
        ):
            await service.create_bundle(
                user_id=sample_user.id,
                agent_id=sample_agent_profile.id,
                name="bundle-broken",
                description="desc",
                skill_ids=[],
                tool_ids=[],
                knowledge_pack_ids=[999_999],
            )


class TestCloneBundle:
    async def test_clone_is_an_independent_copy_with_same_relations(
        self,
        service,
        config_bundle_with_skill_and_tool,
        sample_config_bundle,
        another_user,
    ):
        clone = await service.clone_bundle(
            bundle_id=sample_config_bundle.id, user_id=another_user.id
        )

        assert clone.id != sample_config_bundle.id
        assert clone.user_id == another_user.id
        assert clone.agent_id == sample_config_bundle.agent_id
        assert clone.name == f"Clone of {sample_config_bundle.name}"

        original_bundles = await service.get_user_bundles(
            user_id=sample_config_bundle.user_id, agent_id=sample_config_bundle.agent_id
        )
        clone_bundles = await service.get_user_bundles(
            user_id=another_user.id, agent_id=sample_config_bundle.agent_id
        )
        assert sample_config_bundle.id in [b.id for b in original_bundles]
        assert clone.id in [b.id for b in clone_bundles]

    async def test_raises_for_unknown_bundle(self, service, sample_user):
        with pytest.raises(
            ValueError, match="Config bundle with ID 999999 does not exist"
        ):
            await service.clone_bundle(bundle_id=999_999, user_id=sample_user.id)


class TestCreateFromAgent:
    async def test_inherits_agent_skills_and_tools(
        self, service, agent_profile_with_skill_and_tool, sample_user
    ):
        bundle = await service.create_from_agent(
            user_id=sample_user.id,
            agent_id=agent_profile_with_skill_and_tool.id,
            name="from-agent",
            description="desc",
        )

        bundles = await service.get_user_bundles(
            user_id=sample_user.id, agent_id=agent_profile_with_skill_and_tool.id
        )
        assert bundle.id in [b.id for b in bundles]

    async def test_raises_for_unknown_agent(self, service, sample_user):
        with pytest.raises(
            ValueError, match="Agent profile with ID 999999 does not exist"
        ):
            await service.create_from_agent(
                user_id=sample_user.id,
                agent_id=999_999,
                name="from-agent",
                description="desc",
            )


class TestGetUserBundles:
    async def test_only_returns_bundles_for_matching_user_and_agent(
        self,
        service,
        sample_config_bundle,
        another_user,
        another_agent_profile,
    ):
        # A bundle for a different (user, agent) pair must not leak in.
        other = await service.create_bundle(
            user_id=another_user.id,
            agent_id=another_agent_profile.id,
            name="unrelated-bundle",
            description="desc",
            skill_ids=[],
            tool_ids=[],
        )

        result = await service.get_user_bundles(
            user_id=sample_config_bundle.user_id, agent_id=sample_config_bundle.agent_id
        )

        ids = [b.id for b in result]
        assert sample_config_bundle.id in ids
        assert other.id not in ids