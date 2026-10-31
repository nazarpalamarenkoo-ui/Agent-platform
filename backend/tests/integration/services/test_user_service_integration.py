import pytest
import pytest_asyncio

from src.db.enums.user_role import UserRole
from src.repositories.token_usage_event_repo import TokenUsageEventRepository
from src.repositories.user_repo import UserRepository
from src.services.errors import ConflictError, ForbiddenError, NotFoundError
from src.services.user_service import UserService

VALID_PASSWORD = "Str0ngPass!"


@pytest.fixture
def service(db_session):
    return UserService(
        UserRepository(db_session),
        TokenUsageEventRepository(db_session),
    )


@pytest_asyncio.fixture
async def admin(make_user):
    return await make_user(role=UserRole.ADMIN)


@pytest_asyncio.fixture
async def super_admin(make_user):
    return await make_user(role=UserRole.SUPER_ADMIN)


class TestCreateUser:
    async def test_persists_user_with_hashed_password(self, service):
        user = await service.create_user("new-user", "new@example.com", VALID_PASSWORD)

        assert user.id is not None
        assert user.password_hash != VALID_PASSWORD
        assert service._pwd_context.verify(VALID_PASSWORD, user.password_hash)

    async def test_raises_when_username_taken(self, service):
        await service.create_user("taken", "a@example.com", VALID_PASSWORD)

        with pytest.raises(ValueError, match="Username 'taken' already exists"):
            await service.create_user("taken", "b@example.com", VALID_PASSWORD)

    async def test_raises_when_email_taken(self, service):
        await service.create_user("first", "same@example.com", VALID_PASSWORD)

        with pytest.raises(ValueError, match="Email 'same@example.com' already registered"):
            await service.create_user("second", "same@example.com", VALID_PASSWORD)

    @pytest.mark.parametrize(
        "password,message",
        [
            ("Sh0rt!", "at least 8 characters"),
            ("lowercase123", "uppercase letter"),
            ("UPPERCASE123", "lowercase letter"),
            ("NoDigitsHere", "at least one digit"),
        ],
    )
    async def test_rejects_weak_passwords_and_persists_nothing(
        self, service, password, message
    ):
        with pytest.raises(ValueError, match=message):
            await service.create_user("weak", "weak@example.com", password)

        assert await service.user_repo.get_by_username("weak") is None


class TestPrepareSignup:
    async def test_returns_hash_without_creating_user(self, service):
        password_hash = await service.prepare_signup("pre", "pre@example.com", VALID_PASSWORD)

        assert service._pwd_context.verify(VALID_PASSWORD, password_hash)
        assert await service.user_repo.get_by_username("pre") is None

    async def test_create_user_from_hash_persists_user(self, service):
        password_hash = await service.prepare_signup("fh", "fh@example.com", VALID_PASSWORD)

        user = await service.create_user_from_hash("fh", "fh@example.com", password_hash)

        assert user.password_hash == password_hash

    async def test_create_user_from_hash_rechecks_uniqueness(self, service):
        await service.create_user("race", "race@example.com", VALID_PASSWORD)

        with pytest.raises(ValueError, match="already exists"):
            await service.create_user_from_hash("race", "other@example.com", "hash")


class TestAuthenticateUser:
    async def test_returns_user_for_correct_credentials(self, service):
        created = await service.create_user("auth", "auth@example.com", VALID_PASSWORD)

        result = await service.authenticate_user("auth@example.com", VALID_PASSWORD)

        assert result.id == created.id

    async def test_returns_none_for_unknown_email(self, service):
        assert await service.authenticate_user("no@example.com", VALID_PASSWORD) is None

    async def test_returns_none_for_wrong_password(self, service):
        await service.create_user("auth2", "auth2@example.com", VALID_PASSWORD)

        assert await service.authenticate_user("auth2@example.com", "WrongPass1") is None


class TestGetUser:
    async def test_returns_persisted_user(self, service, sample_user):
        assert (await service.get_user(sample_user.id)).id == sample_user.id

    async def test_raises_for_unknown_id(self, service):
        with pytest.raises(ValueError, match="User 999999 not found"):
            await service.get_user(999_999)


class TestGetUserFor:
    async def test_user_can_get_self(self, service, sample_user):
        assert (await service.get_user_for(sample_user, sample_user.id)).id == sample_user.id

    async def test_regular_user_cannot_get_another_user(
        self, service, sample_user, another_user
    ):
        with pytest.raises(ForbiddenError, match="Forbidden"):
            await service.get_user_for(sample_user, another_user.id)

    async def test_admin_can_get_regular_user(self, service, admin, sample_user):
        assert (await service.get_user_for(admin, sample_user.id)).id == sample_user.id

    async def test_admin_cannot_get_another_admin(self, service, admin, make_user):
        other_admin = await make_user(role=UserRole.ADMIN)
        with pytest.raises(ForbiddenError, match="Only the super admin"):
            await service.get_user_for(admin, other_admin.id)

    async def test_super_admin_can_get_admin(self, service, super_admin, admin):
        assert (await service.get_user_for(super_admin, admin.id)).id == admin.id

    async def test_raises_for_unknown_user(self, service, admin):
        with pytest.raises(NotFoundError, match="User not found"):
            await service.get_user_for(admin, 999_999)


class TestUpdateUser:
    async def test_user_updates_own_username_and_email(self, service):
        user = await service.create_user("old", "old@example.com", VALID_PASSWORD)

        updated = await service.update_user(
            user, user.id, username="new", email="new@example.com"
        )

        assert updated.username == "new"
        assert updated.email == "new@example.com"

    async def test_noop_when_values_unchanged(self, service, sample_user):
        updated = await service.update_user(
            sample_user, sample_user.id, username=sample_user.username
        )
        assert updated.username == sample_user.username

    async def test_raises_when_username_taken(self, service, sample_user, another_user):
        with pytest.raises(ConflictError, match="Username 'anotheruser' already exists"):
            await service.update_user(sample_user, sample_user.id, username="anotheruser")

    async def test_raises_when_email_taken(self, service, sample_user, another_user):
        with pytest.raises(ConflictError, match="already registered"):
            await service.update_user(sample_user, sample_user.id, email=another_user.email)

    async def test_regular_user_cannot_update_someone_else(
        self, service, sample_user, another_user
    ):
        with pytest.raises(ForbiddenError):
            await service.update_user(sample_user, another_user.id, username="hacked")

    async def test_admin_can_update_regular_user(self, service, admin, sample_user):
        updated = await service.update_user(admin, sample_user.id, username="by-admin")
        assert updated.username == "by-admin"

    async def test_raises_for_unknown_user(self, service, admin):
        with pytest.raises(NotFoundError):
            await service.update_user(admin, 999_999, username="x")


class TestPasswordChange:
    async def test_change_password_replaces_credentials(self, service):
        user = await service.create_user("pw", "pw@example.com", VALID_PASSWORD)

        assert await service.change_password(user.id, VALID_PASSWORD, "NewStr0ngPass!") is True

        assert await service.authenticate_user("pw@example.com", "NewStr0ngPass!") is not None
        assert await service.authenticate_user("pw@example.com", VALID_PASSWORD) is None

    async def test_raises_when_old_password_wrong(self, service):
        user = await service.create_user("pw2", "pw2@example.com", VALID_PASSWORD)

        with pytest.raises(ValueError, match="Incorrect current password"):
            await service.change_password(user.id, "WrongOld1", "NewStr0ngPass!")

    async def test_raises_when_new_password_weak_and_keeps_old(self, service):
        user = await service.create_user("pw3", "pw3@example.com", VALID_PASSWORD)

        with pytest.raises(ValueError, match="at least one digit"):
            await service.change_password(user.id, VALID_PASSWORD, "NoDigitsHere")

        assert await service.authenticate_user("pw3@example.com", VALID_PASSWORD) is not None

    async def test_reset_password_does_not_need_old_password(self, service):
        user = await service.create_user("rp", "rp@example.com", VALID_PASSWORD)

        await service.reset_password(user.id, "Reset0Pass!")

        assert await service.authenticate_user("rp@example.com", "Reset0Pass!") is not None

    async def test_reset_password_validates_strength(self, service, sample_user):
        with pytest.raises(ValueError, match="uppercase"):
            await service.reset_password(sample_user.id, "lowercase1")

    async def test_unknown_user(self, service):
        with pytest.raises(ValueError, match="User 999999 not found"):
            await service.change_password(999_999, VALID_PASSWORD, "NewStr0ngPass!")


class TestDeleteUser:
    async def test_user_can_delete_self(self, service):
        user = await service.create_user("del", "del@example.com", VALID_PASSWORD)

        await service.delete_user(user, user.id)

        with pytest.raises(ValueError, match=f"User {user.id} not found"):
            await service.get_user(user.id)

    async def test_admin_deletes_regular_user(self, service, admin, sample_user):
        await service.delete_user(admin, sample_user.id)
        assert await service.user_repo.get_by_id(sample_user.id) is None

    async def test_super_admin_cannot_be_deleted_even_by_self(self, service, super_admin):
        with pytest.raises(ForbiddenError, match="super admin account cannot be deleted"):
            await service.delete_user(super_admin, super_admin.id)

    async def test_admin_cannot_delete_other_admin(self, service, admin, make_user):
        other = await make_user(role=UserRole.ADMIN)
        with pytest.raises(ForbiddenError):
            await service.delete_user(admin, other.id)

    async def test_regular_user_cannot_delete_another(
        self, service, sample_user, another_user
    ):
        with pytest.raises(ForbiddenError):
            await service.delete_user(sample_user, another_user.id)

    async def test_raises_for_unknown_user(self, service, admin):
        with pytest.raises(NotFoundError):
            await service.delete_user(admin, 999_999)


class TestListUsers:
    async def test_respects_limit_and_offset(self, service, sample_user, another_user):
        first = await service.list_users(limit=1, offset=0)
        second = await service.list_users(limit=1, offset=1)

        assert len(first) == len(second) == 1
        assert first[0].id != second[0].id


class TestTokens:
    async def test_report_usage_exceeding_limit(self, service, admin, sample_user):
        await service.set_token_limit(admin, sample_user.id, 10)

        await service.report_token_usage(sample_user, 100)

        assert await service.check_token_limit(sample_user) is True

    async def test_usage_within_limit(self, service, admin, sample_user):
        await service.set_token_limit(admin, sample_user.id, 1_000_000)

        await service.report_token_usage(sample_user, 1)

        assert await service.check_token_limit(sample_user) is False

    async def test_set_token_limit_requires_manage_rights(
        self, service, sample_user, another_user
    ):
        with pytest.raises(ForbiddenError):
            await service.set_token_limit(sample_user, another_user.id, 5)

    async def test_set_token_limit_persists(self, service, admin, sample_user):
        target = await service.set_token_limit(admin, sample_user.id, 777)
        assert target.token_limit == 777

    async def test_reset_usage_zeroes_counter(self, service, admin, sample_user):
        await service.report_token_usage(sample_user, 50)

        target = await service.reset_usage(admin, sample_user.id)

        assert target.tokens_used == 0

    async def test_reset_usage_forbidden_for_foreign_regular_user(
        self, service, sample_user, another_user
    ):
        with pytest.raises(ForbiddenError):
            await service.reset_usage(sample_user, another_user.id)


class TestEnsureSuperAdmin:
    async def test_creates_super_admin_when_none_exists(self, service):
        user = await service.ensure_super_admin("root", "root@example.com", VALID_PASSWORD)

        assert user.role == UserRole.SUPER_ADMIN
        assert service._pwd_context.verify(VALID_PASSWORD, user.password_hash)

    async def test_is_idempotent(self, service):
        first = await service.ensure_super_admin("root", "root@example.com", VALID_PASSWORD)
        second = await service.ensure_super_admin("other", "other@example.com", VALID_PASSWORD)

        assert second.id == first.id

    async def test_promotes_existing_user_by_email(self, service, sample_user):
        user = await service.ensure_super_admin("ignored", sample_user.email, VALID_PASSWORD)

        assert user.id == sample_user.id
        assert user.role == UserRole.SUPER_ADMIN

    async def test_raises_when_username_taken_by_other_email(self, service, sample_user):
        with pytest.raises(ValueError, match="already exists"):
            await service.ensure_super_admin(
                sample_user.username, "brand-new@example.com", VALID_PASSWORD
            )

    async def test_validates_password_for_new_account(self, service):
        with pytest.raises(ValueError, match="at least 8 characters"):
            await service.ensure_super_admin("root", "root@example.com", "weak")


class TestRoles:
    async def test_list_admins_returns_admins_and_super_admins_only(
        self, service, admin, super_admin, sample_user
    ):
        ids = {u.id for u in await service.list_admins()}

        assert {admin.id, super_admin.id} <= ids
        assert sample_user.id not in ids

    async def test_super_admin_promotes_user_to_admin(
        self, service, super_admin, sample_user
    ):
        target = await service.set_role(super_admin, sample_user.id, UserRole.ADMIN)
        assert target.role == UserRole.ADMIN

    async def test_super_admin_demotes_admin(self, service, super_admin, admin):
        target = await service.set_role(super_admin, admin.id, UserRole.USER)
        assert target.role == UserRole.USER

    async def test_only_super_admin_can_change_roles(self, service, admin, sample_user):
        with pytest.raises(ForbiddenError, match="Only the super admin"):
            await service.set_role(admin, sample_user.id, UserRole.ADMIN)

    async def test_cannot_assign_super_admin_role(self, service, super_admin, sample_user):
        with pytest.raises(ValueError, match="Only the 'user' and 'admin' roles"):
            await service.set_role(super_admin, sample_user.id, UserRole.SUPER_ADMIN)

    async def test_cannot_change_own_role(self, service, super_admin):
        with pytest.raises(ConflictError, match="own role"):
            await service.set_role(super_admin, super_admin.id, UserRole.USER)

    async def test_raises_for_unknown_target(self, service, super_admin):
        with pytest.raises(NotFoundError):
            await service.set_role(super_admin, 999_999, UserRole.ADMIN)