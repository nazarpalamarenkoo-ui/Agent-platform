import pytest
from datetime import datetime, timedelta, timezone

from src.repositories.device_code_repo import DeviceCodeRepository
from src.db.models.device_code import DeviceCode
from src.db.enums.device_code_status import DeviceStatus

pytestmark = pytest.mark.db


@pytest.fixture
def device_repo(db_session):
    return DeviceCodeRepository(db_session)


class TestDeviceCodeRepository:

    async def test_get_by_code_found(self, device_repo, sample_device_code):
        found = await device_repo.get_by_code(sample_device_code.device_code)

        assert found is not None
        assert found.id == sample_device_code.id

    async def test_get_by_code_not_found(self, device_repo):
        found = await device_repo.get_by_code("XXXX-0000")

        assert found is None

    async def test_get_pending_for_user_returns_pending(
        self, device_repo, sample_device_code, sample_user
    ):
        results = await device_repo.get_pending_for_user(sample_user.id)

        ids = {d.id for d in results}
        assert sample_device_code.id in ids

    async def test_get_pending_for_user_excludes_approved(
        self, device_repo, approved_device_code, sample_user
    ):
        results = await device_repo.get_pending_for_user(sample_user.id)

        ids = {d.id for d in results}
        assert approved_device_code.id not in ids

    async def test_get_pending_for_user_empty_for_unknown(self, device_repo):
        results = await device_repo.get_pending_for_user(999999)

        assert results == []

    async def test_approve_sets_status(self, device_repo, sample_device_code):
        updated = await device_repo.approve(sample_device_code)

        assert updated.status == DeviceStatus.APPROVED

    async def test_reject_sets_status(self, device_repo, sample_device_code):
        updated = await device_repo.reject(sample_device_code)

        assert updated.status == DeviceStatus.REJECTED

    async def test_get_valid_by_code_returns_pending_unexpired(
        self, device_repo, sample_device_code
    ):
        found = await device_repo.get_valid_by_code(sample_device_code.device_code)

        assert found is not None
        assert found.id == sample_device_code.id

    async def test_get_valid_by_code_none_for_approved(
        self, device_repo, approved_device_code
    ):
        found = await device_repo.get_valid_by_code(approved_device_code.device_code)

        assert found is None

    async def test_get_valid_by_code_none_for_expired_time(
        self, device_repo, db_session, sample_user
    ):
        expired = DeviceCode(
            device_code="ZZZZ-9999",
            user_id=sample_user.id,
            status=DeviceStatus.PENDING,
            scope="read",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            interval=5,
        )
        db_session.add(expired)
        await db_session.flush()

        found = await device_repo.get_valid_by_code("ZZZZ-9999")

        assert found is None

    async def test_expire_stale_marks_expired(
        self, device_repo, db_session, sample_user
    ):
        stale = DeviceCode(
            device_code="STALE-001",
            user_id=sample_user.id,
            status=DeviceStatus.PENDING,
            scope="read",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            interval=5,
        )
        db_session.add(stale)
        await db_session.flush()

        await device_repo.expire_stale()

        refreshed = await device_repo.get_by_code("STALE-001")
        assert refreshed.status == DeviceStatus.EXPIRED

    async def test_expire_stale_leaves_valid_untouched(
        self, device_repo, sample_device_code
    ):
        await device_repo.expire_stale()

        refreshed = await device_repo.get_by_code(sample_device_code.device_code)
        assert refreshed.status == DeviceStatus.PENDING