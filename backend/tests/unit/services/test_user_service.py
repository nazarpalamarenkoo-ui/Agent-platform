from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.enums.user_role import UserRole
from src.services.errors import ConflictError, ForbiddenError, NotFoundError
from src.services.user_service import UserService

VALID_PASSWORD = "Abcdefg1"


class FakeCrypt:
    def hash(self, password):
        return f"hashed:{password}"

    def verify(self, password, hashed):
        return hashed == f"hashed:{password}"


@pytest.fixture(autouse=True)
def fake_crypt(monkeypatch):
    monkeypatch.setattr(UserService, "_pwd_context", FakeCrypt())


def make_user(id=1, role=UserRole.USER, **kw):
    return SimpleNamespace(
        id=id,
        role=role,
        is_admin=role in (UserRole.ADMIN, UserRole.SUPER_ADMIN),
        is_super_admin=role == UserRole.SUPER_ADMIN,
        username=kw.pop("username", f"user{id}"),
        email=kw.pop("email", f"user{id}@example.com"),
        password_hash=kw.pop("password_hash", f"hashed:{VALID_PASSWORD}"),
        **kw,
    )


USER = make_user(1)
OTHER = make_user(2)
ADMIN = make_user(10, UserRole.ADMIN)
OTHER_ADMIN = make_user(11, UserRole.ADMIN)
SUPER = make_user(99, UserRole.SUPER_ADMIN)


@pytest.fixture
def user_repo():
    repo = AsyncMock()
    repo.get_by_username.return_value = None
    repo.get_by_email.return_value = None
    return repo


@pytest.fixture
def token_repo():
    return AsyncMock()


@pytest.fixture
def service(user_repo, token_repo):
    return UserService(user_repo, token_repo)


class TestPrepareSignup:
    async def test_returns_password_hash(self, service):
        assert await service.prepare_signup("alice", "a@x.com", VALID_PASSWORD) == f"hashed:{VALID_PASSWORD}"

    async def test_rejects_taken_username(self, service, user_repo):
        user_repo.get_by_username.return_value = OTHER

        with pytest.raises(ValueError, match="Username 'alice' already exists"):
            await service.prepare_signup("alice", "a@x.com", VALID_PASSWORD)

    async def test_rejects_taken_email(self, service, user_repo):
        user_repo.get_by_email.return_value = OTHER

        with pytest.raises(ValueError, match="Email 'a@x.com' already registered"):
            await service.prepare_signup("alice", "a@x.com", VALID_PASSWORD)

    async def test_rejects_weak_password(self, service):
        with pytest.raises(ValueError, match="at least 8 characters"):
            await service.prepare_signup("alice", "a@x.com", "short")


class TestCreateUser:
    async def test_creates_user_with_hashed_password(self, service, user_repo):
        created = MagicMock()
        user_repo.create.return_value = created

        result = await service.create_user("alice", "a@x.com", VALID_PASSWORD)

        assert result is created
        user_repo.create.assert_awaited_once_with(
            username="alice", email="a@x.com", password_hash=f"hashed:{VALID_PASSWORD}"
        )

    async def test_does_not_create_when_username_taken(self, service, user_repo):
        user_repo.get_by_username.return_value = OTHER

        with pytest.raises(ValueError):
            await service.create_user("alice", "a@x.com", VALID_PASSWORD)

        user_repo.create.assert_not_awaited()


class TestCreateUserFromHash:
    async def test_stores_given_hash_as_is(self, service, user_repo):
        await service.create_user_from_hash("alice", "a@x.com", "precomputed")

        user_repo.create.assert_awaited_once_with(
            username="alice", email="a@x.com", password_hash="precomputed"
        )

    async def test_rechecks_uniqueness(self, service, user_repo):
        user_repo.get_by_email.return_value = OTHER

        with pytest.raises(ValueError, match="already registered"):
            await service.create_user_from_hash("alice", "a@x.com", "h")

        user_repo.create.assert_not_awaited()


class TestAuthenticateUser:
    async def test_returns_user_on_correct_credentials(self, service, user_repo):
        user_repo.get_by_email.return_value = USER

        assert await service.authenticate_user("a@x.com", VALID_PASSWORD) is USER

    async def test_none_for_unknown_email(self, service, user_repo):
        assert await service.authenticate_user("ghost@x.com", VALID_PASSWORD) is None

    async def test_none_for_wrong_password(self, service, user_repo):
        user_repo.get_by_email.return_value = USER

        assert await service.authenticate_user("a@x.com", "WrongPass1") is None


class TestTokens:
    async def test_check_token_limit_delegates(self, service, token_repo):
        token_repo.is_limit_exceeded.return_value = True

        assert await service.check_token_limit(USER) is True
        token_repo.is_limit_exceeded.assert_awaited_once_with(USER)

    @pytest.mark.parametrize("agent_id", [5, None])
    async def test_report_usage(self, service, token_repo, agent_id):
        kwargs = {} if agent_id is None else {"agent_id": agent_id}

        await service.report_token_usage(USER, 100, **kwargs)

        token_repo.report_usage.assert_awaited_once_with(user=USER, tokens_used=100, agent_id=agent_id)


class TestGetUser:
    async def test_returns_user(self, service, user_repo):
        user_repo.get_by_id.return_value = USER

        assert await service.get_user(1) is USER

    async def test_raises_when_not_found(self, service, user_repo):
        user_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="User 1 not found"):
            await service.get_user(1)


class TestGetUserFor:
    @pytest.mark.parametrize(
        "actor, target",
        [(USER, USER), (ADMIN, USER), (SUPER, ADMIN), (SUPER, SUPER), (ADMIN, ADMIN)],
    )
    async def test_allowed(self, service, user_repo, actor, target):
        user_repo.get_by_id.return_value = target

        assert await service.get_user_for(actor, target.id) is target

    async def test_regular_user_cannot_read_others(self, service, user_repo):
        user_repo.get_by_id.return_value = OTHER

        with pytest.raises(ForbiddenError, match="Forbidden"):
            await service.get_user_for(USER, OTHER.id)

    async def test_admin_cannot_read_other_admin(self, service, user_repo):
        user_repo.get_by_id.return_value = OTHER_ADMIN

        with pytest.raises(ForbiddenError, match="super admin"):
            await service.get_user_for(ADMIN, OTHER_ADMIN.id)

    async def test_not_found(self, service, user_repo):
        user_repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError, match="User not found"):
            await service.get_user_for(ADMIN, 5)


class TestUpdateUser:
    @pytest.fixture
    def target(self, user_repo):
        t = make_user(1, username="old", email="old@x.com")
        user_repo.get_by_id.return_value = t
        return t

    async def test_updates_username_and_email(self, service, user_repo, target):
        updated = MagicMock()
        user_repo.update.return_value = updated

        result = await service.update_user(target, 1, username="new", email="new@x.com")

        assert result is updated
        user_repo.update.assert_awaited_once_with(target, username="new", email="new@x.com")

    async def test_noop_when_values_unchanged_or_missing(self, service, user_repo, target):
        assert await service.update_user(target, 1, username="old", email="old@x.com") is target
        assert await service.update_user(target, 1) is target

        user_repo.update.assert_not_awaited()

    async def test_username_taken_by_another_user(self, service, user_repo, target):
        user_repo.get_by_username.return_value = OTHER

        with pytest.raises(ConflictError, match="Username 'new' already exists"):
            await service.update_user(target, 1, username="new")

        user_repo.update.assert_not_awaited()

    async def test_email_taken_by_another_user(self, service, user_repo, target):
        user_repo.get_by_email.return_value = OTHER

        with pytest.raises(ConflictError, match="Email 'new@x.com' already registered"):
            await service.update_user(target, 1, email="new@x.com")

    async def test_same_user_returned_by_lookup_is_not_a_conflict(self, service, user_repo, target):
        user_repo.get_by_username.return_value = target

        await service.update_user(target, 1, username="new")

        user_repo.update.assert_awaited_once_with(target, username="new")

    async def test_other_regular_user_cannot_update(self, service, user_repo, target):
        with pytest.raises(ForbiddenError):
            await service.update_user(OTHER, 1, username="new")

        user_repo.update.assert_not_awaited()

    async def test_admin_can_update_regular_user(self, service, user_repo, target):
        await service.update_user(ADMIN, 1, username="new")

        user_repo.update.assert_awaited_once()

    async def test_not_found(self, service, user_repo):
        user_repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await service.update_user(ADMIN, 1, username="x")


class TestPasswords:
    async def test_change_password(self, service, user_repo):
        user_repo.get_by_id.return_value = USER

        assert await service.change_password(1, VALID_PASSWORD, "NewPass1") is True
        user_repo.update_password.assert_awaited_once_with(USER, "hashed:NewPass1")

    async def test_change_password_wrong_old(self, service, user_repo):
        user_repo.get_by_id.return_value = USER

        with pytest.raises(ValueError, match="Incorrect current password"):
            await service.change_password(1, "WrongPass1", "NewPass1")

        user_repo.update_password.assert_not_awaited()

    async def test_change_password_weak_new(self, service, user_repo):
        user_repo.get_by_id.return_value = USER

        with pytest.raises(ValueError, match="uppercase letter"):
            await service.change_password(1, VALID_PASSWORD, "nopeupper1")

        user_repo.update_password.assert_not_awaited()

    async def test_reset_password(self, service, user_repo):
        user_repo.get_by_id.return_value = USER

        await service.reset_password(1, "NewPass1")

        user_repo.update_password.assert_awaited_once_with(USER, "hashed:NewPass1")

    async def test_reset_password_weak(self, service, user_repo):
        user_repo.get_by_id.return_value = USER

        with pytest.raises(ValueError, match="at least 8"):
            await service.reset_password(1, "Ab1")

        user_repo.update_password.assert_not_awaited()

    async def test_reset_password_unknown_user(self, service, user_repo):
        user_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="User 1 not found"):
            await service.reset_password(1, "NewPass1")


class TestDeleteUser:
    async def test_user_can_delete_self(self, service, user_repo):
        user_repo.get_by_id.return_value = USER

        await service.delete_user(USER, 1)

        user_repo.delete.assert_awaited_once_with(USER)

    async def test_admin_can_delete_regular_user(self, service, user_repo):
        user_repo.get_by_id.return_value = OTHER

        await service.delete_user(ADMIN, 2)

        user_repo.delete.assert_awaited_once_with(OTHER)

    async def test_super_admin_can_delete_admin(self, service, user_repo):
        user_repo.get_by_id.return_value = ADMIN

        await service.delete_user(SUPER, 10)

        user_repo.delete.assert_awaited_once_with(ADMIN)

    async def test_admin_cannot_delete_admin(self, service, user_repo):
        user_repo.get_by_id.return_value = OTHER_ADMIN

        with pytest.raises(ForbiddenError):
            await service.delete_user(ADMIN, 11)

        user_repo.delete.assert_not_awaited()

    async def test_regular_user_cannot_delete_others(self, service, user_repo):
        user_repo.get_by_id.return_value = OTHER

        with pytest.raises(ForbiddenError):
            await service.delete_user(USER, 2)

    async def test_super_admin_cannot_be_deleted_even_by_self(self, service, user_repo):
        user_repo.get_by_id.return_value = SUPER

        with pytest.raises(ForbiddenError, match="cannot be deleted"):
            await service.delete_user(SUPER, 99)

        user_repo.delete.assert_not_awaited()

    async def test_not_found(self, service, user_repo):
        user_repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await service.delete_user(ADMIN, 1)


class TestListUsers:
    async def test_list_users_pagination(self, service, user_repo):
        await service.list_users(limit=10, offset=20)

        user_repo.list_page.assert_awaited_once_with(limit=10, offset=20)

    async def test_list_admins_queries_both_admin_roles(self, service, user_repo):
        await service.list_admins()

        user_repo.list_by_roles.assert_awaited_once_with([UserRole.ADMIN, UserRole.SUPER_ADMIN])


class TestTokenLimitAndUsage:
    async def test_set_token_limit(self, service, user_repo):
        user_repo.get_by_id.return_value = OTHER

        result = await service.set_token_limit(ADMIN, 2, 5000)

        assert result is OTHER
        user_repo.set_token_limit.assert_awaited_once_with(OTHER, 5000)

    async def test_set_token_limit_forbidden_for_regular_user(self, service, user_repo):
        user_repo.get_by_id.return_value = OTHER

        with pytest.raises(ForbiddenError):
            await service.set_token_limit(USER, 2, 5000)

        user_repo.set_token_limit.assert_not_awaited()

    async def test_admin_cannot_change_limit_of_admin(self, service, user_repo):
        user_repo.get_by_id.return_value = OTHER_ADMIN

        with pytest.raises(ForbiddenError):
            await service.set_token_limit(ADMIN, 11, 1)

    async def test_reset_usage(self, service, user_repo):
        user_repo.get_by_id.return_value = OTHER

        assert await service.reset_usage(ADMIN, 2) is OTHER
        user_repo.reset_usage.assert_awaited_once_with(OTHER)

    async def test_reset_usage_forbidden(self, service, user_repo):
        user_repo.get_by_id.return_value = OTHER

        with pytest.raises(ForbiddenError):
            await service.reset_usage(USER, 2)


class TestEnsureSuperAdmin:
    async def test_returns_existing_super_admin(self, service, user_repo):
        user_repo.get_super_admin.return_value = SUPER

        assert await service.ensure_super_admin("root", "r@x.com", VALID_PASSWORD) is SUPER
        user_repo.create.assert_not_awaited()
        user_repo.set_role.assert_not_awaited()

    async def test_promotes_existing_user_by_email(self, service, user_repo):
        user_repo.get_super_admin.return_value = None
        user_repo.get_by_email.return_value = OTHER

        assert await service.ensure_super_admin("root", "r@x.com", VALID_PASSWORD) is OTHER
        user_repo.set_role.assert_awaited_once_with(OTHER, UserRole.SUPER_ADMIN)

    async def test_rejects_taken_username(self, service, user_repo):
        user_repo.get_super_admin.return_value = None
        user_repo.get_by_username.return_value = OTHER

        with pytest.raises(ValueError, match="Username 'root' already exists"):
            await service.ensure_super_admin("root", "r@x.com", VALID_PASSWORD)

    async def test_validates_password_before_creating(self, service, user_repo):
        user_repo.get_super_admin.return_value = None

        with pytest.raises(ValueError, match="at least 8"):
            await service.ensure_super_admin("root", "r@x.com", "weak")

        user_repo.create.assert_not_awaited()

    async def test_creates_super_admin(self, service, user_repo):
        user_repo.get_super_admin.return_value = None
        created = MagicMock()
        user_repo.create.return_value = created

        assert await service.ensure_super_admin("root", "r@x.com", VALID_PASSWORD) is created
        user_repo.create.assert_awaited_once_with(
            username="root", email="r@x.com",
            password_hash=f"hashed:{VALID_PASSWORD}", role=UserRole.SUPER_ADMIN,
        )


class TestSetRole:
    async def test_only_super_admin_can_change_roles(self, service, user_repo):
        with pytest.raises(ForbiddenError, match="Only the super admin"):
            await service.set_role(ADMIN, 2, UserRole.ADMIN)

        user_repo.get_by_id.assert_not_awaited()

    async def test_cannot_assign_super_admin_role(self, service):
        with pytest.raises(ValueError, match="'user' and 'admin'"):
            await service.set_role(SUPER, 2, UserRole.SUPER_ADMIN)

    async def test_target_not_found(self, service, user_repo):
        user_repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await service.set_role(SUPER, 2, UserRole.ADMIN)

    async def test_cannot_change_own_role(self, service, user_repo):
        user_repo.get_by_id.return_value = SUPER

        with pytest.raises(ConflictError, match="own role"):
            await service.set_role(SUPER, 99, UserRole.USER)

    async def test_cannot_change_role_of_another_super_admin(self, service, user_repo):
        user_repo.get_by_id.return_value = make_user(98, UserRole.SUPER_ADMIN)

        with pytest.raises(ForbiddenError, match="cannot be changed"):
            await service.set_role(SUPER, 98, UserRole.USER)

    async def test_promotes_user_to_admin(self, service, user_repo):
        user_repo.get_by_id.return_value = OTHER

        assert await service.set_role(SUPER, 2, UserRole.ADMIN) is OTHER
        user_repo.set_role.assert_awaited_once_with(OTHER, UserRole.ADMIN)

    async def test_same_role_is_noop(self, service, user_repo):
        user_repo.get_by_id.return_value = OTHER

        await service.set_role(SUPER, 2, UserRole.USER)

        user_repo.set_role.assert_not_awaited()


class TestValidatePassword:
    def test_accepts_valid_password(self, service):
        service._validate_password(VALID_PASSWORD)

    @pytest.mark.parametrize(
        "password, message",
        [
            ("Ab1defg", "at least 8 characters"),
            ("abcdefg1", "uppercase letter"),
            ("ABCDEFG1", "lowercase letter"),
            ("Abcdefgh", "one digit"),
        ],
    )
    def test_rejects_invalid(self, service, password, message):
        with pytest.raises(ValueError, match=message):
            service._validate_password(password)