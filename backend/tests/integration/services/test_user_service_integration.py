import pytest

from src.services.user_service import UserService
from src.repositories.user_repo import UserRepository
from src.repositories.token_usage_event_repo import TokenUsageEventRepository

VALID_PASSWORD = "Str0ngPass!"


@pytest.fixture
def service(db_session):
    return UserService(
        UserRepository(db_session),
        TokenUsageEventRepository(db_session),
    )


class TestCreateUser:
    async def test_persists_user_with_hashed_password(self, service):
        user = await service.create_user(
            username="new-user", email="new-user@example.com", password=VALID_PASSWORD
        )

        assert user.id is not None
        assert user.password_hash != VALID_PASSWORD
        assert service._pwd_context.verify(VALID_PASSWORD, user.password_hash)

    async def test_raises_when_username_already_taken(self, service):
        await service.create_user(
            username="taken-user", email="first@example.com", password=VALID_PASSWORD
        )

        with pytest.raises(ValueError, match="Username 'taken-user' already exists"):
            await service.create_user(
                username="taken-user", email="second@example.com", password=VALID_PASSWORD
            )

    async def test_raises_when_email_already_registered(self, service):
        await service.create_user(
            username="first-user", email="taken@example.com", password=VALID_PASSWORD
        )

        with pytest.raises(ValueError, match="Email 'taken@example.com' already registered"):
            await service.create_user(
                username="second-user", email="taken@example.com", password=VALID_PASSWORD
            )

    @pytest.mark.parametrize(
        "password,expected_message",
        [
            ("Sh0rt!", "Password must be at least 8 characters long"),
            ("lowercase123", "Password must contain at least one uppercase letter"),
            ("UPPERCASE123", "Password must contain at least one lowercase letter"),
            ("NoDigitsHere", "Password must contain at least one digit"),
        ],
    )
    async def test_raises_for_weak_passwords(self, service, password, expected_message):
        with pytest.raises(ValueError, match=expected_message):
            await service.create_user(
                username="weak-pw-user", email="weak@example.com", password=password
            )

    async def test_does_not_create_user_when_password_is_weak(self, service):
        with pytest.raises(ValueError):
            await service.create_user(
                username="never-created", email="never-created@example.com", password="weak"
            )

        # the failed signup must not have left a row behind
        not_found = await service.user_repo.get_by_username("never-created")
        assert not_found is None


class TestAuthenticateUser:
    async def test_returns_user_for_correct_credentials(self, service):
        created = await service.create_user(
            username="auth-user", email="auth-user@example.com", password=VALID_PASSWORD
        )

        result = await service.authenticate_user(
            email="auth-user@example.com", password=VALID_PASSWORD
        )

        assert result is not None
        assert result.id == created.id

    async def test_returns_none_for_unknown_email(self, service):
        result = await service.authenticate_user(
            email="nobody@example.com", password=VALID_PASSWORD
        )
        assert result is None

    async def test_returns_none_for_wrong_password(self, service):
        await service.create_user(
            username="auth-user-2", email="auth-user-2@example.com", password=VALID_PASSWORD
        )

        result = await service.authenticate_user(
            email="auth-user-2@example.com", password="WrongPass1"
        )
        assert result is None


class TestGetUser:
    async def test_returns_persisted_user(self, service):
        created = await service.create_user(
            username="lookup-user", email="lookup-user@example.com", password=VALID_PASSWORD
        )

        result = await service.get_user(created.id)
        assert result.id == created.id

    async def test_raises_for_unknown_id(self, service):
        with pytest.raises(ValueError, match="User 999999 not found"):
            await service.get_user(999_999)


class TestUpdateUser:
    async def test_updates_username_and_email(self, service):
        created = await service.create_user(
            username="old-name", email="old@example.com", password=VALID_PASSWORD
        )

        updated = await service.update_user(
            created.id, username="new-name", email="new@example.com"
        )

        assert updated.username == "new-name"
        assert updated.email == "new@example.com"

    async def test_is_a_noop_when_values_are_unchanged(self, service):
        created = await service.create_user(
            username="same-name", email="same@example.com", password=VALID_PASSWORD
        )

        updated = await service.update_user(
            created.id, username="same-name", email="same@example.com"
        )

        assert updated.id == created.id
        assert updated.username == "same-name"

    async def test_raises_when_new_username_taken_by_another_user(self, service):
        await service.create_user(
            username="taken-name", email="taken-name@example.com", password=VALID_PASSWORD
        )
        target = await service.create_user(
            username="target-user", email="target@example.com", password=VALID_PASSWORD
        )

        with pytest.raises(ValueError, match="Username 'taken-name' already exists"):
            await service.update_user(target.id, username="taken-name")

    async def test_raises_when_new_email_taken_by_another_user(self, service):
        await service.create_user(
            username="other-user", email="taken-email@example.com", password=VALID_PASSWORD
        )
        target = await service.create_user(
            username="target-user-2", email="target2@example.com", password=VALID_PASSWORD
        )

        with pytest.raises(
            ValueError, match="Email 'taken-email@example.com' already registered"
        ):
            await service.update_user(target.id, email="taken-email@example.com")

    async def test_raises_for_unknown_user(self, service):
        with pytest.raises(ValueError, match="User 999999 not found"):
            await service.update_user(999_999, username="whoever")


class TestChangePassword:
    async def test_changes_password_when_old_password_is_correct(self, service):
        created = await service.create_user(
            username="pw-user", email="pw-user@example.com", password=VALID_PASSWORD
        )

        result = await service.change_password(created.id, VALID_PASSWORD, "NewStr0ngPass!")
        assert result is True

        authenticated = await service.authenticate_user(
            email="pw-user@example.com", password="NewStr0ngPass!"
        )
        assert authenticated is not None
        assert authenticated.id == created.id

        old_password_still_works = await service.authenticate_user(
            email="pw-user@example.com", password=VALID_PASSWORD
        )
        assert old_password_still_works is None

    async def test_raises_when_old_password_is_incorrect(self, service):
        created = await service.create_user(
            username="pw-user-2", email="pw-user-2@example.com", password=VALID_PASSWORD
        )

        with pytest.raises(ValueError, match="Incorrect current password"):
            await service.change_password(created.id, "WrongOld1", "NewStr0ngPass!")

    async def test_raises_when_new_password_is_weak(self, service):
        created = await service.create_user(
            username="pw-user-3", email="pw-user-3@example.com", password=VALID_PASSWORD
        )

        with pytest.raises(ValueError, match="Password must contain at least one digit"):
            await service.change_password(created.id, VALID_PASSWORD, "NoDigitsHere")

    async def test_raises_for_unknown_user(self, service):
        with pytest.raises(ValueError, match="User 999999 not found"):
            await service.change_password(999_999, VALID_PASSWORD, "NewStr0ngPass!")


class TestDeleteUser:
    async def test_deletes_an_existing_user(self, service):
        created = await service.create_user(
            username="del-user", email="del-user@example.com", password=VALID_PASSWORD
        )

        await service.delete_user(created.id)

        with pytest.raises(ValueError, match=f"User {created.id} not found"):
            await service.get_user(created.id)

    async def test_raises_for_unknown_user(self, service):
        with pytest.raises(ValueError, match="User 999999 not found"):
            await service.delete_user(999_999)