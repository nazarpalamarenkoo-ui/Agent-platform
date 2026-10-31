import pytest

from src.repositories.skill_access_log_repo import SkillAccessLogRepository

pytestmark = pytest.mark.db

ACTION = "view_content"


@pytest.fixture
def log_repo(db_session):
    return SkillAccessLogRepository(db_session)


class TestRecord:

    async def test_record_persists_and_flushes_entry(
        self, log_repo, make_user, make_skill
    ):
        admin = await make_user()
        owner = await make_user()
        skill = await make_skill(owner=owner)

        entry = await log_repo.record(
            admin.id, owner.id, ACTION, skill_id=skill.id, note="support ticket"
        )

        assert entry.id is not None
        assert entry.admin_id == admin.id
        assert entry.owner_id == owner.id
        assert entry.skill_id == skill.id
        assert entry.action == ACTION
        assert entry.note == "support ticket"
        assert entry.created_at is not None

    async def test_skill_and_note_are_optional(self, log_repo, make_user):
        admin = await make_user()
        owner = await make_user()

        entry = await log_repo.record(admin.id, owner.id, ACTION)

        assert entry.skill_id is None
        assert entry.note is None


class TestListing:

    async def test_list_for_owner_is_scoped_newest_first_and_paginates(
        self, log_repo, make_user
    ):
        admin = await make_user()
        owner = await make_user()
        other_owner = await make_user()
        first = await log_repo.record(admin.id, owner.id, ACTION)
        second = await log_repo.record(admin.id, owner.id, ACTION)
        third = await log_repo.record(admin.id, owner.id, ACTION)
        await log_repo.record(admin.id, other_owner.id, ACTION)

        result = await log_repo.list_for_owner(owner.id)
        page = await log_repo.list_for_owner(owner.id, limit=1, offset=1)

        assert [e.id for e in result] == [third.id, second.id, first.id]
        assert [e.id for e in page] == [second.id]

    async def test_list_for_owner_is_empty_for_unknown_owner(self, log_repo):
        assert await log_repo.list_for_owner(999999) == []

    async def test_list_all_returns_every_owner_newest_first_and_paginates(
        self, log_repo, make_user
    ):
        admin = await make_user()
        owner_a = await make_user()
        owner_b = await make_user()
        first = await log_repo.record(admin.id, owner_a.id, ACTION)
        second = await log_repo.record(admin.id, owner_b.id, ACTION)
        third = await log_repo.record(admin.id, owner_a.id, ACTION)

        result = await log_repo.list_all()
        page = await log_repo.list_all(limit=2, offset=1)

        assert [e.id for e in result] == [third.id, second.id, first.id]
        assert [e.id for e in page] == [second.id, first.id]