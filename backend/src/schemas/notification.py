from datetime import datetime

from pydantic import BaseModel

from src.db.enums.notification_type import NotificationType


class NotificationRead(BaseModel):
    id: int
    type: NotificationType
    skill_id: int | None
    tool_id: int | None
    item_name: str | None
    read_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class UnreadCount(BaseModel):
    unread: int


class MarkedRead(BaseModel):
    updated: int