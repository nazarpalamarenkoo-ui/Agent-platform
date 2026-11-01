import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from src.api.auth.admin import bootstrap

pytestmark = pytest.mark.unit

CONFIG = SimpleNamespace(
    SUPER_ADMIN_EMAIL="root@example.com",
    SUPER_ADMIN_USERNAME="root",
    SUPER_ADMIN_PASSWORD="Str0ngPassw0rd",
)


class FakeSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def session():
    return AsyncMock()


@pytest.fixture
def service(monkeypatch, session):
    svc = MagicMock()
    svc.user_repo.get_super_admin = AsyncMock(return_value=None)
    svc.ensure_super_admin = AsyncMock()
    monkeypatch.setattr(bootstrap, "AsyncSessionLocal", lambda: FakeSessionContext(session))
    monkeypatch.setattr(bootstrap, "UserService", lambda **kwargs: svc)
    monkeypatch.setattr(bootstrap, "UserRepository", lambda s: object())
    monkeypatch.setattr(bootstrap, "TokenUsageEventRepository", lambda s: object())
    monkeypatch.setattr(bootstrap, "settings", CONFIG)
    return svc


async def test_creates_super_admin_and_commits(service, session):
    await bootstrap.ensure_super_admin()

    service.ensure_super_admin.assert_awaited_once_with(
        "root", "root@example.com", "Str0ngPassw0rd"
    )
    session.commit.assert_awaited_once()


async def test_does_nothing_when_super_admin_already_exists(service, session):
    service.user_repo.get_super_admin.return_value = SimpleNamespace(id=1)

    await bootstrap.ensure_super_admin()

    service.ensure_super_admin.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "missing", ["SUPER_ADMIN_EMAIL", "SUPER_ADMIN_USERNAME", "SUPER_ADMIN_PASSWORD"]
)
async def test_warns_and_skips_when_not_configured(
    monkeypatch, service, session, caplog, missing
):
    values = {**vars(CONFIG), missing: None}
    monkeypatch.setattr(bootstrap, "settings", SimpleNamespace(**values))

    with caplog.at_level(logging.WARNING):
        await bootstrap.ensure_super_admin()

    assert "super_admin_missing_and_not_configured" in caplog.text
    service.ensure_super_admin.assert_not_awaited()
    session.commit.assert_not_awaited()


async def test_skips_when_settings_are_absent(monkeypatch, service):
    monkeypatch.setattr(bootstrap, "settings", SimpleNamespace())

    await bootstrap.ensure_super_admin()

    service.ensure_super_admin.assert_not_awaited()


async def test_concurrent_creation_is_rolled_back_without_error(service, session):
    service.ensure_super_admin.side_effect = IntegrityError("insert", {}, Exception("dup"))

    await bootstrap.ensure_super_admin()

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


async def test_other_errors_are_not_swallowed(service, session):
    service.ensure_super_admin.side_effect = ValueError("Password must be at least 8 characters long")

    with pytest.raises(ValueError):
        await bootstrap.ensure_super_admin()

    session.commit.assert_not_awaited()