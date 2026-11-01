from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.api.routers import notifications
from src.db.enums.notification_type import NotificationType
from src.dependencies import get_notification_service
from src.services.errors import NotFoundError
from src.services.notification_service import NotificationService

pytestmark = pytest.mark.unit

ROUTER = notifications.router
SERVICE_DEPENDENCY = get_notification_service
SERVICE_SPEC = NotificationService

NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)


def make_view(notification_id=1, **overrides):
    data = dict(
        id=notification_id,
        type=NotificationType.SKILL_ARCHIVED,
        skill_id=10,
        tool_id=None,
        item_name="my-skill",
        read_at=None,
        created_at=NOW,
    )
    data.update(overrides)
    return SimpleNamespace(**data)


class TestListNotifications:
    async def test_returns_serialized_notifications(self, client, service, actor):
        service.list_notifications.return_value = [make_view(1), make_view(2, read_at=NOW)]

        response = await client.get("/notifications")

        assert response.status_code == 200
        body = response.json()
        assert [n["id"] for n in body] == [1, 2]
        assert body[0]["type"] == NotificationType.SKILL_ARCHIVED.value
        assert body[0]["item_name"] == "my-skill"
        assert body[0]["read_at"] is None
        assert body[1]["read_at"] is not None
        service.list_notifications.assert_awaited_once_with(
            actor, unread_only=False, limit=50, offset=0
        )

    async def test_passes_query_params(self, client, service, actor):
        service.list_notifications.return_value = []

        await client.get("/notifications", params={"unread_only": True, "limit": 10, "offset": 5})

        service.list_notifications.assert_awaited_once_with(
            actor, unread_only=True, limit=10, offset=5
        )

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
    async def test_rejects_invalid_pagination(self, client, service, params):
        response = await client.get("/notifications", params=params)

        assert response.status_code == 422
        service.list_notifications.assert_not_awaited()


class TestCounters:
    async def test_unread_count(self, client, service, actor):
        service.unread_count.return_value = 4

        response = await client.get("/notifications/unread-count")

        assert response.status_code == 200
        assert response.json() == {"unread": 4}
        service.unread_count.assert_awaited_once_with(actor)

    async def test_mark_all_read(self, client, service, actor):
        service.mark_all_read.return_value = 3

        response = await client.post("/notifications/read-all")

        assert response.status_code == 200
        assert response.json() == {"updated": 3}
        service.mark_all_read.assert_awaited_once_with(actor)
        service.mark_read.assert_not_awaited()


class TestMarkRead:
    async def test_returns_204(self, client, service, actor):
        response = await client.post("/notifications/5/read")

        assert response.status_code == 204
        assert response.content == b""
        service.mark_read.assert_awaited_once_with(actor, 5)

    async def test_not_found_returns_404(self, client, service):
        service.mark_read.side_effect = NotFoundError("Notification not found")

        response = await client.post("/notifications/5/read")

        assert response.status_code == 404
        assert response.json()["detail"] == "Notification not found"

    async def test_invalid_id(self, client, service):
        response = await client.post("/notifications/abc/read")

        assert response.status_code == 422
        service.mark_read.assert_not_awaited()