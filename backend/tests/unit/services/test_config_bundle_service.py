from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.config_bundle_service import INHERITED, UNAVAILABLE, ConfigBundleService
from src.services.errors import ConflictError, NotFoundError


def obj(id):
    return SimpleNamespace(id=id)


def make_profile(skill_ids=(), tool_ids=(), id=2):
    return SimpleNamespace(
        id=id, skills=[obj(i) for i in skill_ids], tools=[obj(i) for i in tool_ids]
    )


@pytest.fixture
def config_bundle_repo():
    repo = AsyncMock()
    repo.get_by_user_and_name.return_value = None
    repo.create.return_value = SimpleNamespace(id=100)
    return repo


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
    repo = AsyncMock()
    repo.get_active.return_value = make_profile()
    repo.admin_get_by_id.return_value = make_profile()
    return repo


@pytest.fixture
def service(config_bundle_repo, skill_repo, tool_repo, knowledge_pack_repo, agent_profile_repo):
    return ConfigBundleService(
        config_bundle_repo, skill_repo, tool_repo, knowledge_pack_repo, agent_profile_repo
    )


class TestCreateBundle:
    async def test_creates_bundle_with_items_and_returns_reloaded(
        self, service, config_bundle_repo, skill_repo, tool_repo, knowledge_pack_repo
    ):
        s, t, p = obj(1), obj(2), obj(3)
        skill_repo.get_visible_many.return_value = [s]
        tool_repo.get_visible_many.return_value = [t]
        knowledge_pack_repo.get_active_many.return_value = [p]
        loaded = SimpleNamespace(id=100)
        config_bundle_repo.get_owned.return_value = loaded

        result = await service.create_bundle(
            user_id=1, agent_id=2, name="  bundle  ", description="desc",
            skill_ids=[1], tool_ids=[2], knowledge_pack_ids=[3],
        )

        assert result is loaded
        config_bundle_repo.create.assert_awaited_once_with(
            user_id=1, agent_id=2, name="bundle", description="desc"
        )
        config_bundle_repo.add_skill.assert_awaited_once_with(config_bundle_repo.create.return_value, s)
        config_bundle_repo.add_tool.assert_awaited_once_with(config_bundle_repo.create.return_value, t)
        config_bundle_repo.add_knowledge_pack.assert_awaited_once_with(
            config_bundle_repo.create.return_value, p
        )
        config_bundle_repo.get_owned.assert_awaited_once_with(100, 1)

    async def test_skips_items_inherited_from_profile(
        self, service, config_bundle_repo, skill_repo, tool_repo, agent_profile_repo
    ):
        agent_profile_repo.get_active.return_value = make_profile(skill_ids=[1], tool_ids=[5])
        skill_repo.get_visible_many.return_value = [obj(1), obj(2)]
        tool_repo.get_visible_many.return_value = [obj(5), obj(6)]

        await service.create_bundle(1, 2, "b", "d", skill_ids=[1, 2], tool_ids=[5, 6])

        assert [c.args[1].id for c in config_bundle_repo.add_skill.await_args_list] == [2]
        assert [c.args[1].id for c in config_bundle_repo.add_tool.await_args_list] == [6]

    async def test_deduplicates_requested_ids(self, service, skill_repo):
        skill_repo.get_visible_many.return_value = [obj(1), obj(2)]

        await service.create_bundle(1, 2, "b", "d", skill_ids=[1, 1, 2], tool_ids=[])

        skill_repo.get_visible_many.assert_awaited_once_with([1, 2], 1)

    async def test_does_not_query_repos_for_empty_lists(
        self, service, skill_repo, tool_repo, knowledge_pack_repo
    ):
        await service.create_bundle(1, 2, "b", "d", skill_ids=[], tool_ids=[])

        skill_repo.get_visible_many.assert_not_awaited()
        tool_repo.get_visible_many.assert_not_awaited()
        knowledge_pack_repo.get_active_many.assert_not_awaited()

    @pytest.mark.parametrize("name", ["", "   ", None])
    async def test_rejects_empty_name(self, service, name, config_bundle_repo):
        with pytest.raises(ValueError, match="Bundle name must not be empty"):
            await service.create_bundle(1, 2, name, "d", skill_ids=[], tool_ids=[])

        config_bundle_repo.create.assert_not_awaited()

    async def test_raises_when_profile_not_found(self, service, agent_profile_repo, config_bundle_repo):
        agent_profile_repo.get_active.return_value = None

        with pytest.raises(NotFoundError, match="Agent profile not found"):
            await service.create_bundle(1, 2, "b", "d", skill_ids=[], tool_ids=[])

        config_bundle_repo.create.assert_not_awaited()

    async def test_raises_when_name_taken(self, service, config_bundle_repo):
        config_bundle_repo.get_by_user_and_name.return_value = obj(5)

        with pytest.raises(ConflictError, match="Bundle 'b' already exists"):
            await service.create_bundle(1, 2, "b", "d", skill_ids=[], tool_ids=[])

        config_bundle_repo.create.assert_not_awaited()

    @pytest.mark.parametrize(
        "repo_fixture, repo_method, kwargs",
        [
            ("skill_repo", "get_visible_many", {"skill_ids": [1, 2], "tool_ids": []}),
            ("tool_repo", "get_visible_many", {"skill_ids": [], "tool_ids": [1, 2]}),
            ("knowledge_pack_repo", "get_active_many",
             {"skill_ids": [], "tool_ids": [], "knowledge_pack_ids": [1, 2]}),
        ],
    )
    async def test_raises_when_any_item_unavailable(
        self, service, config_bundle_repo, request, repo_fixture, repo_method, kwargs
    ):
        getattr(request.getfixturevalue(repo_fixture), repo_method).return_value = [obj(1)]

        with pytest.raises(NotFoundError, match=UNAVAILABLE):
            await service.create_bundle(1, 2, "b", "d", **kwargs)

        config_bundle_repo.create.assert_not_awaited()


class TestCreateCustomAgent:
    async def test_uses_neutral_profile(self, service, config_bundle_repo, agent_profile_repo):
        agent_profile_repo.get_neutral.return_value = obj(77)
        agent_profile_repo.get_active.return_value = make_profile(id=77)

        await service.create_custom_agent(user_id=1, name="mine", description="d")

        assert config_bundle_repo.create.await_args.kwargs["agent_id"] == 77

    async def test_raises_when_neutral_missing(self, service, agent_profile_repo, config_bundle_repo):
        agent_profile_repo.get_neutral.return_value = None

        with pytest.raises(NotFoundError, match="Neutral agent profile is not configured"):
            await service.create_custom_agent(user_id=1, name="mine", description="d")

        config_bundle_repo.create.assert_not_awaited()


class TestCreateFromAgent:
    async def test_creates_bundle_without_own_items(
        self, service, config_bundle_repo, skill_repo, tool_repo
    ):
        await service.create_from_agent(user_id=1, agent_id=2, name="b", description="d")

        config_bundle_repo.create.assert_awaited_once()
        config_bundle_repo.add_skill.assert_not_awaited()
        config_bundle_repo.add_tool.assert_not_awaited()
        config_bundle_repo.add_knowledge_pack.assert_not_awaited()


class TestCloneBundle:
    @pytest.fixture
    def original(self, config_bundle_repo):
        bundle = SimpleNamespace(
            id=1, agent_id=99, description="Original desc",
            skills=[obj(1)], tools=[obj(2)], knowledge_packs=[obj(3)],
        )
        config_bundle_repo.get_owned.return_value = bundle
        return bundle

    async def test_copies_all_relations(self, service, config_bundle_repo, original):
        await service.clone_bundle(1, 5, name=" Copy ")

        cloned = config_bundle_repo.create.return_value
        config_bundle_repo.create.assert_awaited_once_with(
            user_id=5, agent_id=99, name="Copy", description="Original desc"
        )
        config_bundle_repo.add_skill.assert_awaited_once_with(cloned, original.skills[0])
        config_bundle_repo.add_tool.assert_awaited_once_with(cloned, original.tools[0])
        config_bundle_repo.add_knowledge_pack.assert_awaited_once_with(
            cloned, original.knowledge_packs[0]
        )

    async def test_description_override(self, service, config_bundle_repo, original):
        await service.clone_bundle(1, 5, name="Copy", description="")

        assert config_bundle_repo.create.await_args.kwargs["description"] == ""

    async def test_raises_when_original_not_owned(self, service, config_bundle_repo):
        config_bundle_repo.get_owned.return_value = None

        with pytest.raises(NotFoundError):
            await service.clone_bundle(1, 5, name="Copy")

        config_bundle_repo.create.assert_not_awaited()

    async def test_raises_when_name_taken(self, service, config_bundle_repo, original):
        config_bundle_repo.get_by_user_and_name.return_value = obj(8)

        with pytest.raises(ConflictError):
            await service.clone_bundle(1, 5, name="Copy")

        config_bundle_repo.create.assert_not_awaited()


class TestGetBundles:
    async def test_get_bundle_scoped_to_owner(self, service, config_bundle_repo):
        bundle = obj(1)
        config_bundle_repo.get_owned.return_value = bundle

        assert await service.get_bundle(1, 5) is bundle
        config_bundle_repo.get_owned.assert_awaited_once_with(1, 5)

    async def test_get_bundle_not_found(self, service, config_bundle_repo):
        config_bundle_repo.get_owned.return_value = None

        with pytest.raises(NotFoundError, match="Config bundle not found"):
            await service.get_bundle(1, 5)

    async def test_filters_by_agent(self, service, config_bundle_repo):
        bundles = [obj(1)]
        config_bundle_repo.get_for_user_and_agent.return_value = bundles

        result = await service.get_user_bundles(user_id=1, agent_id=2)

        assert result is bundles
        config_bundle_repo.get_for_user_and_agent.assert_awaited_once_with(1, 2)
        config_bundle_repo.list_for_user.assert_not_awaited()

    async def test_lists_all_with_pagination(self, service, config_bundle_repo):
        await service.get_user_bundles(user_id=1, limit=10, offset=20)

        config_bundle_repo.list_for_user.assert_awaited_once_with(1, limit=10, offset=20)
        config_bundle_repo.get_for_user_and_agent.assert_not_awaited()


class TestUpdateBundle:
    @pytest.fixture
    def bundle(self, config_bundle_repo):
        b = SimpleNamespace(id=1, name="old", description="old desc")
        config_bundle_repo.get_owned.return_value = b
        return b

    async def test_updates_name_and_description(self, service, config_bundle_repo, bundle):
        await service.update_bundle(1, 5, name=" new ", description="new desc")

        config_bundle_repo.update.assert_awaited_once_with(bundle, name="new", description="new desc")

    async def test_no_update_when_nothing_changed(self, service, config_bundle_repo, bundle):
        await service.update_bundle(1, 5, name="old", description="old desc")
        await service.update_bundle(1, 5)

        config_bundle_repo.update.assert_not_awaited()
        config_bundle_repo.get_by_user_and_name.assert_not_awaited()

    async def test_name_conflict_excludes_self(self, service, config_bundle_repo, bundle):
        config_bundle_repo.get_by_user_and_name.return_value = bundle  # same bundle

        await service.update_bundle(1, 5, name="renamed")

        config_bundle_repo.update.assert_awaited_once_with(bundle, name="renamed")

    async def test_raises_when_name_used_by_other_bundle(self, service, config_bundle_repo, bundle):
        config_bundle_repo.get_by_user_and_name.return_value = obj(2)

        with pytest.raises(ConflictError):
            await service.update_bundle(1, 5, name="taken")

        config_bundle_repo.update.assert_not_awaited()

    async def test_rejects_blank_name(self, service, bundle):
        with pytest.raises(ValueError, match="must not be empty"):
            await service.update_bundle(1, 5, name="  ")

    async def test_allows_empty_description(self, service, config_bundle_repo, bundle):
        await service.update_bundle(1, 5, description="")

        config_bundle_repo.update.assert_awaited_once_with(bundle, description="")


class TestDeleteBundle:
    async def test_deletes_owned_bundle(self, service, config_bundle_repo):
        bundle = obj(1)
        config_bundle_repo.get_owned.return_value = bundle

        await service.delete_bundle(1, 5)

        config_bundle_repo.delete.assert_awaited_once_with(bundle)

    async def test_raises_when_not_owned(self, service, config_bundle_repo):
        config_bundle_repo.get_owned.return_value = None

        with pytest.raises(NotFoundError):
            await service.delete_bundle(1, 5)

        config_bundle_repo.delete.assert_not_awaited()


class TestAddToBundle:
    @pytest.fixture
    def bundle(self, config_bundle_repo):
        b = SimpleNamespace(id=1, agent_id=2)
        config_bundle_repo.get_owned.return_value = b
        return b

    async def test_adds_items_except_inherited(
        self, service, config_bundle_repo, skill_repo, tool_repo, knowledge_pack_repo,
        agent_profile_repo, bundle,
    ):
        agent_profile_repo.admin_get_by_id.return_value = make_profile(skill_ids=[1], tool_ids=[5])
        skill_repo.get_visible_many.return_value = [obj(1), obj(2)]
        tool_repo.get_visible_many.return_value = [obj(5), obj(6)]
        knowledge_pack_repo.get_active_many.return_value = [obj(9)]

        await service.add_to_bundle(1, 5, skill_ids=[1, 2], tool_ids=[5, 6], knowledge_pack_ids=[9])

        assert [c.args[1].id for c in config_bundle_repo.add_skill.await_args_list] == [2]
        assert [c.args[1].id for c in config_bundle_repo.add_tool.await_args_list] == [6]
        assert [c.args[1].id for c in config_bundle_repo.add_knowledge_pack.await_args_list] == [9]

    async def test_raises_when_profile_missing(self, service, agent_profile_repo, bundle):
        agent_profile_repo.admin_get_by_id.return_value = None

        with pytest.raises(NotFoundError, match="Agent profile not found"):
            await service.add_to_bundle(1, 5, skill_ids=[1])

    async def test_raises_when_item_unavailable(self, service, skill_repo, config_bundle_repo, bundle):
        skill_repo.get_visible_many.return_value = []

        with pytest.raises(NotFoundError, match=UNAVAILABLE):
            await service.add_to_bundle(1, 5, skill_ids=[1])

        config_bundle_repo.add_skill.assert_not_awaited()

    async def test_noop_without_ids(self, service, config_bundle_repo, bundle):
        await service.add_to_bundle(1, 5)

        config_bundle_repo.add_skill.assert_not_awaited()


class TestRemoveFromBundle:
    @pytest.fixture
    def bundle(self, config_bundle_repo, agent_profile_repo):
        b = SimpleNamespace(
            id=1, agent_id=2,
            skills=[obj(1), obj(2)], tools=[obj(10)], knowledge_packs=[obj(20)],
        )
        config_bundle_repo.get_owned.return_value = b
        agent_profile_repo.admin_get_by_id.return_value = make_profile(skill_ids=[3], tool_ids=[11])
        return b

    async def test_removes_own_items(self, service, config_bundle_repo, bundle):
        await service.remove_from_bundle(
            1, 5, skill_ids=[1, 1], tool_ids=[10], knowledge_pack_ids=[20]
        )

        config_bundle_repo.remove_skill.assert_awaited_once_with(bundle, bundle.skills[0])
        config_bundle_repo.remove_tool.assert_awaited_once_with(bundle, bundle.tools[0])
        config_bundle_repo.remove_knowledge_pack.assert_awaited_once_with(bundle, bundle.knowledge_packs[0])

    async def test_ignores_ids_not_in_bundle(self, service, config_bundle_repo, bundle):
        await service.remove_from_bundle(1, 5, skill_ids=[999], tool_ids=[999], knowledge_pack_ids=[999])

        config_bundle_repo.remove_skill.assert_not_awaited()
        config_bundle_repo.remove_tool.assert_not_awaited()
        config_bundle_repo.remove_knowledge_pack.assert_not_awaited()

    async def test_refuses_to_remove_inherited_skill(self, service, config_bundle_repo, bundle):
        with pytest.raises(ConflictError, match=INHERITED):
            await service.remove_from_bundle(1, 5, skill_ids=[3])

    async def test_refuses_to_remove_inherited_tool(self, service, bundle):
        with pytest.raises(ConflictError, match=INHERITED):
            await service.remove_from_bundle(1, 5, tool_ids=[11])

    async def test_nothing_removed_when_any_item_is_inherited(self, service, config_bundle_repo, bundle):
        with pytest.raises(ConflictError):
            await service.remove_from_bundle(1, 5, skill_ids=[1], tool_ids=[11])

        config_bundle_repo.remove_skill.assert_not_awaited()

    async def test_raises_when_profile_missing(self, service, agent_profile_repo, bundle):
        agent_profile_repo.admin_get_by_id.return_value = None

        with pytest.raises(NotFoundError, match="Agent profile not found"):
            await service.remove_from_bundle(1, 5, skill_ids=[1])