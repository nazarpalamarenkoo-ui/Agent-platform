import pytest

from src.db.enums.notification_type import NotificationType
from src.repositories import notification_repo as notification_module
from src.repositories.notification_repo import NotificationRepository

pytestmark = pytest.mark.db


@pytest.fixture
def notif_repo(db_session):
    return NotificationRepository(db_session)


@pytest.fixture
def notif_type():
    return list(NotificationType)[0]


@pytest.fixture
def other_notif_type():
    types = list(NotificationType)
    if len(types) < 2:
        pytest.skip("NotificationType has only one member")
    return types[1]


class TestCreateMissing:

    async def test_requires_exactly_one_target(self, notif_repo, notif_type):
        with pytest.raises(ValueError):
            await notif_repo.create_missing([1], notif_type)
        with pytest.raises(ValueError):
            await notif_repo.create_missing([1], notif_type, skill_id=1, tool_id=1)

    async def test_empty_user_ids_returns_zero(self, notif_repo, notif_type, make_skill):
        skill = await make_skill()

        assert await notif_repo.create_missing([], notif_type, skill_id=skill.id) == 0

    async def test_creates_one_notification_per_user_for_skill(
        self, notif_repo, notif_type, make_user, make_skill
    ):
        users = [await make_user() for _ in range(2)]
        skill = await make_skill()

        created = await notif_repo.create_missing(
            [u.id for u in users], notif_type, skill_id=skill.id
        )

        assert created == 2
        for user in users:
            rows = await notif_repo.list_for_user(user.id)
            assert len(rows) == 1
            notification, skill_name, tool_name = rows[0]
            assert notification.skill_id == skill.id
            assert notification.tool_id is None
            assert skill_name == skill.skill_name
            assert tool_name is None

    async def test_creates_notification_for_tool(
        self, notif_repo, notif_type, make_user, make_tool
    ):
        user = await make_user()
        tool = await make_tool()

        await notif_repo.create_missing([user.id], notif_type, tool_id=tool.id)

        notification, skill_name, tool_name = (await notif_repo.list_for_user(user.id))[0]
        assert notification.tool_id == tool.id
        assert notification.skill_id is None
        assert skill_name is None
        assert tool_name == tool.tool_name

    async def test_duplicate_user_ids_are_collapsed(
        self, notif_repo, notif_type, make_user, make_skill
    ):
        user = await make_user()
        skill = await make_skill()

        created = await notif_repo.create_missing(
            [user.id, user.id, user.id], notif_type, skill_id=skill.id
        )

        assert created == 1

    async def test_is_idempotent_and_only_creates_missing(
        self, notif_repo, notif_type, make_user, make_skill
    ):
        existing = await make_user()
        fresh = await make_user()
        skill = await make_skill()
        await notif_repo.create_missing([existing.id], notif_type, skill_id=skill.id)

        created = await notif_repo.create_missing(
            [existing.id, fresh.id], notif_type, skill_id=skill.id
        )

        assert created == 1
        assert len(await notif_repo.list_for_user(existing.id)) == 1
        assert len(await notif_repo.list_for_user(fresh.id)) == 1

    async def test_other_skill_or_type_does_not_count_as_existing(
        self, notif_repo, notif_type, other_notif_type, make_user, make_skill
    ):
        user = await make_user()
        skill = await make_skill()
        other_skill = await make_skill()
        await notif_repo.create_missing([user.id], notif_type, skill_id=skill.id)

        assert await notif_repo.create_missing(
            [user.id], notif_type, skill_id=other_skill.id
        ) == 1
        assert await notif_repo.create_missing(
            [user.id], other_notif_type, skill_id=skill.id
        ) == 1

    async def test_dedup_works_across_chunks(
        self, monkeypatch, notif_repo, notif_type, make_user, make_skill
    ):
        monkeypatch.setattr(notification_module, "CHUNK_SIZE", 2)
        users = [await make_user() for _ in range(5)]
        skill = await make_skill()
        await notif_repo.create_missing(
            [u.id for u in users[:3]], notif_type, skill_id=skill.id
        )

        created = await notif_repo.create_missing(
            [u.id for u in users], notif_type, skill_id=skill.id
        )

        assert created == 2


class TestDeleteForItem:

    async def test_deletes_only_matching_skill_and_type(
        self, notif_repo, notif_type, other_notif_type, make_user, make_skill
    ):
        user = await make_user()
        skill = await make_skill()
        other_skill = await make_skill()
        await notif_repo.create_missing([user.id], notif_type, skill_id=skill.id)
        await notif_repo.create_missing([user.id], other_notif_type, skill_id=skill.id)
        await notif_repo.create_missing([user.id], notif_type, skill_id=other_skill.id)

        await notif_repo.delete_for_item(notif_type, skill_id=skill.id)

        remaining = {
            (n.type, n.skill_id) for n, _, _ in await notif_repo.list_for_user(user.id)
        }
        assert remaining == {
            (other_notif_type, skill.id),
            (notif_type, other_skill.id),
        }

    async def test_deletes_for_tool(
        self, notif_repo, notif_type, make_user, make_tool
    ):
        user = await make_user()
        tool = await make_tool()
        await notif_repo.create_missing([user.id], notif_type, tool_id=tool.id)

        await notif_repo.delete_for_item(notif_type, tool_id=tool.id)

        assert await notif_repo.list_for_user(user.id) == []

    async def test_requires_a_target(self, notif_repo, notif_type):
        with pytest.raises(ValueError):
            await notif_repo.delete_for_item(notif_type)


class TestListAndCount:

    async def test_list_for_user_is_scoped_newest_first_and_paginates(
        self, notif_repo, notif_type, make_user, make_skill
    ):
        user = await make_user()
        other = await make_user()
        skills = [await make_skill() for _ in range(3)]
        for skill in skills:
            await notif_repo.create_missing([user.id], notif_type, skill_id=skill.id)
        await notif_repo.create_missing([other.id], notif_type, skill_id=skills[0].id)

        rows = await notif_repo.list_for_user(user.id)
        page = await notif_repo.list_for_user(user.id, limit=1, offset=1)

        assert [n.skill_id for n, _, _ in rows] == [s.id for s in reversed(skills)]
        assert [n.skill_id for n, _, _ in page] == [skills[1].id]

    async def test_unread_only_filters_read_notifications(
        self, notif_repo, notif_type, make_user, make_skill
    ):
        user = await make_user()
        first, second = await make_skill(), await make_skill()
        await notif_repo.create_missing([user.id], notif_type, skill_id=first.id)
        await notif_repo.create_missing([user.id], notif_type, skill_id=second.id)
        read_one = [n for n, _, _ in await notif_repo.list_for_user(user.id)][0]
        await notif_repo.mark_read(read_one)

        unread = await notif_repo.list_for_user(user.id, unread_only=True)

        assert len(unread) == 1
        assert unread[0][0].id != read_one.id

    async def test_count_unread(self, notif_repo, notif_type, make_user, make_skill):
        user = await make_user()
        other = await make_user()
        assert await notif_repo.count_unread(user.id) == 0

        for _ in range(2):
            skill = await make_skill()
            await notif_repo.create_missing([user.id], notif_type, skill_id=skill.id)
        await notif_repo.create_missing([other.id], notif_type, skill_id=skill.id)
        assert await notif_repo.count_unread(user.id) == 2

        first = (await notif_repo.list_for_user(user.id))[0][0]
        await notif_repo.mark_read(first)
        assert await notif_repo.count_unread(user.id) == 1


class TestOwnershipAndRead:

    async def test_get_owned_checks_owner(
        self, notif_repo, notif_type, make_user, make_skill
    ):
        owner = await make_user()
        stranger = await make_user()
        skill = await make_skill()
        await notif_repo.create_missing([owner.id], notif_type, skill_id=skill.id)
        notification = (await notif_repo.list_for_user(owner.id))[0][0]

        assert (await notif_repo.get_owned(notification.id, owner.id)).id == notification.id
        assert await notif_repo.get_owned(notification.id, stranger.id) is None
        assert await notif_repo.get_owned(999999, owner.id) is None

    async def test_mark_read_sets_timestamp_once(
        self, notif_repo, notif_type, make_user, make_skill
    ):
        user = await make_user()
        skill = await make_skill()
        await notif_repo.create_missing([user.id], notif_type, skill_id=skill.id)
        notification = (await notif_repo.list_for_user(user.id))[0][0]
        assert notification.read_at is None

        await notif_repo.mark_read(notification)
        first = notification.read_at
        await notif_repo.mark_read(notification)

        assert first is not None
        assert notification.read_at == first

    async def test_mark_all_read_only_touches_unread_of_that_user(
        self, db_session, notif_repo, notif_type, make_user, make_skill
    ):
        user = await make_user()
        other = await make_user()
        skills = [await make_skill() for _ in range(3)]
        for skill in skills:
            await notif_repo.create_missing([user.id], notif_type, skill_id=skill.id)
        await notif_repo.create_missing([other.id], notif_type, skill_id=skills[0].id)
        already_read = (await notif_repo.list_for_user(user.id))[0][0]
        await notif_repo.mark_read(already_read)

        updated = await notif_repo.mark_all_read(user.id)

        assert updated == 2
        assert await notif_repo.count_unread(user.id) == 0
        assert await notif_repo.count_unread(other.id) == 1

    async def test_mark_all_read_returns_zero_when_nothing_unread(
        self, notif_repo, make_user
    ):
        user = await make_user()

        assert await notif_repo.mark_all_read(user.id) == 0