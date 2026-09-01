import pytest

from src.repositories.config_bundle_repo import ConfigBundleRepository

pytestmark = pytest.mark.db


@pytest.fixture
def config_repo(db_session):
    return ConfigBundleRepository(db_session)


class TestConfigBundleRepository:

    async def test_get_for_user_and_agent_returns_match(
        self, config_repo, sample_config_bundle, sample_user, sample_agent_profile
    ):
        results = await config_repo.get_for_user_and_agent(sample_user.id, sample_agent_profile.id)

        ids = {c.id for c in results}
        assert sample_config_bundle.id in ids

    async def test_get_for_user_and_agent_empty_for_unknown(self, config_repo):
        results = await config_repo.get_for_user_and_agent(999999, 999999)

        assert results == []

    async def test_add_skill_appends_once(self, config_repo, sample_config_bundle, sample_skill):
        await config_repo.add_skill(sample_config_bundle, sample_skill)
        await config_repo.add_skill(sample_config_bundle, sample_skill)

        assert len(sample_config_bundle.skills) == 1

    async def test_remove_skill_removes_existing(self, config_repo, sample_config_bundle, sample_skill):
        await config_repo.add_skill(sample_config_bundle, sample_skill)

        await config_repo.remove_skill(sample_config_bundle, sample_skill)

        assert sample_skill not in sample_config_bundle.skills

    async def test_remove_skill_noop_when_absent(self, config_repo, sample_config_bundle, sample_skill):
        result = await config_repo.remove_skill(sample_config_bundle, sample_skill)

        assert result is sample_config_bundle

    async def test_add_tool_appends_once(self, config_repo, sample_config_bundle, sample_tool):
        await config_repo.add_tool(sample_config_bundle, sample_tool)
        await config_repo.add_tool(sample_config_bundle, sample_tool)

        assert len(sample_config_bundle.tools) == 1

    async def test_remove_tool_removes_existing(self, config_repo, sample_config_bundle, sample_tool):
        await config_repo.add_tool(sample_config_bundle, sample_tool)

        await config_repo.remove_tool(sample_config_bundle, sample_tool)

        assert sample_tool not in sample_config_bundle.tools

    async def test_remove_tool_noop_when_absent(self, config_repo, sample_config_bundle, sample_tool):
        result = await config_repo.remove_tool(sample_config_bundle, sample_tool)

        assert result is sample_config_bundle

    async def test_get_by_id_with_relations_found(self, config_repo, config_bundle_with_skill_and_tool):
        found = await config_repo.get_by_id_with_relations(config_bundle_with_skill_and_tool.id)

        assert found is not None
        assert len(found.skills) == 1
        assert len(found.tools) == 1

    async def test_get_by_id_with_relations_not_found(self, config_repo):
        found = await config_repo.get_by_id_with_relations(999999)

        assert found is None