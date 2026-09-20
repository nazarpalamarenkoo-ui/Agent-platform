from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.device_code import DeviceCode
from src.db.enums.device_code_status import DeviceStatus
from src.repositories.base_repo import BaseRepository


class DeviceCodeRepository(BaseRepository[DeviceCode]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, DeviceCode)

    async def get_by_code(self, device_code: str) -> Optional[DeviceCode]:
        
        result = await self.session.execute(
            select(DeviceCode).where(DeviceCode.device_code == device_code)
        )
        return result.scalar_one_or_none()

    async def get_pending_for_user(self, user_id: int) -> list[DeviceCode]:
        
        result = await self.session.execute(
            select(DeviceCode).where(
                DeviceCode.user_id == user_id,
                DeviceCode.status == DeviceStatus.PENDING,
            )
        )
        return list(result.scalars().all())

    async def approve(self, device_code: DeviceCode) -> DeviceCode:
        
        device_code.status = DeviceStatus.APPROVED
        await self.session.flush()
        return device_code

    async def reject(self, device_code: DeviceCode) -> DeviceCode:
        
        device_code.status = DeviceStatus.REJECTED
        await self.session.flush()
        return device_code

    async def expire_stale(self) -> None:
        
        await self.session.execute(
            update(DeviceCode)
            .where(
                DeviceCode.status == DeviceStatus.PENDING,
                DeviceCode.expires_at < datetime.now(timezone.utc),
            )
            .values(status=DeviceStatus.EXPIRED)
        )
        await self.session.flush()

    async def get_valid_by_code(self, device_code: str) -> Optional[DeviceCode]:
        
        result = await self.session.execute(
            select(DeviceCode).where(
                DeviceCode.device_code == device_code,
                DeviceCode.status == DeviceStatus.PENDING,
                DeviceCode.expires_at > datetime.now(timezone.utc),
            )
        )
        return result.scalar_one_or_none()