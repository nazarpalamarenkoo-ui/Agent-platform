from datetime import datetime

from pydantic import BaseModel, Field

SCOPE_PATTERN = r"^[a-z0-9_:.\-]+( [a-z0-9_:.\-]+)*$"


class DeviceTokenCreate(BaseModel):
    scope: str = Field(min_length=1, max_length=100, pattern=SCOPE_PATTERN)
    name: str = Field(default="device", min_length=1, max_length=100)
    config_bundle_id: int | None = None


class DeviceRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    config_bundle_id: int | None = None
    expires_at: datetime


class DeviceTokenIssued(DeviceRead):
    access_token: str
    token_type: str = "bearer"