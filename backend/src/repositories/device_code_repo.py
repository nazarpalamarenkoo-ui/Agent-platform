from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.device_code import DeviceCode
from src.repositories.base_repo import BaseRepository


def _is_active():
    return (
        DeviceCode.revoked_at.is_(None),
        DeviceCode.expires_at > datetime.now(timezone.utc),
    )


class DeviceCodeRepository(BaseRepository[DeviceCode]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, DeviceCode)

    async def get_by_token_hash(self, token_hash: str) -> Optional[DeviceCode]:
        result = await self.session.execute(
            select(DeviceCode).where(DeviceCode.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def get_active_by_token_hash(self, token_hash: str) -> Optional[DeviceCode]:
        result = await self.session.execute(
            select(DeviceCode).where(
                DeviceCode.token_hash == token_hash, *_is_active()
            )
        )
        return result.scalar_one_or_none()

    async def get_owned(self, device_id: int, user_id: int) -> Optional[DeviceCode]:
        result = await self.session.execute(
            select(DeviceCode).where(
                DeviceCode.id == device_id, DeviceCode.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: int,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DeviceCode]:
        stmt = select(DeviceCode).where(DeviceCode.user_id == user_id)
        if active_only:
            stmt = stmt.where(*_is_active())
        stmt = (
            stmt.order_by(DeviceCode.created_at.desc(), DeviceCode.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def revoke(self, device: DeviceCode) -> DeviceCode:
        if device.revoked_at is None:
            device.revoked_at = datetime.now(timezone.utc)
            await self.session.flush()
        return device

    async def touch(self, device: DeviceCode) -> DeviceCode:
        device.last_used_at = datetime.now(timezone.utc)
        await self.session.flush()
        return device