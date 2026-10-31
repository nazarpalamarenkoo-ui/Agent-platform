import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.db.enums.user_role import UserRole
from src.db.models.skill_access_logs import SkillAccessLog
from src.repositories.skill_access_log_repo import SkillAccessLogRepository

pytestmark = pytest.mark.integration

ACTION = "view"


@pytest.fixture
def log_repo(db_session):
    return SkillAccessLogRepository(db_session)


@pytest.fixture
async def admin(make_user):
    return await make_user(role=UserRole.ADMIN)


async def count_logs(session) -> int:
    result = await session.execute(select(func.count()).select_from(SkillAccessLog))
    return result.scalar_one()


class TestRecord:

    async def test_persists_every_field(
        self, log_repo, db_session, admin, sample_user, sample_skill
    ):
        entry = await log_repo.record(
            admin.id, sample_user.id, ACTION, skill_id=sample_skill.id, note="support ticket #1"
        )
        await db_session.commit()

        result = await db_session.execute(
            select(SkillAccessLog)
            .where(SkillAccessLog.id == entry.id)
            .execution_options(populate_existing=True)
        )
        row = result.scalar_one()
        assert row.admin_id == admin.id
        assert row.owner_id == sample_user.id
        assert row.skill_id == sample_skill.id
        assert row.action == ACTION
        assert row.note == "support ticket #1"
        assert row.created_at is not None

    async def test_skill_and_note_are_optional(self, log_repo, db_session, admin, sample_user):
        entry = await log_repo.record(admin.id, sample_user.id, ACTION)
        await db_session.commit()

        assert entry.id is not None
        assert entry.skill_id is None
        assert entry.note is None

    async def test_record_flushes_but_does_not_commit(
        self, log_repo, db_session, admin, sample_user
    ):
        await log_repo.record(admin.id, sample_user.id, ACTION)
        assert await count_logs(db_session) == 1

        await db_session.rollback()

        assert await count_logs(db_session) == 0

    async def test_unknown_admin_violates_foreign_key(self, log_repo, db_session, sample_user):
        with pytest.raises(IntegrityError):
            await log_repo.record(999_999, sample_user.id, ACTION)

        await db_session.rollback()

    async def test_unknown_owner_violates_foreign_key(self, log_repo, db_session, admin):
        with pytest.raises(IntegrityError):
            await log_repo.record(admin.id, 999_999, ACTION)

        await db_session.rollback()

    async def test_unknown_skill_violates_foreign_key(
        self, log_repo, db_session, admin, sample_user
    ):
        with pytest.raises(IntegrityError):
            await log_repo.record(admin.id, sample_user.id, ACTION, skill_id=999_999)

        await db_session.rollback()


class TestListForOwner:

    async def test_returns_only_that_owners_entries(
        self, log_repo, db_session, admin, sample_user, another_user
    ):
        mine = await log_repo.record(admin.id, sample_user.id, ACTION)
        await log_repo.record(admin.id, another_user.id, ACTION)
        await db_session.commit()

        result = await log_repo.list_for_owner(sample_user.id)

        assert [e.id for e in result] == [mine.id]

    async def test_orders_newest_first(self, log_repo, db_session, admin, sample_user):
        # created_at is identical inside one transaction, so id must break the tie.
        entries = [await log_repo.record(admin.id, sample_user.id, ACTION) for _ in range(3)]
        await db_session.commit()

        result = await log_repo.list_for_owner(sample_user.id)

        assert [e.id for e in result] == [e.id for e in reversed(entries)]

    async def test_limit_and_offset_paginate(self, log_repo, db_session, admin, sample_user):
        for _ in range(5):
            await log_repo.record(admin.id, sample_user.id, ACTION)
        await db_session.commit()

        everything = [e.id for e in await log_repo.list_for_owner(sample_user.id)]
        page = [e.id for e in await log_repo.list_for_owner(sample_user.id, limit=2, offset=2)]

        assert page == everything[2:4]

    async def test_returns_empty_list_when_no_entries(self, log_repo, sample_user):
        assert await log_repo.list_for_owner(sample_user.id) == []


class TestListAll:

    async def test_returns_entries_for_all_owners_newest_first(
        self, log_repo, db_session, admin, sample_user, another_user
    ):
        first = await log_repo.record(admin.id, sample_user.id, ACTION)
        second = await log_repo.record(admin.id, another_user.id, ACTION)
        third = await log_repo.record(admin.id, sample_user.id, ACTION)
        await db_session.commit()

        result = await log_repo.list_all()

        assert [e.id for e in result] == [third.id, second.id, first.id]

    async def test_limit_and_offset_paginate(
        self, log_repo, db_session, admin, sample_user, another_user
    ):
        for owner in (sample_user, another_user, sample_user, another_user):
            await log_repo.record(admin.id, owner.id, ACTION)
        await db_session.commit()

        everything = [e.id for e in await log_repo.list_all()]

        assert [e.id for e in await log_repo.list_all(limit=3)] == everything[:3]
        assert [e.id for e in await log_repo.list_all(limit=10, offset=3)] == everything[3:]