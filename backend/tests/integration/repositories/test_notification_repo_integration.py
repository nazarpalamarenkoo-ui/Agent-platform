import importlib

import pytest
from sqlalchemy import func, select

from src.db.enums.notification_type import NotificationType
from src.db.models.notification import Notification
from src.repositories.notification_repo import NotificationRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def notif_repo(db_session):
    return NotificationRepository(db_session)


async def count_notifications(session, *conditions) -> int:
    result = await session.execute(
        select(func.count()).select_from(Notification).where(*conditions)
    )
    return result.scalar_one()


async def fresh_notification(session, notification_id) -> Notification | None:
    result = await session.execute(
        select(Notification)
        .where(Notification.id == notification_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


class TestCreateMissing:

    async def test_creates_notification_for_every_user(
        self, notif_repo, db_session, make_user, sample_skill
    ):
        users = [await make_user(), await make_user(), await make_user()]

        created = await notif_repo.create_missing(
            [u.id for u in users], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id
        )
        await db_session.commit()

        assert created == 3
        assert await count_notifications(
            db_session, Notification.skill_id == sample_skill.id
        ) == 3

    async def test_persists_fields_for_skill_notification(
        self, notif_repo, db_session, sample_user, sample_skill
    ):
        await notif_repo.create_missing(
            [sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id
        )
        await db_session.commit()

        row = (await db_session.execute(select(Notification))).scalar_one()

        assert row.user_id == sample_user.id
        assert row.type == NotificationType.SKILL_ARCHIVED
        assert row.skill_id == sample_skill.id
        assert row.tool_id is None
        assert row.read_at is None
        assert row.created_at is not None

    async def test_persists_fields_for_tool_notification(
        self, notif_repo, db_session, sample_user, sample_tool
    ):
        await notif_repo.create_missing(
            [sample_user.id], NotificationType.TOOL_ARCHIVED, tool_id=sample_tool.id
        )
        await db_session.commit()

        row = (await db_session.execute(select(Notification))).scalar_one()

        assert row.type == NotificationType.TOOL_ARCHIVED
        assert row.tool_id == sample_tool.id
        assert row.skill_id is None

    async def test_second_call_does_not_duplicate_existing(
        self, notif_repo, db_session, sample_user, another_user, sample_skill
    ):
        first = await notif_repo.create_missing(
            [sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id
        )
        await db_session.commit()

        second = await notif_repo.create_missing(
            [sample_user.id, another_user.id],
            NotificationType.SKILL_ARCHIVED,
            skill_id=sample_skill.id,
        )
        await db_session.commit()

        assert (first, second) == (1, 1)
        assert await count_notifications(
            db_session, Notification.skill_id == sample_skill.id
        ) == 2

    async def test_repeating_the_same_call_creates_nothing(
        self, notif_repo, db_session, sample_user, sample_skill
    ):
        args = ([sample_user.id], NotificationType.SKILL_ARCHIVED)
        await notif_repo.create_missing(*args, skill_id=sample_skill.id)
        await db_session.commit()

        assert await notif_repo.create_missing(*args, skill_id=sample_skill.id) == 0

    async def test_duplicate_user_ids_in_input_are_collapsed(
        self, notif_repo, db_session, sample_user, sample_skill
    ):
        created = await notif_repo.create_missing(
            [sample_user.id, sample_user.id, sample_user.id],
            NotificationType.SKILL_ARCHIVED,
            skill_id=sample_skill.id,
        )
        await db_session.commit()

        assert created == 1
        assert await count_notifications(db_session) == 1

    async def test_empty_user_list_creates_nothing(self, notif_repo, db_session, sample_skill):
        created = await notif_repo.create_missing(
            [], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id
        )

        assert created == 0
        assert await count_notifications(db_session) == 0

    async def test_existing_check_is_scoped_to_the_item(
        self, notif_repo, db_session, sample_user, sample_skill, another_skill
    ):
        await notif_repo.create_missing(
            [sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id
        )
        await db_session.commit()

        created = await notif_repo.create_missing(
            [sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=another_skill.id
        )

        assert created == 1

    async def test_skill_and_tool_notifications_do_not_shadow_each_other(
        self, notif_repo, db_session, sample_user, sample_skill, sample_tool
    ):
        await notif_repo.create_missing(
            [sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id
        )
        created = await notif_repo.create_missing(
            [sample_user.id], NotificationType.TOOL_ARCHIVED, tool_id=sample_tool.id
        )

        assert created == 1

    async def test_works_across_chunk_boundaries(
        self, notif_repo, db_session, monkeypatch, make_user, sample_skill
    ):
        monkeypatch.setattr(
            importlib.import_module(NotificationRepository.__module__), "CHUNK_SIZE", 2
        )
        users = [await make_user() for _ in range(5)]
        await notif_repo.create_missing(
            [u.id for u in users[:3]], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id
        )
        await db_session.commit()

        created = await notif_repo.create_missing(
            [u.id for u in users], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id
        )
        await db_session.commit()

        assert created == 2
        assert await count_notifications(
            db_session, Notification.skill_id == sample_skill.id
        ) == 5

    async def test_requires_exactly_one_target(
        self, notif_repo, sample_user, sample_skill, sample_tool
    ):
        with pytest.raises(ValueError):
            await notif_repo.create_missing([sample_user.id], NotificationType.SKILL_ARCHIVED)

        with pytest.raises(ValueError):
            await notif_repo.create_missing(
                [sample_user.id],
                NotificationType.SKILL_ARCHIVED,
                skill_id=sample_skill.id,
                tool_id=sample_tool.id,
            )


class TestDeleteForItem:

    async def test_deletes_only_notifications_of_that_skill(
        self, notif_repo, db_session, sample_user, another_user, sample_skill, another_skill
    ):
        users = [sample_user.id, another_user.id]
        await notif_repo.create_missing(users, NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id)
        await notif_repo.create_missing(users, NotificationType.SKILL_ARCHIVED, skill_id=another_skill.id)
        await db_session.commit()

        await notif_repo.delete_for_item(NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id)
        await db_session.commit()

        assert await count_notifications(db_session, Notification.skill_id == sample_skill.id) == 0
        assert await count_notifications(db_session, Notification.skill_id == another_skill.id) == 2

    async def test_deletes_only_notifications_of_that_tool(
        self, notif_repo, db_session, sample_user, sample_skill, sample_tool, another_tool
    ):
        await notif_repo.create_missing([sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id)
        await notif_repo.create_missing([sample_user.id], NotificationType.TOOL_ARCHIVED, tool_id=sample_tool.id)
        await notif_repo.create_missing([sample_user.id], NotificationType.TOOL_ARCHIVED, tool_id=another_tool.id)
        await db_session.commit()

        await notif_repo.delete_for_item(NotificationType.TOOL_ARCHIVED, tool_id=sample_tool.id)
        await db_session.commit()

        assert await count_notifications(db_session, Notification.tool_id == sample_tool.id) == 0
        assert await count_notifications(db_session, Notification.tool_id == another_tool.id) == 1
        assert await count_notifications(db_session, Notification.skill_id == sample_skill.id) == 1

    async def test_deleted_item_can_be_notified_again(
        self, notif_repo, db_session, sample_user, sample_skill
    ):
        await notif_repo.create_missing([sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id)
        await db_session.commit()
        await notif_repo.delete_for_item(NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id)
        await db_session.commit()

        created = await notif_repo.create_missing(
            [sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id
        )

        assert created == 1

    async def test_requires_a_target(self, notif_repo):
        with pytest.raises(ValueError):
            await notif_repo.delete_for_item(NotificationType.SKILL_ARCHIVED)


class TestListForUser:

    async def test_returns_skill_and_tool_names_via_outer_join(
        self, notif_repo, db_session, sample_user, sample_skill, sample_tool
    ):
        await notif_repo.create_missing([sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id)
        await notif_repo.create_missing([sample_user.id], NotificationType.TOOL_ARCHIVED, tool_id=sample_tool.id)
        await db_session.commit()

        rows = await notif_repo.list_for_user(sample_user.id)

        by_type = {n.type: (skill_name, tool_name) for n, skill_name, tool_name in rows}
        assert by_type[NotificationType.SKILL_ARCHIVED] == (sample_skill.skill_name, None)
        assert by_type[NotificationType.TOOL_ARCHIVED] == (None, sample_tool.tool_name)

    async def test_is_scoped_to_user(
        self, notif_repo, db_session, sample_user, another_user, sample_skill
    ):
        await notif_repo.create_missing([another_user.id], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id)
        await db_session.commit()

        assert await notif_repo.list_for_user(sample_user.id) == []

    async def test_orders_newest_first_with_id_as_tiebreaker(
        self, notif_repo, db_session, sample_user, make_skill
    ):
        skills = [await make_skill() for _ in range(3)]
        for skill in skills:
            await notif_repo.create_missing(
                [sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=skill.id
            )
        await db_session.commit()

        rows = await notif_repo.list_for_user(sample_user.id)

        assert [n.skill_id for n, _, _ in rows] == [s.id for s in reversed(skills)]

    async def test_limit_and_offset_paginate(
        self, notif_repo, db_session, sample_user, make_skill
    ):
        for _ in range(5):
            skill = await make_skill()
            await notif_repo.create_missing(
                [sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=skill.id
            )
        await db_session.commit()

        everything = [n.id for n, _, _ in await notif_repo.list_for_user(sample_user.id)]
        page = [n.id for n, _, _ in await notif_repo.list_for_user(sample_user.id, limit=2, offset=1)]

        assert page == everything[1:3]

    async def test_unread_only_hides_read_notifications(
        self, notif_repo, db_session, sample_user, sample_skill, sample_tool
    ):
        await notif_repo.create_missing([sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id)
        await notif_repo.create_missing([sample_user.id], NotificationType.TOOL_ARCHIVED, tool_id=sample_tool.id)
        await db_session.commit()
        rows = await notif_repo.list_for_user(sample_user.id)
        read_one = next(n for n, _, _ in rows if n.type == NotificationType.SKILL_ARCHIVED)
        await notif_repo.mark_read(read_one)
        await db_session.commit()

        unread = await notif_repo.list_for_user(sample_user.id, unread_only=True)

        assert [n.type for n, _, _ in unread] == [NotificationType.TOOL_ARCHIVED]
        assert len(await notif_repo.list_for_user(sample_user.id)) == 2


class TestUnreadAndOwnership:

    async def test_count_unread_reflects_reads(
        self, notif_repo, db_session, sample_user, sample_skill, sample_tool
    ):
        await notif_repo.create_missing([sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id)
        await notif_repo.create_missing([sample_user.id], NotificationType.TOOL_ARCHIVED, tool_id=sample_tool.id)
        await db_session.commit()
        assert await notif_repo.count_unread(sample_user.id) == 2

        rows = await notif_repo.list_for_user(sample_user.id)
        await notif_repo.mark_read(rows[0][0])
        await db_session.commit()

        assert await notif_repo.count_unread(sample_user.id) == 1

    async def test_count_unread_is_user_scoped(
        self, notif_repo, db_session, sample_user, another_user, sample_skill
    ):
        await notif_repo.create_missing([another_user.id], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id)
        await db_session.commit()

        assert await notif_repo.count_unread(sample_user.id) == 0

    async def test_get_owned_returns_only_own_notification(
        self, notif_repo, db_session, sample_user, another_user, sample_skill
    ):
        await notif_repo.create_missing([sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id)
        await db_session.commit()
        notification = (await notif_repo.list_for_user(sample_user.id))[0][0]

        assert (await notif_repo.get_owned(notification.id, sample_user.id)).id == notification.id
        assert await notif_repo.get_owned(notification.id, another_user.id) is None
        assert await notif_repo.get_owned(999_999, sample_user.id) is None


class TestMarkRead:

    async def test_mark_read_is_persisted(
        self, notif_repo, db_session, sample_user, sample_skill
    ):
        await notif_repo.create_missing([sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id)
        await db_session.commit()
        notification = (await notif_repo.list_for_user(sample_user.id))[0][0]

        await notif_repo.mark_read(notification)
        await db_session.commit()

        reloaded = await fresh_notification(db_session, notification.id)
        assert reloaded.read_at is not None
        assert reloaded.read_at.tzinfo is not None

    async def test_mark_read_twice_keeps_first_timestamp(
        self, notif_repo, db_session, sample_user, sample_skill
    ):
        await notif_repo.create_missing([sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id)
        await db_session.commit()
        notification = (await notif_repo.list_for_user(sample_user.id))[0][0]

        await notif_repo.mark_read(notification)
        await db_session.commit()
        first = (await fresh_notification(db_session, notification.id)).read_at

        await notif_repo.mark_read(notification)
        await db_session.commit()

        assert (await fresh_notification(db_session, notification.id)).read_at == first


class TestMarkAllRead:

    async def test_marks_all_unread_and_returns_count(
        self, notif_repo, db_session, sample_user, sample_skill, sample_tool
    ):
        await notif_repo.create_missing([sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id)
        await notif_repo.create_missing([sample_user.id], NotificationType.TOOL_ARCHIVED, tool_id=sample_tool.id)
        await db_session.commit()

        updated = await notif_repo.mark_all_read(sample_user.id)
        await db_session.commit()

        assert updated == 2
        assert await notif_repo.count_unread(sample_user.id) == 0

    async def test_does_not_touch_other_users(
        self, notif_repo, db_session, sample_user, another_user, sample_skill
    ):
        await notif_repo.create_missing(
            [sample_user.id, another_user.id], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id
        )
        await db_session.commit()

        await notif_repo.mark_all_read(sample_user.id)
        await db_session.commit()

        assert await notif_repo.count_unread(another_user.id) == 1

    async def test_already_read_are_not_counted_or_modified(
        self, notif_repo, db_session, sample_user, sample_skill, sample_tool
    ):
        await notif_repo.create_missing([sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=sample_skill.id)
        await db_session.commit()
        await notif_repo.mark_all_read(sample_user.id)
        await db_session.commit()
        notification = (await notif_repo.list_for_user(sample_user.id))[0][0]
        first_read_at = (await fresh_notification(db_session, notification.id)).read_at

        await notif_repo.create_missing([sample_user.id], NotificationType.TOOL_ARCHIVED, tool_id=sample_tool.id)
        await db_session.commit()
        updated = await notif_repo.mark_all_read(sample_user.id)
        await db_session.commit()

        assert updated == 1
        assert (await fresh_notification(db_session, notification.id)).read_at == first_read_at

    async def test_returns_zero_when_nothing_to_mark(self, notif_repo, sample_user):
        assert await notif_repo.mark_all_read(sample_user.id) == 0