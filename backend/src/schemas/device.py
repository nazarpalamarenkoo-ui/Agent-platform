from pydantic import BaseModel
from datetime import datetime


class DeviceCodeInitiate(BaseModel):
    user_id: int
    scope: str


class DeviceCodeRead(BaseModel):
    id: int
    device_code: str
    scope: str
    expires_at: datetime
    interval: int
    model_config = {"from_attributes": True}


class DeviceVerify(BaseModel):
    device_code: str


class DeviceTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"