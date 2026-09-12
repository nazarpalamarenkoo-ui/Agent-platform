import secrets
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone

from src.config import settings
from src.repositories.device_code_repo import DeviceCodeRepository, DeviceStatus
from src.db.models.device_code import DeviceCode

class DeviceAuthService:
    
    def __init__(self, device_code_repo: DeviceCodeRepository):
        self.device_code_repo = device_code_repo
        
    async def initiate_flow(self, user_id: int, scope: str) -> DeviceCode:
        code = secrets.token_urlsafe(16)

        device_code = await self.device_code_repo.create(
            device_code=code,
            user_id=user_id,
            scope=scope,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            interval=5,
            status=DeviceStatus.PENDING,
        )

        return device_code
    
    async def verify_and_approve(self, device_code_str: str) -> str:
        
        device_code = await self.device_code_repo.get_valid_by_code(device_code_str)

        if not device_code:
            raise ValueError("Invalid or expired device code")

        await self.device_code_repo.approve(device_code)

        token = jwt.encode(
            {
                "sub": str(device_code.user_id),
                "scope": device_code.scope,
                "exp": datetime.now(timezone.utc) + timedelta(days=30),
            },
            settings.JWT_SECRET_KEY,
            algorithm="HS256",
        )

        return token