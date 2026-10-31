import pytest

from src.db.enums.notification_type import NotificationType
from src.repositories.notification_repo import NotificationRepository
from src.services.errors import NotFoundError
from src.services.notification_service import NotificationService


@pytest.fixture
def repo(db_session):
    return NotificationRepository(db_session)


@pytest.fixture
def service(repo):
    return NotificationService(repo)


class TestListNotifications:
    async def test_returns_view_with_skill_name(
        self, service, repo, sample_user, make_skill
    ):
        skill = await make_skill()
        await repo.create_missing(
            [sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=skill.id
        )

        views = await service.list_notifications(sample_user)

        assert len(views) == 1
        assert views[0].type == NotificationType.SKILL_ARCHIVED
        assert views[0].skill_id == skill.id
        assert views[0].tool_id is None
        assert views[0].item_name == skill.skill_name
        assert views[0].read_at is None

    async def test_returns_view_with_tool_name(
        self, service, repo, sample_user, make_tool
    ):
        tool = await make_tool()
        await repo.create_missing(
            [sample_user.id], NotificationType.TOOL_ARCHIVED, tool_id=tool.id
        )

        views = await service.list_notifications(sample_user)

        assert len(views) == 1
        assert views[0].tool_id == tool.id
        assert views[0].item_name == tool.tool_name

    async def test_does_not_return_other_users_notifications(
        self, service, repo, sample_user, another_user, make_skill
    ):
        skill = await make_skill()
        await repo.create_missing(
            [another_user.id], NotificationType.SKILL_ARCHIVED, skill_id=skill.id
        )

        assert await service.list_notifications(sample_user) == []

    async def test_unread_only_filters_read_ones(
        self, service, repo, sample_user, make_skill
    ):
        s1, s2 = await make_skill(), await make_skill()
        await repo.create_missing(
            [sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=s1.id
        )
        await repo.create_missing(
            [sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=s2.id
        )
        all_views = await service.list_notifications(sample_user)
        await service.mark_read(sample_user, all_views[0].id)

        unread = await service.list_notifications(sample_user, unread_only=True)

        assert len(unread) == 1
        assert unread[0].id != all_views[0].id

    async def test_respects_limit_and_offset(
        self, service, repo, sample_user, make_skill
    ):
        for _ in range(3):
            skill = await make_skill()
            await repo.create_missing(
                [sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=skill.id
            )

        first = await service.list_notifications(sample_user, limit=2, offset=0)
        rest = await service.list_notifications(sample_user, limit=2, offset=2)

        assert len(first) == 2
        assert len(rest) == 1
        assert {v.id for v in first}.isdisjoint({v.id for v in rest})


class TestCreateMissing:
    async def test_is_idempotent_for_same_item(
        self, service, repo, sample_user, make_skill
    ):
        skill = await make_skill()
        for _ in range(2):
            await repo.create_missing(
                [sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=skill.id
            )

        assert await service.unread_count(sample_user) == 1


class TestUnreadCount:
    async def test_is_zero_without_notifications(self, service, sample_user):
        assert await service.unread_count(sample_user) == 0

    async def test_decreases_after_mark_read(
        self, service, repo, sample_user, make_skill
    ):
        skill = await make_skill()
        await repo.create_missing(
            [sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=skill.id
        )
        assert await service.unread_count(sample_user) == 1

        [view] = await service.list_notifications(sample_user)
        await service.mark_read(sample_user, view.id)

        assert await service.unread_count(sample_user) == 0


class TestMarkRead:
    async def test_sets_read_at(self, service, repo, sample_user, make_skill):
        skill = await make_skill()
        await repo.create_missing(
            [sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=skill.id
        )
        [view] = await service.list_notifications(sample_user)

        await service.mark_read(sample_user, view.id)

        [after] = await service.list_notifications(sample_user)
        assert after.read_at is not None

    async def test_raises_for_unknown_notification(self, service, sample_user):
        with pytest.raises(NotFoundError, match="Notification not found"):
            await service.mark_read(sample_user, 999_999)

    async def test_raises_when_notification_belongs_to_another_user(
        self, service, repo, sample_user, another_user, make_skill
    ):
        skill = await make_skill()
        await repo.create_missing(
            [another_user.id], NotificationType.SKILL_ARCHIVED, skill_id=skill.id
        )
        [foreign] = await service.list_notifications(another_user)

        with pytest.raises(NotFoundError):
            await service.mark_read(sample_user, foreign.id)

        assert await service.unread_count(another_user) == 1


class TestMarkAllRead:
    async def test_marks_only_own_unread_and_returns_count(
        self, service, repo, sample_user, another_user, make_skill
    ):
        for _ in range(2):
            skill = await make_skill()
            await repo.create_missing(
                [sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=skill.id
            )
        other_skill = await make_skill()
        await repo.create_missing(
            [another_user.id], NotificationType.SKILL_ARCHIVED, skill_id=other_skill.id
        )

        affected = await service.mark_all_read(sample_user)

        assert affected == 2
        assert await service.unread_count(sample_user) == 0
        assert await service.unread_count(another_user) == 1

    async def test_returns_zero_when_nothing_unread(self, service, sample_user):
        assert await service.mark_all_read(sample_user) == 0