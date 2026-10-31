import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from src.config import settings
from src.db.models.device_code import DeviceCode
from src.repositories.device_code_repo import DeviceCodeRepository
from src.services.errors import NotFoundError

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
TOKEN_TYPE_DEVICE = "device"
DEVICE_TOKEN_TTL = timedelta(days=30)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class DeviceAuthService:

    def __init__(self, device_code_repo: DeviceCodeRepository):
        self.device_code_repo = device_code_repo

    async def issue_token(
        self,
        user_id: int,
        scope: str,
        name: str = "device",
        config_bundle_id: int | None = None,
    ) -> tuple[DeviceCode, str]:
        expires_at = datetime.now(timezone.utc) + DEVICE_TOKEN_TTL
        token = jwt.encode(
            {
                "sub": str(user_id),
                "typ": TOKEN_TYPE_DEVICE,
                "scope": scope,
                "jti": secrets.token_urlsafe(16),
                "exp": expires_at,
            },
            settings.JWT_SECRET_KEY,
            algorithm=ALGORITHM,
        )

        device = await self.device_code_repo.create(
            token_hash=hash_token(token),
            user_id=user_id,
            name=name,
            config_bundle_id=config_bundle_id,
            expires_at=expires_at,
        )

        logger.info("device_token_issued: user_id=%s scope=%s", user_id, scope)

        return device, token

    async def authenticate(self, token: str) -> DeviceCode:
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError:
            logger.warning("device_token_rejected: invalid_jwt")
            raise ValueError("Invalid or expired device token")

        if payload.get("typ") != TOKEN_TYPE_DEVICE:
            logger.warning("device_token_rejected: wrong_type")
            raise ValueError("Invalid or expired device token")

        device = await self.device_code_repo.get_active_by_token_hash(hash_token(token))
        if device is None or str(device.user_id) != payload.get("sub"):
            logger.warning("device_token_rejected: not_active")
            raise ValueError("Invalid or expired device token")

        await self.device_code_repo.touch(device)
        return device

    async def list_devices(
        self,
        user_id: int,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DeviceCode]:
        return await self.device_code_repo.list_for_user(
            user_id, active_only=active_only, limit=limit, offset=offset
        )

    async def revoke_device(self, user_id: int, device_id: int) -> DeviceCode:
        device = await self.device_code_repo.get_owned(device_id, user_id)
        if device is None:
            raise NotFoundError("Device not found")

        await self.device_code_repo.revoke(device)

        logger.info("device_token_revoked: user_id=%s device_id=%s", user_id, device_id)

        return device