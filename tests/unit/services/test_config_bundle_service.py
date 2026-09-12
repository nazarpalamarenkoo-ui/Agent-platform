from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.config_bundle_service import ConfigBundleService


@pytest.fixture
def config_bundle_repo():
    return AsyncMock()


@pytest.fixture
def skill_repo():
    return AsyncMock()


@pytest.fixture
def tool_repo():
    return AsyncMock()


@pytest.fixture
def knowledge_pack_repo():
    return AsyncMock()


@pytest.fixture
def agent_profile_repo():
    return AsyncMock()


@pytest.fixture
def service(
    config_bundle_repo, skill_repo, tool_repo, knowledge_pack_repo, agent_profile_repo
):
    return ConfigBundleService(
        config_bundle_repo, skill_repo, tool_repo, knowledge_pack_repo, agent_profile_repo
    )


class TestCreateBundle:
    async def test_creates_bundle_with_skills_tools_and_packs(
        self, service, config_bundle_repo, skill_repo, tool_repo, knowledge_pack_repo
    ):
        bundle = MagicMock()
        config_bundle_repo.create.return_value = bundle
        skill_repo.get_by_id.return_value = MagicMock()
        tool_repo.get_by_id.return_value = MagicMock()
        knowledge_pack_repo.get_by_id.return_value = MagicMock()

        result = await service.create_bundle(
            user_id=1,
            agent_id=2,
            name="bundle",
            description="desc",
            skill_ids=[1],
            tool_ids=[2],
            knowledge_pack_ids=[3],
        )

        assert result is bundle
        config_bundle_repo.create.assert_awaited_once_with(
            user_id=1, agent_id=2, name="bundle", description="desc"
        )
        config_bundle_repo.add_skill.assert_awaited_once()
        config_bundle_repo.add_tool.assert_awaited_once()
        config_bundle_repo.add_knowledge_pack.assert_awaited_once()

    async def test_knowledge_pack_ids_defaults_to_none(
        self, service, config_bundle_repo, knowledge_pack_repo
    ):
        config_bundle_repo.create.return_value = MagicMock()

        await service.create_bundle(
            user_id=1,
            agent_id=2,
            name="bundle",
            description="desc",
            skill_ids=[],
            tool_ids=[],
        )

        knowledge_pack_repo.get_by_id.assert_not_awaited()
        config_bundle_repo.add_knowledge_pack.assert_not_awaited()

    async def test_raises_when_skill_missing(
        self, service, config_bundle_repo, skill_repo
    ):
        config_bundle_repo.create.return_value = MagicMock()
        skill_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="Skill with ID 1 does not exist"):
            await service.create_bundle(
                user_id=1,
                agent_id=2,
                name="b",
                description="d",
                skill_ids=[1],
                tool_ids=[],
            )

    async def test_raises_when_tool_missing(
        self, service, config_bundle_repo, tool_repo
    ):
        config_bundle_repo.create.return_value = MagicMock()
        tool_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="Tool with ID 9 does not exist"):
            await service.create_bundle(
                user_id=1,
                agent_id=2,
                name="b",
                description="d",
                skill_ids=[],
                tool_ids=[9],
            )

    async def test_raises_when_knowledge_pack_missing(
        self, service, config_bundle_repo, knowledge_pack_repo
    ):
        config_bundle_repo.create.return_value = MagicMock()
        knowledge_pack_repo.get_by_id.return_value = None

        with pytest.raises(
            ValueError, match="Knowledge pack with ID 7 does not exist"
        ):
            await service.create_bundle(
                user_id=1,
                agent_id=2,
                name="b",
                description="d",
                skill_ids=[],
                tool_ids=[],
                knowledge_pack_ids=[7],
            )


class TestCloneBundle:
    async def test_clones_bundle_with_all_relations(
        self, service, config_bundle_repo
    ):
        skill = MagicMock()
        tool = MagicMock()
        pack = MagicMock()
        original = MagicMock(
            agent_id=99,
            description="Original desc",
            skills=[skill],
            tools=[tool],
            knowledge_packs=[pack],
        )
        original.name = "Original"
        config_bundle_repo.get_by_id_with_relations.return_value = original
        cloned = MagicMock()
        config_bundle_repo.create.return_value = cloned

        result = await service.clone_bundle(bundle_id=1, user_id=5)

        assert result is cloned
        config_bundle_repo.create.assert_awaited_once_with(
            user_id=5,
            agent_id=99,
            name="Clone of Original",
            description="Original desc",
        )
        config_bundle_repo.add_skill.assert_awaited_once_with(cloned, skill)
        config_bundle_repo.add_tool.assert_awaited_once_with(cloned, tool)
        config_bundle_repo.add_knowledge_pack.assert_awaited_once_with(cloned, pack)

    async def test_raises_when_original_not_found(
        self, service, config_bundle_repo
    ):
        config_bundle_repo.get_by_id_with_relations.return_value = None

        with pytest.raises(
            ValueError, match="Config bundle with ID 1 does not exist"
        ):
            await service.clone_bundle(bundle_id=1, user_id=5)

        config_bundle_repo.create.assert_not_awaited()


class TestCreateFromAgent:
    async def test_creates_bundle_from_agent_skills_and_tools(
        self, service, config_bundle_repo, agent_profile_repo
    ):
        skill = MagicMock()
        tool = MagicMock()
        agent = MagicMock(skills=[skill], tools=[tool])
        agent_profile_repo.get_by_id.return_value = agent
        bundle = MagicMock()
        config_bundle_repo.create.return_value = bundle

        result = await service.create_from_agent(
            user_id=1, agent_id=2, name="b", description="d"
        )

        assert result is bundle
        config_bundle_repo.add_skill.assert_awaited_once_with(bundle, skill)
        config_bundle_repo.add_tool.assert_awaited_once_with(bundle, tool)

    async def test_raises_when_agent_not_found(
        self, service, agent_profile_repo, config_bundle_repo
    ):
        agent_profile_repo.get_by_id.return_value = None

        with pytest.raises(
            ValueError, match="Agent profile with ID 2 does not exist"
        ):
            await service.create_from_agent(
                user_id=1, agent_id=2, name="b", description="d"
            )

        config_bundle_repo.create.assert_not_awaited()


class TestGetUserBundles:
    async def test_delegates_to_repo(self, service, config_bundle_repo):
        bundles = [MagicMock()]
        config_bundle_repo.get_for_user_and_agent.return_value = bundles

        result = await service.get_user_bundles(user_id=1, agent_id=2)

        assert result is bundles
        config_bundle_repo.get_for_user_and_agent.assert_awaited_once_with(1, 2)