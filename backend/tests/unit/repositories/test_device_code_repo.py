from datetime import datetime, timedelta, timezone

import pytest

from src.repositories.device_code_repo import DeviceCodeRepository

pytestmark = pytest.mark.db


def past(minutes=5):
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


def now():
    return datetime.now(timezone.utc)


@pytest.fixture
def device_repo(db_session):
    return DeviceCodeRepository(db_session)


class TestTokenLookups:

    async def test_get_by_token_hash_found_even_if_revoked_or_expired(
        self, device_repo, make_device_code
    ):
        revoked = await make_device_code(revoked_at=past())
        expired = await make_device_code(expires_at=past())

        assert (await device_repo.get_by_token_hash(revoked.token_hash)).id == revoked.id
        assert (await device_repo.get_by_token_hash(expired.token_hash)).id == expired.id

    async def test_get_by_token_hash_not_found(self, device_repo):
        assert await device_repo.get_by_token_hash("missing") is None

    async def test_get_active_returns_valid_device(self, device_repo, sample_device_code):
        found = await device_repo.get_active_by_token_hash(sample_device_code.token_hash)

        assert found is not None
        assert found.id == sample_device_code.id

    async def test_get_active_none_when_revoked(self, device_repo, make_device_code):
        device = await make_device_code(revoked_at=past())

        assert await device_repo.get_active_by_token_hash(device.token_hash) is None

    async def test_get_active_none_when_expired(self, device_repo, make_device_code):
        device = await make_device_code(expires_at=past(1))

        assert await device_repo.get_active_by_token_hash(device.token_hash) is None

    async def test_get_active_none_for_unknown_hash(self, device_repo):
        assert await device_repo.get_active_by_token_hash("missing") is None


class TestOwnership:

    async def test_get_owned_checks_owner(
        self, device_repo, sample_device_code, sample_user, another_user
    ):
        found = await device_repo.get_owned(sample_device_code.id, sample_user.id)

        assert found.id == sample_device_code.id
        assert await device_repo.get_owned(sample_device_code.id, another_user.id) is None
        assert await device_repo.get_owned(999999, sample_user.id) is None


class TestListForUser:

    async def test_returns_only_own_active_devices_newest_first(
        self, device_repo, make_device_code, sample_user, another_user
    ):
        first = await make_device_code()
        second = await make_device_code()
        await make_device_code(revoked_at=past())
        await make_device_code(expires_at=past())
        await make_device_code(user=another_user)

        result = await device_repo.list_for_user(sample_user.id)

        assert [d.id for d in result] == [second.id, first.id]

    async def test_active_only_false_includes_revoked_and_expired(
        self, device_repo, make_device_code, sample_user
    ):
        active = await make_device_code()
        revoked = await make_device_code(revoked_at=past())
        expired = await make_device_code(expires_at=past())

        result = await device_repo.list_for_user(sample_user.id, active_only=False)

        assert {d.id for d in result} == {active.id, revoked.id, expired.id}

    async def test_paginates(self, device_repo, make_device_code, sample_user):
        first = await make_device_code()
        second = await make_device_code()
        await make_device_code()

        page = await device_repo.list_for_user(sample_user.id, limit=2, offset=1)

        assert [d.id for d in page] == [second.id, first.id]

    async def test_empty_for_unknown_user(self, device_repo):
        assert await device_repo.list_for_user(999999) == []


class TestRevokeAndTouch:

    async def test_revoke_sets_timestamp_once(self, device_repo, sample_device_code):
        assert sample_device_code.revoked_at is None

        await device_repo.revoke(sample_device_code)
        first = sample_device_code.revoked_at
        await device_repo.revoke(sample_device_code)

        assert first is not None
        assert sample_device_code.revoked_at == first

    async def test_revoked_device_is_no_longer_active(
        self, device_repo, sample_device_code
    ):
        await device_repo.revoke(sample_device_code)

        assert (
            await device_repo.get_active_by_token_hash(sample_device_code.token_hash)
            is None
        )

    async def test_touch_updates_last_used_at(self, device_repo, sample_device_code):
        assert sample_device_code.last_used_at is None
        before = now()

        updated = await device_repo.touch(sample_device_code)

        assert updated is sample_device_code
        assert updated.last_used_at >= before

    async def test_touch_moves_timestamp_forward(self, device_repo, make_device_code):
        device = await make_device_code(last_used_at=past(60))
        old = device.last_used_at

        await device_repo.touch(device)

        assert device.last_used_at > old