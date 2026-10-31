import pytest

from src.db.enums.user_role import UserRole
from src.repositories.user_repo import UserRepository

pytestmark = pytest.mark.db


def non_super_roles():
    return [r for r in UserRole if r != UserRole.SUPER_ADMIN]


@pytest.fixture
def user_repo(db_session):
    return UserRepository(db_session)


class TestLookups:

    async def test_get_by_username_found(self, user_repo, sample_user):
        found = await user_repo.get_by_username(sample_user.username)

        assert found is not None
        assert found.id == sample_user.id

    async def test_get_by_username_not_found(self, user_repo):
        assert await user_repo.get_by_username("nonexistent") is None

    async def test_get_by_email_found(self, user_repo, sample_user):
        found = await user_repo.get_by_email(sample_user.email)

        assert found is not None
        assert found.id == sample_user.id

    async def test_get_by_email_not_found(self, user_repo):
        assert await user_repo.get_by_email("nobody@example.com") is None

    async def test_exists_by_email(self, user_repo, sample_user):
        assert await user_repo.exists_by_email(sample_user.email) is True
        assert await user_repo.exists_by_email("nobody@example.com") is False

    async def test_list_page_orders_by_id_and_paginates(self, user_repo, make_user):
        users = [await make_user() for _ in range(3)]

        everything = await user_repo.list_page()
        page = await user_repo.list_page(limit=1, offset=1)

        assert [u.id for u in everything] == sorted(u.id for u in users)
        assert [u.id for u in page] == [users[1].id]


class TestUpdates:

    async def test_update_password_changes_hash(self, user_repo, sample_user):
        updated = await user_repo.update_password(sample_user, "new-hash")

        assert updated is sample_user
        assert updated.password_hash == "new-hash"

    async def test_reset_usage_zeroes_tokens(self, user_repo, sample_user):
        sample_user.tokens_used = 500
        await user_repo.session.flush()

        updated = await user_repo.reset_usage(sample_user)

        assert updated.tokens_used == 0

    async def test_set_token_limit(self, user_repo, sample_user):
        updated = await user_repo.set_token_limit(sample_user, 12345)

        assert updated.token_limit == 12345

    async def test_set_role(self, user_repo, sample_user):
        target = non_super_roles()[0]

        updated = await user_repo.set_role(sample_user, target)

        assert updated.role == target


class TestRoles:

    async def test_get_super_admin_found(self, user_repo, make_user):
        await make_user()
        admin = await make_user(role=UserRole.SUPER_ADMIN)

        assert (await user_repo.get_super_admin()).id == admin.id

    async def test_get_super_admin_none_when_missing(self, user_repo, make_user):
        await make_user()

        assert await user_repo.get_super_admin() is None

    async def test_list_by_roles_filters_and_orders_by_id(self, user_repo, make_user):
        role = non_super_roles()[0]
        first = await make_user(role=role)
        await make_user(role=UserRole.SUPER_ADMIN)
        second = await make_user(role=role)

        result = await user_repo.list_by_roles([role])

        assert [u.id for u in result] == [first.id, second.id]

    async def test_list_by_roles_accepts_several_roles(self, user_repo, make_user):
        role = non_super_roles()[0]
        regular = await make_user(role=role)
        admin = await make_user(role=UserRole.SUPER_ADMIN)

        result = await user_repo.list_by_roles([role, UserRole.SUPER_ADMIN])

        assert {u.id for u in result} == {regular.id, admin.id}

    async def test_list_by_roles_empty_input_returns_empty(self, user_repo, make_user):
        await make_user()

        assert await user_repo.list_by_roles([]) == []