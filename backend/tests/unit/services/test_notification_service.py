from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.db.enums.notification_type import NotificationType
from src.services.errors import NotFoundError
from src.services.notification_service import NotificationService, NotificationView

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
ACTOR = SimpleNamespace(id=7)


@pytest.fixture
def repo():
    return AsyncMock()


@pytest.fixture
def service(repo):
    return NotificationService(repo)


def make_notification(id=1, type=NotificationType.SKILL_ARCHIVED, skill_id=None, tool_id=None, read_at=None):
    return SimpleNamespace(
        id=id, type=type, skill_id=skill_id, tool_id=tool_id, read_at=read_at, created_at=NOW
    )


class TestListNotifications:
    async def test_passes_filters_to_repo(self, service, repo):
        repo.list_for_user.return_value = []

        result = await service.list_notifications(ACTOR, unread_only=True, limit=10, offset=20)

        assert result == []
        repo.list_for_user.assert_awaited_once_with(7, unread_only=True, limit=10, offset=20)

    async def test_defaults(self, service, repo):
        repo.list_for_user.return_value = []

        await service.list_notifications(ACTOR)

        repo.list_for_user.assert_awaited_once_with(7, unread_only=False, limit=50, offset=0)

    async def test_maps_skill_notification(self, service, repo):
        n = make_notification(id=1, skill_id=3)
        repo.list_for_user.return_value = [(n, "my-skill", None)]

        [view] = await service.list_notifications(ACTOR)

        assert view == NotificationView(
            id=1, type=NotificationType.SKILL_ARCHIVED, skill_id=3, tool_id=None,
            item_name="my-skill", read_at=None, created_at=NOW,
        )

    async def test_maps_tool_notification(self, service, repo):
        n = make_notification(id=2, type=NotificationType.TOOL_ARCHIVED, tool_id=4)
        repo.list_for_user.return_value = [(n, None, "my-tool")]

        [view] = await service.list_notifications(ACTOR)

        assert view.item_name == "my-tool"
        assert view.tool_id == 4

    async def test_item_name_is_none_when_item_deleted(self, service, repo):
        repo.list_for_user.return_value = [(make_notification(), None, None)]

        [view] = await service.list_notifications(ACTOR)

        assert view.item_name is None

    async def test_preserves_order(self, service, repo):
        rows = [(make_notification(id=i), f"s{i}", None) for i in (3, 1, 2)]
        repo.list_for_user.return_value = rows

        views = await service.list_notifications(ACTOR)

        assert [v.id for v in views] == [3, 1, 2]


class TestUnreadCount:
    async def test_delegates(self, service, repo):
        repo.count_unread.return_value = 5

        assert await service.unread_count(ACTOR) == 5
        repo.count_unread.assert_awaited_once_with(7)


class TestMarkRead:
    async def test_marks_owned_notification(self, service, repo):
        notification = make_notification()
        repo.get_owned.return_value = notification

        await service.mark_read(ACTOR, 1)

        repo.get_owned.assert_awaited_once_with(1, 7)
        repo.mark_read.assert_awaited_once_with(notification)

    async def test_raises_when_not_found_or_not_owned(self, service, repo):
        repo.get_owned.return_value = None

        with pytest.raises(NotFoundError, match="Notification not found"):
            await service.mark_read(ACTOR, 1)

        repo.mark_read.assert_not_awaited()


class TestMarkAllRead:
    async def test_returns_number_updated(self, service, repo):
        repo.mark_all_read.return_value = 4

        assert await service.mark_all_read(ACTOR) == 4
        repo.mark_all_read.assert_awaited_once_with(7)