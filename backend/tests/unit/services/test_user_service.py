from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.user_service import UserService


@pytest.fixture
def user_repo():
    return AsyncMock()


@pytest.fixture
def token_repo():
    return AsyncMock()


@pytest.fixture
def service(user_repo, token_repo, monkeypatch):
    svc = UserService(user_repo, token_repo)
    monkeypatch.setattr(
        svc._pwd_context, "hash", lambda pw: f"hashed:{pw}"
    )
    monkeypatch.setattr(
        svc._pwd_context,
        "verify",
        lambda pw, hashed: hashed == f"hashed:{pw}",
    )
    return svc


VALID_PASSWORD = "Abcdefg1"


class TestCreateUser:
    async def test_creates_user_with_hashed_password(
        self, service, user_repo
    ):
        user_repo.get_by_username.return_value = None
        user_repo.get_by_email.return_value = None
        created = MagicMock()
        user_repo.create.return_value = created

        result = await service.create_user(
            username="alice", email="alice@example.com", password=VALID_PASSWORD
        )

        assert result is created
        user_repo.create.assert_awaited_once_with(
            username="alice",
            email="alice@example.com",
            password_hash=f"hashed:{VALID_PASSWORD}",
        )

    async def test_raises_when_username_taken(self, service, user_repo):
        user_repo.get_by_username.return_value = MagicMock()

        with pytest.raises(ValueError, match="Username 'alice' already exists"):
            await service.create_user(
                username="alice", email="alice@example.com", password=VALID_PASSWORD
            )

        user_repo.create.assert_not_awaited()

    async def test_raises_when_email_taken(self, service, user_repo):
        user_repo.get_by_username.return_value = None
        user_repo.get_by_email.return_value = MagicMock()

        with pytest.raises(
            ValueError, match="Email 'alice@example.com' already registered"
        ):
            await service.create_user(
                username="alice", email="alice@example.com", password=VALID_PASSWORD
            )

        user_repo.create.assert_not_awaited()

    async def test_raises_when_password_invalid(self, service, user_repo):
        user_repo.get_by_username.return_value = None
        user_repo.get_by_email.return_value = None

        with pytest.raises(ValueError, match="at least 8 characters"):
            await service.create_user(
                username="alice", email="alice@example.com", password="short1A"
            )

        user_repo.create.assert_not_awaited()


class TestAuthenticateUser:
    async def test_returns_user_on_correct_credentials(
        self, service, user_repo
    ):
        user = MagicMock(password_hash=f"hashed:{VALID_PASSWORD}")
        user_repo.get_by_email.return_value = user

        result = await service.authenticate_user(
            email="alice@example.com", password=VALID_PASSWORD
        )

        assert result is user

    async def test_returns_none_when_email_unknown(self, service, user_repo):
        user_repo.get_by_email.return_value = None

        result = await service.authenticate_user(
            email="ghost@example.com", password=VALID_PASSWORD
        )

        assert result is None

    async def test_returns_none_when_password_wrong(self, service, user_repo):
        user = MagicMock(password_hash=f"hashed:{VALID_PASSWORD}")
        user_repo.get_by_email.return_value = user

        result = await service.authenticate_user(
            email="alice@example.com", password="WrongPass1"
        )

        assert result is None


class TestCheckTokenLimit:
    async def test_delegates_to_token_repo(self, service, token_repo):
        user = MagicMock()
        token_repo.is_limit_exceeded.return_value = True

        result = await service.check_token_limit(user)

        assert result is True
        token_repo.is_limit_exceeded.assert_awaited_once_with(user)


class TestReportTokenUsage:
    async def test_reports_usage_with_agent_id(self, service, token_repo):
        user = MagicMock()

        await service.report_token_usage(user, tokens_used=100, agent_id=5)

        token_repo.report_usage.assert_awaited_once_with(
            user=user, tokens_used=100, agent_id=5
        )

    async def test_reports_usage_without_agent_id(self, service, token_repo):
        user = MagicMock()

        await service.report_token_usage(user, tokens_used=100)

        token_repo.report_usage.assert_awaited_once_with(
            user=user, tokens_used=100, agent_id=None
        )


class TestGetUser:
    async def test_returns_user_when_found(self, service, user_repo):
        user = MagicMock()
        user_repo.get_by_id.return_value = user

        result = await service.get_user(1)

        assert result is user

    async def test_raises_when_not_found(self, service, user_repo):
        user_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="User 1 not found"):
            await service.get_user(1)


class TestUpdateUser:
    async def test_updates_username_and_email_when_available(
        self, service, user_repo
    ):
        user = MagicMock(id=1, username="old", email="old@example.com")
        user_repo.get_by_id.return_value = user
        user_repo.get_by_username.return_value = None
        user_repo.get_by_email.return_value = None
        updated = MagicMock()
        user_repo.update.return_value = updated

        result = await service.update_user(
            user_id=1, username="new", email="new@example.com"
        )

        assert result is updated
        user_repo.update.assert_awaited_once_with(
            user, username="new", email="new@example.com"
        )

    async def test_no_op_when_values_unchanged(self, service, user_repo):
        user = MagicMock(id=1, username="same", email="same@example.com")
        user_repo.get_by_id.return_value = user

        result = await service.update_user(
            user_id=1, username="same", email="same@example.com"
        )

        assert result is user
        user_repo.update.assert_not_awaited()

    async def test_no_op_when_nothing_passed(self, service, user_repo):
        user = MagicMock(id=1, username="same", email="same@example.com")
        user_repo.get_by_id.return_value = user

        result = await service.update_user(user_id=1)

        assert result is user
        user_repo.update.assert_not_awaited()

    async def test_raises_when_new_username_taken_by_another_user(
        self, service, user_repo
    ):
        user = MagicMock(id=1, username="old", email="old@example.com")
        user_repo.get_by_id.return_value = user
        other_user = MagicMock(id=2)
        user_repo.get_by_username.return_value = other_user

        with pytest.raises(ValueError, match="Username 'new' already exists"):
            await service.update_user(user_id=1, username="new")

        user_repo.update.assert_not_awaited()

    async def test_allows_username_change_when_taken_by_self(
        self, service, user_repo
    ):
        # Defensive case: get_by_username happens to return the same user
        # (e.g. case-insensitive lookup); should not be treated as a conflict.
        user = MagicMock(id=1, username="old", email="old@example.com")
        user_repo.get_by_id.return_value = user
        user_repo.get_by_username.return_value = user
        updated = MagicMock()
        user_repo.update.return_value = updated

        result = await service.update_user(user_id=1, username="new")

        assert result is updated
        user_repo.update.assert_awaited_once_with(user, username="new")

    async def test_raises_when_new_email_taken_by_another_user(
        self, service, user_repo
    ):
        user = MagicMock(id=1, username="old", email="old@example.com")
        user_repo.get_by_id.return_value = user
        other_user = MagicMock(id=2)
        user_repo.get_by_email.return_value = other_user

        with pytest.raises(
            ValueError, match="Email 'new@example.com' already registered"
        ):
            await service.update_user(user_id=1, email="new@example.com")

        user_repo.update.assert_not_awaited()


class TestChangePassword:
    async def test_changes_password_on_correct_old_password(
        self, service, user_repo
    ):
        user = MagicMock(id=1, password_hash=f"hashed:{VALID_PASSWORD}")
        user_repo.get_by_id.return_value = user

        result = await service.change_password(
            user_id=1, old_password=VALID_PASSWORD, new_password="NewPass1"
        )

        assert result is True
        user_repo.update_password.assert_awaited_once_with(
            user, "hashed:NewPass1"
        )

    async def test_raises_when_old_password_wrong(self, service, user_repo):
        user = MagicMock(id=1, password_hash=f"hashed:{VALID_PASSWORD}")
        user_repo.get_by_id.return_value = user

        with pytest.raises(ValueError, match="Incorrect current password"):
            await service.change_password(
                user_id=1, old_password="WrongPass1", new_password="NewPass1"
            )

        user_repo.update_password.assert_not_awaited()

    async def test_raises_when_new_password_invalid(self, service, user_repo):
        user = MagicMock(id=1, password_hash=f"hashed:{VALID_PASSWORD}")
        user_repo.get_by_id.return_value = user

        with pytest.raises(ValueError, match="uppercase letter"):
            await service.change_password(
                user_id=1, old_password=VALID_PASSWORD, new_password="nopeupper1"
            )

        user_repo.update_password.assert_not_awaited()


class TestDeleteUser:
    async def test_deletes_existing_user(self, service, user_repo):
        user = MagicMock(id=1)
        user_repo.get_by_id.return_value = user
        user_repo.delete.return_value = True

        await service.delete_user(1)

        user_repo.delete.assert_awaited_once_with(user)

    async def test_raises_when_user_not_found(self, service, user_repo):
        user_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="User 1 not found"):
            await service.delete_user(1)

        user_repo.delete.assert_not_awaited()


class TestValidatePassword:
    def test_accepts_valid_password(self, service):
        service._validate_password(VALID_PASSWORD)  # should not raise

    def test_rejects_too_short(self, service):
        with pytest.raises(ValueError, match="at least 8 characters"):
            service._validate_password("Ab1defg")

    def test_rejects_missing_uppercase(self, service):
        with pytest.raises(ValueError, match="uppercase letter"):
            service._validate_password("abcdefg1")

    def test_rejects_missing_lowercase(self, service):
        with pytest.raises(ValueError, match="lowercase letter"):
            service._validate_password("ABCDEFG1")

    def test_rejects_missing_digit(self, service):
        with pytest.raises(ValueError, match="one digit"):
            service._validate_password("Abcdefgh")