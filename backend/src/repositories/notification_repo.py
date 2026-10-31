from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.enums.notification_type import NotificationType
from src.db.models.notification import Notification
from src.db.models.skills import Skill
from src.db.models.tools_definition import ToolDefinition
from src.repositories.base_repo import BaseRepository

CHUNK_SIZE = 1000


class NotificationRepository(BaseRepository[Notification]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, Notification)

    async def create_missing(
        self,
        user_ids: Sequence[int],
        notification_type: NotificationType,
        skill_id: int | None = None,
        tool_id: int | None = None,
    ) -> int:
        if (skill_id is None) == (tool_id is None):
            raise ValueError("Exactly one of skill_id and tool_id must be provided")

        ids = list(dict.fromkeys(user_ids))
        if not ids:
            return 0

        existing: set[int] = set()
        for start in range(0, len(ids), CHUNK_SIZE):
            chunk = ids[start:start + CHUNK_SIZE]
            stmt = select(Notification.user_id).where(
                Notification.type == notification_type,
                Notification.user_id.in_(chunk),
            )
            if skill_id is not None:
                stmt = stmt.where(Notification.skill_id == skill_id)
            else:
                stmt = stmt.where(Notification.tool_id == tool_id)
            existing.update((await self.session.execute(stmt)).scalars().all())

        new_ids = [user_id for user_id in ids if user_id not in existing]
        self.session.add_all(
            [
                Notification(
                    user_id=user_id,
                    type=notification_type,
                    skill_id=skill_id,
                    tool_id=tool_id,
                )
                for user_id in new_ids
            ]
        )
        await self.session.flush()
        return len(new_ids)

    async def delete_for_item(
        self,
        notification_type: NotificationType,
        skill_id: int | None = None,
        tool_id: int | None = None,
    ) -> None:
        stmt = delete(Notification).where(Notification.type == notification_type)
        if skill_id is not None:
            stmt = stmt.where(Notification.skill_id == skill_id)
        elif tool_id is not None:
            stmt = stmt.where(Notification.tool_id == tool_id)
        else:
            raise ValueError("Exactly one of skill_id and tool_id must be provided")
        await self.session.execute(stmt)
        await self.session.flush()

    async def list_for_user(
        self,
        user_id: int,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ):
        stmt = (
            select(Notification, Skill.skill_name, ToolDefinition.tool_name)
            .outerjoin(Skill, Skill.id == Notification.skill_id)
            .outerjoin(ToolDefinition, ToolDefinition.id == Notification.tool_id)
            .where(Notification.user_id == user_id)
        )
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))
        stmt = (
            stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.all())

    async def count_unread(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
        )
        return int(result.scalar_one())

    async def get_owned(self, notification_id: int, user_id: int) -> Optional[Notification]:
        result = await self.session.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def mark_read(self, notification: Notification) -> Notification:
        if notification.read_at is None:
            notification.read_at = datetime.now(timezone.utc)
            await self.session.flush()
        return notification

    async def mark_all_read(self, user_id: int) -> int:
        result = await self.session.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            .values(read_at=datetime.now(timezone.utc))
        )
        await self.session.flush()
        return result.rowcount or 0