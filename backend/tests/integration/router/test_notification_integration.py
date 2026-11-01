import pytest
import pytest_asyncio

from src.api.routers import notifications
from src.db.db_connection import get_db
from src.db.enums.notification_type import NotificationType
from src.repositories.notification_repo import NotificationRepository

pytestmark = [pytest.mark.integration, pytest.mark.db]


@pytest.fixture
def app(db_session, build_app):
    application = build_app(notifications.router)
    application.dependency_overrides[get_db] = lambda: db_session
    return application


@pytest.fixture(autouse=True)
def real_actor(default_actor, sample_user):
    default_actor.id = sample_user.id
    return default_actor


@pytest_asyncio.fixture
async def violation_notification(db_session, sample_user, make_skill):
    skill = await make_skill(owner=sample_user)
    await NotificationRepository(db_session).create_missing(
        [sample_user.id], NotificationType.SKILL_ARCHIVED, skill_id=skill.id
    )
    return skill


async def test_list_is_empty_for_user_without_notifications(client):
    response = await client.get("/notifications")

    assert response.status_code == 200, response.text
    assert response.json() == []


async def test_unread_count_is_zero_without_notifications(client):
    response = await client.get("/notifications/unread-count")

    assert response.status_code == 200, response.text
    assert response.json() == {"unread": 0}


async def test_read_all_without_notifications_updates_nothing(client):
    response = await client.post("/notifications/read-all")

    assert response.status_code == 200, response.text
    assert response.json() == {"updated": 0}


async def test_mark_unknown_notification_read_returns_404(client):
    response = await client.post("/notifications/999999/read")

    assert response.status_code == 404, response.text


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
async def test_list_invalid_pagination_returns_422(client, params):
    response = await client.get("/notifications", params=params)

    assert response.status_code == 422, response.text


async def test_owner_sees_notification_about_archived_skill(client, violation_notification):
    skill = violation_notification

    response = await client.get("/notifications")

    assert response.status_code == 200, response.text
    item = response.json()[0]
    assert item["skill_id"] == skill.id
    assert item["item_name"] == skill.skill_name
    assert item["read_at"] is None
    assert item["created_at"]


async def test_notification_is_private_to_its_owner(
    client, default_actor, another_user, violation_notification
):
    default_actor.id = another_user.id

    listed = await client.get("/notifications")
    count = await client.get("/notifications/unread-count")

    assert listed.json() == []
    assert count.json() == {"unread": 0}


async def test_unread_count_reflects_new_notification(client, violation_notification):
    response = await client.get("/notifications/unread-count")

    assert response.json() == {"unread": 1}


async def test_mark_read_sets_read_at_and_decrements_counter(client, violation_notification):
    notification_id = (await client.get("/notifications")).json()[0]["id"]

    response = await client.post(f"/notifications/{notification_id}/read")

    assert response.status_code == 204, response.text
    assert (await client.get("/notifications/unread-count")).json() == {"unread": 0}
    assert (await client.get("/notifications")).json()[0]["read_at"] is not None


async def test_unread_only_filter_hides_read_notifications(client, violation_notification):
    notification_id = (await client.get("/notifications")).json()[0]["id"]
    await client.post(f"/notifications/{notification_id}/read")

    unread = await client.get("/notifications", params={"unread_only": True})
    everything = await client.get("/notifications")

    assert unread.json() == []
    assert len(everything.json()) == 1


async def test_mark_read_all_updates_every_unread_notification(client, violation_notification):
    first = await client.post("/notifications/read-all")
    second = await client.post("/notifications/read-all")

    assert first.json() == {"updated": 1}
    assert second.json() == {"updated": 0}


async def test_cannot_mark_foreign_notification_read(
    client, default_actor, sample_user, another_user, violation_notification
):
    notification_id = (await client.get("/notifications")).json()[0]["id"]
    default_actor.id = another_user.id

    response = await client.post(f"/notifications/{notification_id}/read")

    assert response.status_code in (403, 404), response.text
    default_actor.id = sample_user.id
    assert (await client.get("/notifications/unread-count")).json() == {"unread": 1}