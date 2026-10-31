from dataclasses import dataclass
from datetime import datetime

from src.db.enums.notification_type import NotificationType
from src.db.models.users import User
from src.repositories.notification_repo import NotificationRepository
from src.services.errors import NotFoundError


@dataclass(frozen=True)
class NotificationView:
    id: int
    type: NotificationType
    skill_id: int | None
    tool_id: int | None
    item_name: str | None
    read_at: datetime | None
    created_at: datetime


class NotificationService:

    def __init__(self, notification_repo: NotificationRepository):
        self.notification_repo = notification_repo

    async def list_notifications(
        self,
        actor: User,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[NotificationView]:
        rows = await self.notification_repo.list_for_user(
            actor.id, unread_only=unread_only, limit=limit, offset=offset
        )
        return [
            NotificationView(
                id=n.id,
                type=n.type,
                skill_id=n.skill_id,
                tool_id=n.tool_id,
                item_name=skill_name or tool_name,
                read_at=n.read_at,
                created_at=n.created_at,
            )
            for n, skill_name, tool_name in rows
        ]

    async def unread_count(self, actor: User) -> int:
        return await self.notification_repo.count_unread(actor.id)

    async def mark_read(self, actor: User, notification_id: int) -> None:
        notification = await self.notification_repo.get_owned(notification_id, actor.id)
        if notification is None:
            raise NotFoundError("Notification not found")
        await self.notification_repo.mark_read(notification)

    async def mark_all_read(self, actor: User) -> int:
        return await self.notification_repo.mark_all_read(actor.id)