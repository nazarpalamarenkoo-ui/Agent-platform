from fastapi import APIRouter, Depends, Query, status

from src.api.auth.auth import get_current_user
from src.api.routers.errors import to_http
from src.db.models.users import User
from src.dependencies import get_notification_service
from src.schemas.notification import MarkedRead, NotificationRead, UnreadCount
from src.services.notification_service import NotificationService

router = APIRouter(
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[NotificationRead])
async def list_notifications(
    unread_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    actor: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> list[NotificationRead]:
    items = await service.list_notifications(
        actor, unread_only=unread_only, limit=limit, offset=offset
    )
    return [NotificationRead.model_validate(i) for i in items]


@router.get("/unread-count", response_model=UnreadCount)
async def unread_count(
    actor: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> UnreadCount:
    return UnreadCount(unread=await service.unread_count(actor))


@router.post("/read-all", response_model=MarkedRead)
async def mark_all_read(
    actor: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> MarkedRead:
    return MarkedRead(updated=await service.mark_all_read(actor))


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    notification_id: int,
    actor: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> None:
    try:
        await service.mark_read(actor, notification_id)
    except ValueError as e:
        raise to_http(e)